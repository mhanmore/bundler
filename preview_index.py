#!/usr/bin/env python3
"""
Preview script: reads templates/sequence_template.csv, runs the real pagination
calculator against the sample documents, and renders preview_index.pdf.

Usage:
    .venv/bin/python preview_index.py [--docs-dir PATH]

Defaults to ~/Downloads/MH Sandbox as the documents directory.
"""

import argparse
import csv
import logging
from pathlib import Path

# pypdf emits noisy "Ignoring wrong pointing object" warnings on malformed PDFs;
# these are harmless for page counting so suppress them in the preview.
logging.getLogger("pypdf").setLevel(logging.ERROR)

from bundler.index import generate_index
from bundler.models import TOCEntry
from bundler.paginator import calculate_pagination

CSV_PATH  = Path("templates/sequence_template.csv")
OUT_PATH  = Path("preview_index.pdf")
DOCS_DEFAULT = Path.home() / "Downloads" / "MH Sandbox"


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
    parser.add_argument("--docs-dir", type=Path, default=DOCS_DEFAULT,
                        help="Directory containing source PDFs")
    args = parser.parse_args()

    docs_dir: Path = args.docs_dir
    print(f"Documents: {docs_dir}")

    entries = load_entries_from_csv(CSV_PATH)
    print(f"CSV rows:  {len(entries)} entries loaded from {CSV_PATH}")

    numbered, missing = calculate_pagination(entries, docs_dir, strict=False)
    if missing:
        for path in missing:
            print(f"WARNING: file not found, treated as placeholder: {path}")

    pages, _ = generate_index(numbered, OUT_PATH)

    real = sum(1 for e in numbered if e.entry_type == "document" and e.page_number is not None)
    phld = sum(1 for e in numbered if e.entry_type == "document" and e.page_number is None)
    print(f"Paginated: {real} documents, {phld} placeholder(s)")
    print(f"Written:   {OUT_PATH}  ({pages} page{'s' if pages != 1 else ''})")


if __name__ == "__main__":
    main()
