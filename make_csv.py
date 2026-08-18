#!/usr/bin/env python3
"""
make_csv.py — Scaffold a _sequence.csv from a folder tree.

Folder layout (1 or 2 levels of folders, then PDF files):

    root/
        [01 ]Section Name/
            file.pdf
            [02 ]Sub Heading/
                file.pdf

Usage:
    .venv/bin/python make_csv.py <source-folder> [--output PATH]

    Omit --output to print to stdout.

Rules
-----
- Top-level subdirectories → section_heading rows
- Second-level subdirectories → heading rows
- PDF files (any case) → document rows; non-PDF files are skipped with a warning
- Folder ordering: numeric prefix (leading digits) if present, else alphabetical
- File ordering within a folder: numeric prefix if any file has one, else file
  creation date (macOS st_birthtime, falling back to mtime)
- Numeric prefixes are stripped from titles but drive sort order
- Double extensions like "foo.pdf.PDF" are collapsed to "foo"
- Titles are derived from filenames (prefix stripped, extension removed); edit
  the output CSV before use
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import re
import sys
from pathlib import Path


# ── Helpers ────────────────────────────────────────────────────────────────────

_NUM_RE = re.compile(r"^(\d+)[.\-_ ]+")


def _numeric_prefix(name: str) -> int | None:
    m = _NUM_RE.match(name)
    return int(m.group(1)) if m else None


def _strip_numeric_prefix(name: str) -> str:
    return _NUM_RE.sub("", name).strip()


def _clean_title(name: str, *, is_dir: bool) -> str:
    """Strip numeric prefix and (for files) collapse all PDF-like extensions."""
    t = _strip_numeric_prefix(name)
    if not is_dir:
        # Collapse double/triple extensions: "foo.pdf.PDF" → "foo"
        p = Path(t)
        while p.suffix.lower() == ".pdf":
            p = p.with_suffix("")
        t = p.name
    return t.strip()


def _creation_time(path: Path) -> float:
    st = os.stat(path)
    return getattr(st, "st_birthtime", st.st_mtime)


def _sort_dirs(dirs: list[Path]) -> list[Path]:
    """Sort folders: numeric prefix first, then alphabetical."""
    has_numbers = any(_numeric_prefix(d.name) is not None for d in dirs)
    if has_numbers:
        return sorted(dirs, key=lambda d: (
            _numeric_prefix(d.name) if _numeric_prefix(d.name) is not None else 9999,
            d.name,
        ))
    return sorted(dirs, key=lambda d: d.name)


def _sort_files(files: list[Path]) -> list[Path]:
    """Sort files: numeric prefix if any has one, else creation date."""
    has_numbers = any(_numeric_prefix(f.name) is not None for f in files)
    if has_numbers:
        return sorted(files, key=lambda f: (
            _numeric_prefix(f.name) if _numeric_prefix(f.name) is not None else 9999,
            f.name,
        ))
    return sorted(files, key=_creation_time)


def _sort_mixed(items: list[Path]) -> list[Path]:
    """
    Sort a mix of files and sub-dirs within a section.

    If any item (file or dir) has a numeric prefix, use that for ordering.
    Otherwise sort files by creation date and dirs alphabetically, interleaved
    by their natural filesystem position isn't possible — so fall back to
    alphabetical for everything.
    """
    has_numbers = any(_numeric_prefix(p.name) is not None for p in items)
    if has_numbers:
        return sorted(items, key=lambda p: (
            _numeric_prefix(p.name) if _numeric_prefix(p.name) is not None else 9999,
            p.name,
        ))
    # No numbers: dirs alphabetically, files by creation date.
    # Keep them interleaved alphabetically by name as best approximation.
    dirs  = sorted([p for p in items if p.is_dir()],  key=lambda p: p.name)
    files = _sort_files([p for p in items if p.is_file()])
    # Merge: dirs first, then files — cleaner output when there are no numbers.
    return dirs + files


def _pdfs_and_others(folder: Path) -> tuple[list[Path], list[Path], list[Path]]:
    """Return (subdirs, pdf_files, skipped_files) — hidden items excluded."""
    subdirs, pdfs, skipped = [], [], []
    for p in sorted(folder.iterdir(), key=lambda x: x.name):
        if p.name.startswith("."):
            continue
        if p.is_dir():
            subdirs.append(p)
        elif p.is_file():
            if p.suffix.lower() == ".pdf":
                pdfs.append(p)
            else:
                skipped.append(p)
    return subdirs, pdfs, skipped


# ── Row builder ────────────────────────────────────────────────────────────────

def build_rows(root: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    warnings: list[str] = []

    top_dirs, top_pdfs, top_skipped = _pdfs_and_others(root)

    for f in top_pdfs:
        warnings.append(f"PDF at root level (not included): {f.name}")
    for f in top_skipped:
        warnings.append(f"Non-PDF skipped: {f.relative_to(root)}")

    for section_dir in _sort_dirs(top_dirs):
        section_title = _clean_title(section_dir.name, is_dir=True)
        section_col   = section_title

        rows.append({
            "section":    section_col,
            "entry_type": "section_heading",
            "title":      section_title.upper(),
            "file_name":  "",
        })

        sub_dirs, sec_pdfs, sec_skipped = _pdfs_and_others(section_dir)
        for f in sec_skipped:
            warnings.append(f"Non-PDF skipped: {f.relative_to(root)}")

        all_items: list[Path] = sub_dirs + sec_pdfs
        ordered = _sort_mixed(all_items)

        for item in ordered:
            if item.is_dir():
                heading_title = _clean_title(item.name, is_dir=True)
                rows.append({
                    "section":    section_col,
                    "entry_type": "heading",
                    "title":      heading_title,
                    "file_name":  "",
                })
                _, h_pdfs, h_skipped = _pdfs_and_others(item)
                for f in h_skipped:
                    warnings.append(f"Non-PDF skipped: {f.relative_to(root)}")
                for pdf in _sort_files(h_pdfs):
                    rows.append({
                        "section":    section_col,
                        "entry_type": "document",
                        "title":      _clean_title(pdf.name, is_dir=False),
                        "file_name":  str(pdf.relative_to(root)),
                    })
            else:
                # PDF file directly in the section
                rows.append({
                    "section":    section_col,
                    "entry_type": "document",
                    "title":      _clean_title(item.name, is_dir=False),
                    "file_name":  str(item.relative_to(root)),
                })

    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr)

    return rows


# ── Main ───────────────────────────────────────────────────────────────────────

def write_csv(rows: list[dict[str, str]], out: io.TextIOBase) -> None:
    writer = csv.DictWriter(
        out,
        fieldnames=["section", "entry_type", "title", "file_name"],
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scaffold _sequence.csv from a section/heading/document folder tree."
    )
    parser.add_argument("source", type=Path, help="Root folder to scan")
    parser.add_argument(
        "--output", "-o", type=Path, default=None,
        help="Output CSV path (default: print to stdout)",
    )
    args = parser.parse_args()

    root: Path = args.source.resolve()
    if not root.is_dir():
        sys.exit(f"ERROR: not a directory: {root}")

    rows = build_rows(root)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", newline="", encoding="utf-8") as f:
            write_csv(rows, f)
        print(f"Written: {args.output}  ({len(rows)} rows)", file=sys.stderr)
    else:
        write_csv(rows, sys.stdout)


if __name__ == "__main__":
    main()
