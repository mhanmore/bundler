"""
Pagination calculator for the bundle builder.

Workflow
--------
1. Count pages in each source PDF (pypdf — no merging required).
2. Render a first-pass index to a temp file to measure how many pages the index occupies.
3. Compute page offsets: index occupies pages 1..N, documents follow sequentially.
4. If the index page count changed from the estimate (rare — only happens when a
   page-number crossing a digit boundary pushes a title onto a new line), re-render once.
5. Return the TOCEntry list with page_number set on every real document entry.
   Placeholder entries (file_name is None or empty) keep page_number=None and are
   shown in the index as "—" but excluded from the merged bundle.

Public API
----------
    count_pages(pdf_path)               → int
    calculate_pagination(entries, docs_dir) → list[TOCEntry]
"""

from __future__ import annotations

import dataclasses
import tempfile
from pathlib import Path

from pypdf import PdfReader

from bundler.index import generate_index
from bundler.models import TOCEntry


def count_pages(pdf_path: Path) -> int:
    """Return the page count of a PDF without loading the full document into memory."""
    reader = PdfReader(str(pdf_path), strict=False)
    return len(reader.pages)


def _collect_page_counts(
    entries: list[TOCEntry], docs_dir: Path, strict: bool = True
) -> tuple[dict[str, int], list[str]]:
    """
    Open every source PDF referenced in *entries* and count its pages.

    Returns
    -------
    counts:  file_name → page_count for every file that exists.
    missing: list of file paths that could not be found.

    When strict=True the caller should raise on a non-empty missing list.
    When strict=False missing files are silently treated as placeholders.
    """
    missing: list[str] = []
    counts: dict[str, int] = {}

    for entry in entries:
        if entry.entry_type != "document" or not entry.file_name:
            continue
        pdf_path = docs_dir / entry.file_name
        if not pdf_path.exists():
            missing.append(str(pdf_path))
        else:
            counts[entry.file_name] = count_pages(pdf_path)

    return counts, missing


def _assign_page_numbers(
    entries: list[TOCEntry],
    page_counts: dict[str, int],
    index_pages: int,
    cover_pages: int = 0,
) -> list[TOCEntry]:
    """
    Return a new list of TOCEntries with page_number set for every real document.

    Documents start at page cover_pages + index_pages + 1 and are allocated
    contiguous pages based on their page_counts entry. Placeholder entries (no
    file_name) keep page_number=None.
    """
    result: list[TOCEntry] = []
    cursor = cover_pages + index_pages + 1

    for entry in entries:
        if entry.entry_type in ("section_heading", "heading"):
            result.append(entry)
        elif entry.entry_type == "document":
            if entry.file_name and entry.file_name in page_counts:
                result.append(dataclasses.replace(entry, page_number=cursor))
                cursor += page_counts[entry.file_name]
            elif entry.file_name:
                # Non-empty file_name but file is missing — auto-mark as placeholder
                result.append(dataclasses.replace(
                    entry, page_number=None, title=entry.title + " [FILE NOT FOUND]"
                ))
            else:
                # Intentionally blank file_name
                result.append(dataclasses.replace(entry, page_number=None))

    return result


def calculate_pagination(
    entries: list[TOCEntry],
    docs_dir: Path,
    strict: bool = True,
    cover_pages: int = 0,
) -> tuple[list[TOCEntry], list[str]]:
    """
    Count pages in all source PDFs and assign page_number to each document entry.

    Uses a two-pass index render so that the index's own page count is accounted
    for correctly in the page offsets.

    Parameters
    ----------
    entries:   TOCEntry list from the CSV parser, with file_name populated.
    docs_dir:  Directory containing the source PDF files.
    strict:    If True (default), raise FileNotFoundError on any missing file.
               If False, treat missing files as placeholders and return their
               paths in the second element of the return tuple.

    Returns
    -------
    (numbered_entries, missing_files)
    numbered_entries: TOCEntries with page_number set on all located documents.
    missing_files:    Paths of files that could not be found (empty when strict=True).

    Raises
    ------
    FileNotFoundError  if strict=True and any non-placeholder file is missing.
    """
    page_counts, missing = _collect_page_counts(entries, docs_dir)

    if strict and missing:
        files = "\n".join(f"  {p}" for p in missing)
        raise FileNotFoundError(f"Source PDFs not found:\n{files}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_index = Path(tmp) / "index.pdf"
        estimated_index_pages = 1  # conservative starting estimate

        for _ in range(2):  # at most 2 passes
            numbered = _assign_page_numbers(entries, page_counts, estimated_index_pages, cover_pages)
            actual_index_pages, _ = generate_index(numbered, tmp_index)

            if actual_index_pages == estimated_index_pages:
                break  # stable — offsets are correct

            estimated_index_pages = actual_index_pages  # retry with corrected estimate

    return numbered, missing
