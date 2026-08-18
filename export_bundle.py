#!/usr/bin/env python3
"""
Export a bundle as a self-contained ZIP archive.

Copies source PDFs into a numbered folder/file structure that mirrors the
compiled index, then adds a freestanding index.pdf, an updated _config.toml,
and an updated _structure.csv so the archive can be re-ingested by the bundler.

Usage:
    .venv/bin/python export_bundle.py --source PATH [--output PATH]

--source accepts the same inputs as preview_bundle.py (directory or .toml file).
--output is the destination .zip path (default: output/<bundle-title>.zip).
"""

import argparse
import csv
import logging
import re
import shutil
import tempfile
import tomllib
import zipfile
from copy import deepcopy
from pathlib import Path

import tomli_w

logging.basicConfig(level=logging.WARNING, format="%(message)s")
logging.getLogger("pypdf").setLevel(logging.ERROR)

from bundler.cover import build_cover
from bundler.index import generate_index
from bundler.merger import stamp_pdf
from bundler.models import TOCEntry
from bundler.paginator import calculate_pagination

SOURCE_DEFAULT = Path("source")
OUTPUT_DIR     = Path("output")

# ── Helpers ────────────────────────────────────────────────────────────────────

def _safe_name(text: str) -> str:
    """Make a string safe for Windows filenames.

    Quotes are dropped entirely; all other Windows-forbidden characters
    (\\/:*?<>|) are replaced with underscores.  Trailing dots are also
    removed (a Windows edge case).
    """
    text = re.sub(r'[\'"]', "", text)           # drop quotes
    text = re.sub(r'[\\/:*?<>|]', "_", text)   # replace other forbidden chars
    text = re.sub(r"\s+", " ", text).strip()
    text = text.rstrip(".")                      # trailing dot illegal on Windows
    return text or "Untitled"


def _pad(n: int, total: int) -> str:
    """Zero-pad *n* to match the width of *total*."""
    width = max(2, len(str(total)))
    return str(n).zfill(width)


# ── CSV loading (mirrors preview_bundle.py) ────────────────────────────────────

def _load_entries(csv_path: Path) -> list[TOCEntry]:
    entries: list[TOCEntry] = []
    doc_index = 0
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            entry_type = row["entry_type"].strip()
            title      = row["title"].strip()
            file_name  = row["file_name"].strip() or None
            section    = row["section"].strip()

            if entry_type == "section_heading":
                entries.append(TOCEntry(entry_type="section_heading",
                                        title=title or section.upper()))
            elif entry_type == "heading":
                entries.append(TOCEntry(entry_type="heading", title=title))
            elif entry_type == "document":
                doc_index += 1
                entries.append(TOCEntry(entry_type="document", title=title,
                                        file_name=file_name,
                                        dest_name=f"doc_{doc_index}"))
    return entries


# ── Core export logic ──────────────────────────────────────────────────────────

