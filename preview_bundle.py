#!/usr/bin/env python3
"""
End-to-end preview: CSV → paginate → index → merge → single_bundle.pdf

Usage:
    .venv/bin/python preview_bundle.py [--source PATH]

--source can be:
  - A directory containing _case.toml and _sequence.csv  (default: source/)
  - A path to a .toml file directly

When using a .toml file, [bundle] may contain:
    docs_root = "/abs/or/relative/path"   # where PDFs live
    sequence  = "_sequence.csv"           # CSV path, relative to the toml

--docs overrides docs_root from the toml in all cases.

Output is written to output/:
    output/cover.pdf         — the generated cover page
    output/index.pdf         — the generated index
    output/single_bundle.pdf — the merged and page-stamped bundle
"""

import argparse
import csv
import logging
import tomllib
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(message)s")
logging.getLogger("pypdf").setLevel(logging.ERROR)

from bundler.cover import build_cover
from bundler.index import generate_index
from bundler.merger import build_bundle
from bundler.models import TOCEntry
from bundler.paginator import calculate_pagination

SOURCE_DEFAULT = Path("source")
OUTPUT_DIR     = Path("output")


def load_entries_from_csv(csv_path: Path) -> list[TOCEntry]:
    entries: list[TOCEntry] = []
    doc_index = 0
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            entry_type = row["entry_type"].strip()
            title      = row["title"].strip()
            file_name  = row["file_name"].strip() or None
            section    = row["section"].strip()

            if entry_type == "section_heading":
                entries.append(TOCEntry(
                    entry_type="section_heading",
                    title=title or section.upper(),
                ))
            elif entry_type == "heading":
                entries.append(TOCEntry(
                    entry_type="heading",
                    title=title,
                ))
            elif entry_type == "document":
                doc_index += 1
                entries.append(TOCEntry(
                    entry_type="document",
                    title=title,
                    file_name=file_name,
                    dest_name=f"doc_{doc_index}",
                ))
    return entries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE_DEFAULT,
                        help="Directory containing _case.toml, or path to a .toml file")
    parser.add_argument("--docs", type=Path, default=None,
                        help="Root directory for resolving PDF paths (overrides toml docs_root)")
    parser.add_argument("--style", choices=["court", "statdec"], default=None,
                        help="Cover page style (overrides [cover] style in the TOML; "
                             "default: 'court')")
    parser.add_argument("--output", "-o", type=Path, default=None,
                        help="Destination path for the compiled bundle PDF "
                             "(default: output/single_bundle.pdf)")
    args = parser.parse_args()

    source: Path = args.source

    # Resolve toml path and source directory
    if source.suffix == ".toml":
        case_meta_path = source.resolve()
        source_dir     = case_meta_path.parent
    else:
        source_dir     = source.resolve()
        case_meta_path = source_dir / "_case.toml"

    # Read paths from [bundle] section of the toml, resolve relative to the toml dir
    with case_meta_path.open("rb") as f:
        _raw = tomllib.load(f)
    _bundle = _raw.get("bundle", {})

    _seq_raw = _bundle.get("sequence", "_sequence.csv")
    csv_path = (source_dir / _seq_raw).resolve()

    if args.docs is not None:
        docs_dir = args.docs.resolve()
    elif "docs_root" in _bundle:
        docs_dir = (source_dir / _bundle["docs_root"]).resolve()
    else:
        docs_dir = source_dir

    if args.output is not None:
        bundle_path = args.output.resolve()
    else:
        bundle_path = OUTPUT_DIR / "single_bundle.pdf"
    bundle_path.parent.mkdir(parents=True, exist_ok=True)

    OUTPUT_DIR.mkdir(exist_ok=True)
    cover_path = OUTPUT_DIR / "cover.pdf"
    index_path = OUTPUT_DIR / "index.pdf"

    print(f"Config:     {case_meta_path}")
    print(f"CSV:        {csv_path}")
    print(f"Docs root:  {docs_dir}")

    # 1. Generate cover page
    build_cover(case_meta_path, cover_path, style=args.style)
    from bundler.paginator import count_pages
    cover_count = count_pages(cover_path)
    print(f"Cover:      {cover_path}  ({cover_count} page{'s' if cover_count != 1 else ''})")

    # 2. Load CSV
    entries = load_entries_from_csv(csv_path)
    doc_count = sum(1 for e in entries if e.entry_type == "document")
    print(f"Loaded:     {doc_count} document entries")

    # 3. Calculate pagination (two-pass); cover occupies pages 1..cover_count
    numbered, missing = calculate_pagination(entries, docs_dir, strict=False, cover_pages=cover_count)
    if missing:
        for path in missing:
            print(f"WARNING:    file not found, treated as placeholder — {Path(path).name}")
    real = sum(1 for e in numbered if e.entry_type == "document" and e.page_number is not None)
    phld = sum(1 for e in numbered if e.entry_type == "document" and e.page_number is None)
    print(f"Paginated:  {real} documents, {phld} placeholder(s)")

    # 4. Generate index PDF
    index_pages, index_links = generate_index(numbered, index_path)
    print(f"Index:      {index_path}  ({index_pages} page{'s' if index_pages != 1 else ''},"
          f" {len(index_links)} link(s))")

    # 5. Merge + stamp + bookmarks + hyperlinks (cover = page 1, index = page 2+)
    total_pages = build_bundle(
        numbered, docs_dir, index_path, index_links, bundle_path,
        cover_path=cover_path,
    )
    size_mb = bundle_path.stat().st_size / 1_048_576
    print(f"Bundle:     {bundle_path}  ({total_pages} pages, {size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
