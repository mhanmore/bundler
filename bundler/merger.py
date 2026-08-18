"""
PDF merger for the bundle builder.

Workflow
--------
1. Append the pre-generated index PDF.
2. Append each real source document PDF in sequence order (placeholders skipped).
3. Stamp sequential page numbers onto every page.
4. Clear inherited outlines from source documents, then add our clean nested outline
   (Index → sections → documents) with 100% zoom destinations.
5. Add named destinations for each document (belt-and-braces navigation).
6. Add invisible GoTo link annotations to index entries at 100% zoom.
7. Set OpenAction to open at 100% zoom on page 1.
8. Write output.

Public API
----------
    build_bundle(entries, docs_dir, index_path, index_links, output_path) → int
        Returns the total page count of the output bundle.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject, DecodedStreamObject, DictionaryObject, Fit,
    FloatObject, NameObject, NullObject, NumberObject,
)

from bundler.index import IndexLink
from bundler.models import TOCEntry

log = logging.getLogger(__name__)

# 100% zoom destination — used for all navigation targets
FIT_100 = Fit.xyz(left=None, top=None, zoom=1.0)

# ── Page-number stamp typography ───────────────────────────────────────────────
STAMP_FONT        = "Times-Roman"
STAMP_SIZE        = 11    # pt
STAMP_MARGIN_R    = 20    # pt from right edge of page
STAMP_MARGIN_B    = 15    # pt from bottom edge of page
STAMP_PAD_X       = 4     # pt horizontal padding inside white background box
STAMP_PAD_Y       = 3     # pt vertical padding inside white background box
# Use a light gray opaque knockout box for cross-viewer compatibility.
# Some viewers ignore transparency in merged overlay content streams.
STAMP_BG_GRAY     = 0.90  # 1.0=white, 0.0=black


# ── Internal helpers ───────────────────────────────────────────────────────────

def _normalize_page_rotation(page, page_num: int) -> None:
    """
    If a page has a non-zero /Rotate, transfer that rotation into page content
    and page boxes, then clear /Rotate.
    """
    rot = int(page.get("/Rotate", 0)) % 360
    if rot == 0:
        return
    log.debug("Normalizing page %d rotation: /Rotate=%d", page_num, rot)
    page.transfer_rotation_to_content()


def _stamp_stream_bytes(page_number: int, width: float, height: float) -> bytes:
    """
    Return raw PDF content stream operators for a page number stamp at the
    visual bottom-right.  Font name /BndlPgNum must be in the page resources.

    Callers must normalize /Rotate first (see _normalize_page_rotation), so
    placement is in unrotated MediaBox coordinates.
    """
    from reportlab.pdfbase import pdfmetrics

    text = str(page_number)
    text_w = pdfmetrics.stringWidth(text, STAMP_FONT, STAMP_SIZE)

    mr, mb   = STAMP_MARGIN_R, STAMP_MARGIN_B
    pad_x, pad_y = STAMP_PAD_X, STAMP_PAD_Y
    tx = width  - mr          # right anchor x
    ty = mb                   # bottom anchor y
    bg = STAMP_BG_GRAY

    # Box coordinates
    box_x = tx - text_w - pad_x
    box_y = ty - pad_y
    box_w = text_w + pad_x * 2
    box_h = STAMP_SIZE + pad_y * 2

    # Text origin: right-align at tx by shifting left by text_w
    text_x = tx - text_w
    text_y = ty

    lines = [
        b"q",
        f"{bg:.3f} g".encode(),
        f"{box_x:.3f} {box_y:.3f} {box_w:.3f} {box_h:.3f} re f".encode(),
        b"0 g",
        b"BT",
        f"/BndlPgNum {STAMP_SIZE} Tf".encode(),
        f"{text_x:.3f} {text_y:.3f} Td".encode(),
        f"({text}) Tj".encode(),
        b"ET",
        b"Q",
    ]
    return b"\n".join(lines)


def _apply_stamp(writer: PdfWriter, page, stamp_font_ref, page_number: int) -> None:
    """
    Stamp a page number onto a page without decoding its content stream.

    Source PDFs may apply top-level (outside any q/Q) cm transforms — common in
    scanned documents that use a coordinate-system flip.  If we simply append our
    stamp stream those transforms are still active and our coordinates are wrong.

    Fix: wrap the entire source content in an outer q … Q by inserting a tiny
    preamble stream containing just "q".  The stamp stream then begins with "Q"
    (which restores the clean initial graphics state) before drawing.  The logical
    concatenation becomes:

        q  [source content]  Q  q  [stamp operators]  Q

    The source's top-level state changes are isolated inside the outer q/Q pair
    and our stamp always runs at the page's default (identity) coordinate system.
    """
    w = float(page.mediabox.width)
    h = float(page.mediabox.height)

    # Preamble: save graphics state so source content is fully isolated
    preamble_obj = DecodedStreamObject()
    preamble_obj.set_data(b"q")
    preamble_ref = writer._add_object(preamble_obj.flate_encode())

    # Stamp stream: restore state (cleans up anything source left at top level)
    # then draw the stamp in the default page coordinate system.
    stamp_data = b"Q\n" + _stamp_stream_bytes(page_number, w, h)
    stamp_obj = DecodedStreamObject()
    stamp_obj.set_data(stamp_data)
    stamp_ref = writer._add_object(stamp_obj.flate_encode())

    # Ensure /Resources > /Font exists and contains our font.
    # Both /Resources and /Font may be stored as indirect references.
    res = page.get("/Resources")
    if res is None:
        res = DictionaryObject()
        page[NameObject("/Resources")] = res
    else:
        res = res.get_object() if hasattr(res, "get_object") else res
    fonts = res.get("/Font")
    if fonts is None:
        fonts = DictionaryObject()
        res[NameObject("/Font")] = fonts
    else:
        fonts = fonts.get_object() if hasattr(fonts, "get_object") else fonts
    fonts[NameObject("/BndlPgNum")] = stamp_font_ref

    # Build new /Contents: [preamble, *original_contents, stamp]
    existing = page.raw_get("/Contents")
    if isinstance(existing, ArrayObject):
        new_contents = ArrayObject([preamble_ref, *existing, stamp_ref])
    else:
        new_contents = ArrayObject([preamble_ref, existing, stamp_ref])
    page[NameObject("/Contents")] = new_contents


def _set_open_at_100_percent(writer: PdfWriter) -> None:
    """Set OpenAction to open at 100% zoom on the first page."""
    if not writer.pages:
        return
    first_page_ref = writer.pages[0].indirect_reference
    if first_page_ref is None:
        return
    writer._root_object.update({
        NameObject("/OpenAction"): ArrayObject([
            first_page_ref,
            NameObject("/XYZ"),
            NullObject(),       # left — inherit
            NullObject(),       # top  — inherit
            FloatObject(1.0),   # zoom = 100%
        ])
    })


def _clear_inherited_outlines(writer: PdfWriter) -> None:
    """
    Remove outline entries inherited from source documents when they were appended.
    Source PDFs often have their own bookmarks which appear in the panel alongside
    our bundle outline and make navigation confusing. Clearing here lets us install
    a single clean hierarchy.
    """
    if "/Outlines" in writer._root_object:
        del writer._root_object[NameObject("/Outlines")]


def _add_outline(
    writer: PdfWriter, entries: list[TOCEntry], page_offset: int = 0
) -> None:
    """
    Add a clean nested PDF outline at 100% zoom:
      Index                    → page 1  (100% zoom)
      ├── SECTION HEADING      → first real document page in section
      │   ├── Document title   → document start page  (100% zoom)
      │   └── ...
      └── ...

    *page_offset* accounts for any pages prepended before the index (e.g. a cover).
    Section entries are created lazily on the first real document in that section.
    Placeholder entries (page_number=None) are omitted.
    """
    writer.add_outline_item("Index", page_offset, fit=FIT_100)

    section_ref = None
    pending_section: str | None = None
    doc_counter = 0

    for entry in entries:
        if entry.entry_type == "section_heading":
            pending_section = entry.title
            section_ref = None

        elif entry.entry_type == "document":
            doc_counter += 1
            if entry.page_number is None:
                continue  # placeholder — keep counter in sync but skip outline item

            page_idx = entry.page_number - 1  # page_number already includes cover offset

            if section_ref is None and pending_section is not None:
                section_ref = writer.add_outline_item(
                    pending_section, page_idx, fit=FIT_100
                )

            writer.add_outline_item(
                f"{doc_counter}. {entry.title}", page_idx, parent=section_ref, fit=FIT_100
            )


def _add_named_destinations(
    writer: PdfWriter, entries: list[TOCEntry], page_offset: int = 0
) -> None:
    """
    Add a named destination for each real document entry.

    Named destinations allow navigation independent of the outline panel — some
    PDF viewers and court systems use /Dests by name rather than outline items.
    Each destination is registered under the entry's dest_name (e.g. "doc_3").
    *page_offset* accounts for any pages prepended before the index (e.g. a cover).
    """
    for entry in entries:
        if entry.entry_type != "document":
            continue
        if not entry.dest_name or entry.page_number is None:
            continue
        # add_named_destination takes a 0-indexed page number
        writer.add_named_destination(entry.dest_name, entry.page_number - 1)  # page_number already includes cover offset


def _add_index_links(
    writer: PdfWriter, index_links: list[IndexLink], page_offset: int = 0
) -> None:
    """
    Add invisible GoTo link annotations to the index pages at 100% zoom so that
    clicking an entry jumps to the first page of that document at exactly 100%.
    *page_offset* accounts for any pages prepended before the index (e.g. a cover).
    """
    for link in index_links:
        to_page_idx = link.target_page - 1  # target_page already includes cover offset
        if to_page_idx < 0 or to_page_idx >= len(writer.pages):
            log.warning("Link target page %d out of range, skipping", link.target_page)
            continue

        to_page_ref = writer.pages[to_page_idx].indirect_reference
        if to_page_ref is None:
            continue

        x1, y1, x2, y2 = link.rect
        annot = writer._add_object(DictionaryObject({
            NameObject("/Type"):    NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Link"),
            NameObject("/Rect"): ArrayObject([
                FloatObject(x1), FloatObject(y1),
                FloatObject(x2), FloatObject(y2),
            ]),
            NameObject("/Border"): ArrayObject([
                NumberObject(0), NumberObject(0), NumberObject(0),
            ]),
            NameObject("/Dest"): ArrayObject([
                to_page_ref,
                NameObject("/XYZ"),
                NullObject(),       # left  — inherit position
                NullObject(),       # top   — inherit position
                FloatObject(1.0),   # zoom  = 100%
            ]),
        }))

        from_page = writer.pages[page_offset + link.index_page_idx]
        if "/Annots" in from_page:
            from_page[NameObject("/Annots")].append(annot)
        else:
            from_page[NameObject("/Annots")] = ArrayObject([annot])


# ── Public API ─────────────────────────────────────────────────────────────────

def stamp_pdf(src_path: Path, dst_path: Path, start_page: int) -> None:
    """
    Stamp sequential page numbers onto a standalone PDF.

    Each page receives the number *start_page + page_index*, matching the
    position that page would occupy in the compiled bundle.

    Parameters
    ----------
    src_path:   Source PDF to stamp.
    dst_path:   Destination for the stamped PDF (may equal src_path).
    start_page: Bundle page number of the first page in this document.
    """
    writer = PdfWriter()
    writer.append(str(src_path))

    stamp_font_ref = writer._add_object(DictionaryObject({
        NameObject("/Type"):     NameObject("/Font"),
        NameObject("/Subtype"):  NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Times-Roman"),
        NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
    }))

    for i, page in enumerate(writer.pages):
        page_num = start_page + i
        _normalize_page_rotation(page, page_num)
        _apply_stamp(writer, page, stamp_font_ref, page_num)

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    with dst_path.open("wb") as f:
        writer.write(f)


def build_bundle(
    entries: list[TOCEntry],
    docs_dir: Path,
    index_path: Path,
    index_links: list[IndexLink],
    output_path: Path,
    cover_path: Path | None = None,
) -> int:
    """
    Merge the index PDF with source documents, stamp page numbers, install a
    clean outline and named destinations, add index hyperlinks, and write output.

    Parameters
    ----------
    entries:      Numbered TOCEntries from calculate_pagination().
    docs_dir:     Directory containing source PDFs.
    index_path:   Pre-generated index PDF (from generate_index()).
    index_links:  Entry positions from generate_index(), for hyperlink annotations.
    output_path:  Destination path for the merged bundle PDF.
    cover_path:   Optional pre-generated cover PDF prepended as the first page(s).
                  Cover pages are stamped starting at page 1.

    Returns
    -------
    Total page count of the output bundle.
    """
    writer = PdfWriter()

    # ── 0. Prepend cover (if provided) — not stamped ───────────────────────────
    if cover_path is not None:
        writer.append(str(cover_path))
    cover_count = len(writer.pages)  # 0 when no cover, 1 when cover present

    # ── 1. Append index ────────────────────────────────────────────────────────
    writer.append(str(index_path))

    # ── 2. Append source documents in sequence order ───────────────────────────
    for entry in entries:
        if entry.entry_type != "document":
            continue
        if not entry.file_name or entry.page_number is None:
            log.debug("Skipped placeholder: %s", entry.title)
            continue
        writer.append(str(docs_dir / entry.file_name))

    # ── 3. Normalize page rotations, then stamp sequential page numbers ───────
    # Every page is stamped starting at 1 (cover = page 1, index = page 2, ...).
    # The stamp font is added once to the writer and shared across all pages.
    stamp_font_ref = writer._add_object(DictionaryObject({
        NameObject("/Type"):     NameObject("/Font"),
        NameObject("/Subtype"):  NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Times-Roman"),
        NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
    }))
    for i, page in enumerate(writer.pages):
        page_num = i + 1
        _normalize_page_rotation(page, page_num)
        _apply_stamp(writer, page, stamp_font_ref, page_num)

    # ── 4. Clear inherited outlines, install clean bundle outline ─────────────
    _clear_inherited_outlines(writer)
    _add_outline(writer, entries, page_offset=cover_count)

    # ── 5. Named destinations (belt-and-braces) ───────────────────────────────
    _add_named_destinations(writer, entries, page_offset=cover_count)

    # ── 6. Index hyperlink annotations at 100% zoom ───────────────────────────
    _add_index_links(writer, index_links, page_offset=cover_count)

    # ── 7. OpenAction: open at 100% zoom ──────────────────────────────────────
    _set_open_at_100_percent(writer)

    # ── 8. Write output ───────────────────────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as f:
        writer.write(f)

    total = len(writer.pages)
    log.info("Bundle written: %s (%d pages)", output_path, total)
    return total