def export_bundle(
    case_meta_path: Path,
    docs_dir: Path,
    csv_path: Path,
    raw_toml: dict,
    out_zip: Path,
    stamp: bool = False,
    style: str | None = None,
) -> None:
    """Build the export ZIP. Prints progress to stdout."""

    entries = _load_entries(csv_path)
    doc_total = sum(1 for e in entries if e.entry_type == "document")

    # ── Pagination — cover occupies page 1, index follows, then documents ──────
    numbered, missing = calculate_pagination(entries, docs_dir,
                                             strict=False, cover_pages=1)
    if missing:
        for p in missing:
            print(f"WARNING:    missing file, skipped — {Path(p).name}")

    # ── Generate freestanding index ───────────────────────────────────────────
    with tempfile.TemporaryDirectory() as _td:
        tmp = Path(_td)

        # ── Generate cover ────────────────────────────────────────────────────
        cover_tmp = tmp / "cover.pdf"
        build_cover(case_meta_path, cover_tmp, style=style)

        # ── Generate index (page numbers now include the cover offset) ────────
        index_tmp = tmp / "index.pdf"
        index_pages, _ = generate_index(numbered, index_tmp)
        print(f"Index:      {index_pages} page{'s' if index_pages != 1 else ''}")

        # ── Build in-memory folder layout ─────────────────────────────────────
        # section_counter : sequential number for folder naming
        # doc_counter     : global doc number shown in the index
        root = tmp / "export"
        root.mkdir()

        section_counter = 0
        doc_counter     = 0
        section_dir: Path = root          # docs before any heading go to root
        section_total = sum(1 for e in entries if e.entry_type == "section_heading")

        # new CSV rows, rebuilt with updated file_name paths
        new_rows: list[dict] = []
        # read original CSV column names to preserve them
        with csv_path.open(newline="", encoding="utf-8") as f:
            orig_fieldnames = csv.DictReader(f).fieldnames or []

        with csv_path.open(newline="", encoding="utf-8") as f:
            orig_rows = list(csv.DictReader(f))

        orig_iter = iter(orig_rows)

        for entry in numbered:
            orig_row = next(orig_iter)
            new_row = dict(orig_row)

            if entry.entry_type == "section_heading":
                section_counter += 1
                folder_name = f"{_pad(section_counter, section_total)} - {_safe_name(entry.title)}"
                section_dir = root / folder_name
                section_dir.mkdir(exist_ok=True)
                # section_heading rows have no file_name; leave unchanged

            elif entry.entry_type == "document":
                doc_counter += 1
                safe_title  = _safe_name(entry.title)
                dest_name   = f"{_pad(doc_counter, doc_total)} - {safe_title}.pdf"
                dest_path   = section_dir / dest_name

                # Relative path from export root → used in new CSV
                rel_path = dest_path.relative_to(root)

                if entry.file_name and entry.page_number is not None:
                    src = docs_dir / entry.file_name
                    if src.exists():
                        if stamp:
                            stamp_pdf(src, dest_path, entry.page_number)
                        else:
                            shutil.copy2(src, dest_path)
                    else:
                        print(f"SKIP:       {entry.file_name} not found")
                # else: placeholder — no file to copy

                new_row["file_name"] = str(rel_path)

            new_rows.append(new_row)

        # ── Write updated _structure.csv ──────────────────────────────────────
        new_csv = root / "_structure.csv"
        with new_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=orig_fieldnames)
            writer.writeheader()
            writer.writerows(new_rows)

        # ── Write updated _config.toml ────────────────────────────────────────
        new_toml = deepcopy(raw_toml)
        new_toml.setdefault("bundle", {})
        new_toml["bundle"]["docs_root"] = "."
        new_toml["bundle"]["sequence"]  = "_structure.csv"

        new_toml_path = root / "_config.toml"
        new_toml_path.write_bytes(tomli_w.dumps(new_toml).encode())

        # ── Cover (page 1) ────────────────────────────────────────────────────
        if stamp:
            stamp_pdf(cover_tmp, root / "cover.pdf", start_page=1)
        else:
            shutil.copy2(cover_tmp, root / "cover.pdf")

        # ── Index (starts at page 2, after the single-page cover) ───────────
        if stamp:
            stamp_pdf(index_tmp, root / "index.pdf", start_page=2)
        else:
            shutil.copy2(index_tmp, root / "index.pdf")

        # ── ZIP ───────────────────────────────────────────────────────────────
        bundle_title = _safe_name(raw_toml.get("bundle", {}).get("title", "Bundle"))
        out_zip.parent.mkdir(parents=True, exist_ok=True)

        file_count = 0
        with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED,
                             compresslevel=1) as zf:
            for f in sorted(root.rglob("*")):
                if f.is_file():
                    arcname = Path(bundle_title) / f.relative_to(root)
                    zf.write(f, arcname)
                    file_count += 1

        size_mb = out_zip.stat().st_size / 1_048_576
        print(f"Exported:   {out_zip}  ({file_count} files, {size_mb:.1f} MB)")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export a bundle as a self-contained ZIP archive.")
    parser.add_argument("--source", type=Path, default=SOURCE_DEFAULT,
                        help="Directory containing _case.toml, or path to a .toml file")
    parser.add_argument("--output", "-o", type=Path, default=None,
                        help="Destination .zip path (default: output/<title>.zip)")
    parser.add_argument("--style", choices=["court", "statdec"], default=None,
                        help="Cover page style (overrides [cover] style in the TOML; "
                             "default: 'court')")
    parser.add_argument("--stamp", action="store_true", default=False,
                        help="Stamp bundle page numbers onto each exported PDF")
    args = parser.parse_args()

    source: Path = args.source
    if source.suffix == ".toml":
        case_meta_path = source.resolve()
        source_dir     = case_meta_path.parent
    else:
        source_dir     = source.resolve()
        case_meta_path = source_dir / "_case.toml"

    with case_meta_path.open("rb") as f:
        raw_toml = tomllib.load(f)
    _bundle = raw_toml.get("bundle", {})

    csv_path = (source_dir / _bundle.get("sequence", "_sequence.csv")).resolve()

    if "docs_root" in _bundle:
        docs_dir = (source_dir / _bundle["docs_root"]).resolve()
    else:
        docs_dir = source_dir

    bundle_title = _bundle.get("title", "Bundle")
    if args.output is not None:
        out_zip = args.output.resolve()
    else:
        out_zip = (OUTPUT_DIR / f"{_safe_name(bundle_title)}.zip").resolve()

    print(f"Config:     {case_meta_path}")
    print(f"CSV:        {csv_path}")
    print(f"Docs root:  {docs_dir}")
    print(f"Output:     {out_zip}")

    export_bundle(case_meta_path, docs_dir, csv_path, raw_toml, out_zip,
                  stamp=args.stamp, style=args.style)


if __name__ == "__main__":
    main()
