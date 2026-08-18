"""
ReportLab index (table of contents) generator for UK court bundles.

Visual spec
-----------
- A4 portrait, Times-Roman throughout
- Page 1 header: "INDEX" centred (14 pt bold), "Page No." right-aligned (10 pt)
- Section headings: 11 pt bold, all-caps, flush left, extra space above
- Document entries: 10 pt regular, indented 1 cm, dotted leader, right-aligned page number
- Dots: evenly spaced, filling the gap between title end and page number
- Long titles wrap; dots and page number appear only on the final line

generate_index() is the public entry point. Returns (page_count, index_links) where
index_links records the bounding rect of each document entry so the merger can add
hyperlink annotations to the finished bundle.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from reportlab.lib.colors import black, HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from bundler.models import TOCEntry


# ── Page geometry ──────────────────────────────────────────────────────────────
PAGE_W, PAGE_H = A4          # 595.28 × 841.89 pt
MARGIN_L = 2.5 * cm         # 70.87 pt
MARGIN_R = 2.5 * cm
MARGIN_T = 2.5 * cm
MARGIN_B = 2.5 * cm

CONTENT_L = MARGIN_L
CONTENT_R = PAGE_W - MARGIN_R   # 524.41 pt

DOC_INDENT = 1.0 * cm          # document entries indented relative to section headings

# ── Typography ─────────────────────────────────────────────────────────────────
FONT_REGULAR = "Times-Roman"
FONT_BOLD    = "Times-Bold"

SIZE_TITLE   = 14   # pt  "INDEX"
SIZE_SECTION = 11   # pt  section headings
SIZE_HEADING = 10   # pt  sub-headings within a section
SIZE_ENTRY   = 10   # pt  document entries

# ── Vertical spacing (points) ──────────────────────────────────────────────────
LEAD_TITLE        = 22   # space below "INDEX" heading
LEAD_HEADER_GAP   = 10   # space below "Page No." line before first entry
LEAD_SECTION      = 16   # line height for a section heading line
LEAD_HEADING      = 14   # line height for a sub-heading line
LEAD_ENTRY        = 14   # line height for a document entry line
GAP_BEFORE_SECTION = 10  # extra whitespace above each section heading
GAP_BEFORE_HEADING =  6  # extra whitespace above each sub-heading

# ── Tramlines (INDEX heading) ───────────────────────────────────────────────────
TRAMLINE_W     = 220  # pt — width of horizontal rules flanking "INDEX"
TRAMLINE_V_PAD = 10   # pt — gap between rule and top/bottom of text

# ── Dot leader ─────────────────────────────────────────────────────────────────
DOT_GAP = 4     # pt gap: title-end→first-dot and last-dot→page-number
MIN_DOTS = 3    # minimum number of dots; skip leader if space is too tight


# ── Link record ────────────────────────────────────────────────────────────────

@dataclass
class IndexLink:
    """
    Records the position of one document entry in the rendered index PDF so
    the merger can add a hyperlink annotation pointing to that document's page
    in the final merged bundle.
    """
    dest_name: str                          # identifies the target document
    target_page: int                        # 1-indexed page in the merged bundle
    index_page_idx: int                     # 0-indexed page within the index PDF
    rect: tuple[float, float, float, float] # (x1, y1, x2, y2) in PDF coordinates


class _IndexCanvas:
    """Stateful canvas wrapper that draws TOC entries and manages page breaks."""

    def __init__(self, output_path: Path) -> None:
        self._c = canvas.Canvas(str(output_path), pagesize=A4)
        self._page = 0
        self._y: float = 0.0
        self._links: list[IndexLink] = []
        self._new_page()

    # ── Page management ────────────────────────────────────────────────────────

    def _new_page(self) -> None:
        if self._page > 0:
            self._c.showPage()
        self._page += 1
        self._y = PAGE_H - MARGIN_T
        if self._page == 1:
            self._draw_first_header()

    def _draw_first_header(self) -> None:
        c = self._c
        cx = PAGE_W / 2
        tx0 = cx - TRAMLINE_W / 2
        tx1 = cx + TRAMLINE_W / 2

        # Top rule
        c.setLineWidth(0.75)
        c.line(tx0, self._y, tx1, self._y)

        # "INDEX" baseline sits below the top rule by the cap height + padding
        text_y = self._y - SIZE_TITLE * 0.662 - TRAMLINE_V_PAD
        c.setFont(FONT_BOLD, SIZE_TITLE)
        c.drawCentredString(cx, text_y, "INDEX")

        # Bottom rule sits below the descender + padding
        box_bottom = text_y - SIZE_TITLE * 0.217 - TRAMLINE_V_PAD
        c.line(tx0, box_bottom, tx1, box_bottom)

        self._y = box_bottom - LEAD_TITLE  # gap after tramline box

        # "Page No." right-aligned
        c.setFont(FONT_REGULAR, SIZE_ENTRY)
        c.drawRightString(CONTENT_R, self._y, "Page No.")
        self._y -= (LEAD_ENTRY + LEAD_HEADER_GAP)

    def _ensure(self, height_needed: float) -> None:
        """Open a new page if there is insufficient space for *height_needed* points."""
        if self._y - height_needed < MARGIN_B:
            self._new_page()

    # ── Measurement helpers ────────────────────────────────────────────────────

    @staticmethod
    def _sw(text: str, font: str, size: float) -> float:
        return pdfmetrics.stringWidth(text, font, size)

    # ── Dot leader ─────────────────────────────────────────────────────────────

    def _dot_leader(self, y: float, x0: float, x1: float,
                    font: str, size: float) -> None:
        available = x1 - x0
        dot_w = self._sw(".", font, size)
        n = int(available / dot_w)
        if n < MIN_DOTS:
            return
        total_w = n * dot_w
        # Centre the dot run in the available space so gaps are equal on both sides
        offset = (available - total_w) / 2
        self._c.setFont(font, size)
        self._c.drawString(x0 + offset, y, "." * n)

    # ── Text wrapping ──────────────────────────────────────────────────────────

    def _wrap(self, text: str, font: str, size: float,
              full_w: float, last_w: float) -> list[str]:
        """
        Word-wrap *text* such that:
        - every line except the last fits within *full_w*,
        - the last line fits within *last_w* (reserving room for dots + page number).
        """
        words = text.split()
        if not words:
            return [""]

        lines: list[str] = []
        cur: list[str] = []

        for word in words:
            candidate = " ".join(cur + [word])
            if self._sw(candidate, font, size) <= full_w:
                cur.append(word)
            else:
                if cur:
                    lines.append(" ".join(cur))
                cur = [word]
        if cur:
            lines.append(" ".join(cur))

        # Ensure the last line fits within last_w.
        # If it doesn't, peel words off the end into a new (final) line.
        while lines and self._sw(lines[-1], font, size) > last_w:
            tail = lines[-1].split()
            if len(tail) == 1:
                break  # single oversized word — cannot split further
            lines[-1] = " ".join(tail[:-1])
            lines.append(tail[-1])

        return lines or [text]

    # ── Public drawing methods ─────────────────────────────────────────────────

    def section_heading(self, title: str) -> None:
        self._ensure(GAP_BEFORE_SECTION + LEAD_SECTION)
        self._y -= GAP_BEFORE_SECTION
        self._c.setFont(FONT_BOLD, SIZE_SECTION)
        self._c.drawString(CONTENT_L, self._y, title.upper())
        self._y -= LEAD_SECTION

    def heading(self, title: str) -> None:
        self._ensure(GAP_BEFORE_HEADING + LEAD_HEADING)
        self._y -= GAP_BEFORE_HEADING
        self._c.setFont(FONT_BOLD, SIZE_HEADING)
        self._c.drawString(CONTENT_L + DOC_INDENT, self._y, title)
        self._y -= LEAD_HEADING

    def document_entry(self, title: str, page_number: Optional[int],
                       dest_name: Optional[str] = None,
                       doc_number: Optional[int] = None) -> None:
        font = FONT_REGULAR
        size = SIZE_ENTRY
        x_title = CONTENT_L + DOC_INDENT
        placeholder = page_number is None

        page_str = "—" if placeholder else str(page_number)
        pn_w = self._sw(page_str, font, size)

        if placeholder:
            # No dot leader for placeholders — wrap title across full content width
            full_line_max = CONTENT_R - x_title
            lines = self._wrap(title, font, size, full_line_max, full_line_max)
        else:
            # Reserve space for dots + page number on the final line
            min_dot_run = self._sw("." * MIN_DOTS, font, size)
            last_line_max = (CONTENT_R - x_title
                             - DOT_GAP * 2 - min_dot_run
                             - pn_w)
            full_line_max = CONTENT_R - x_title
            lines = self._wrap(title, font, size, full_line_max, last_line_max)

        self._ensure(len(lines) * LEAD_ENTRY)

        # Capture position AFTER _ensure so we have the correct page and y
        y_top_baseline = self._y
        current_page_idx = self._page - 1  # 0-indexed

        c = self._c

        if placeholder:
            n = len(lines)
            rect_top = y_top_baseline + size * 0.85
            rect_bottom = y_top_baseline - (n - 1) * LEAD_ENTRY - size * 0.3
            c.setFillColor(HexColor("#FFFF99"))
            c.rect(CONTENT_L, rect_bottom, CONTENT_R - CONTENT_L,
                   rect_top - rect_bottom, fill=1, stroke=0)
            c.setFillColor(black)

        c.setFont(font, size)

        # Document number in the left gutter
        if doc_number is not None:
            c.drawString(CONTENT_L, y_top_baseline, f"{doc_number}.")

        # Non-final lines: no leader, no page number
        for line in lines[:-1]:
            c.drawString(x_title, self._y, line)
            self._y -= LEAD_ENTRY

        # Final line
        final = lines[-1]
        final_w = self._sw(final, font, size)
        c.drawString(x_title, self._y, final)
        c.drawRightString(CONTENT_R, self._y, page_str)

        if not placeholder:
            dot_x0 = x_title + final_w + DOT_GAP
            dot_x1 = CONTENT_R - pn_w - DOT_GAP
            self._dot_leader(self._y, dot_x0, dot_x1, font, size)

        # Record link region for real entries that have a destination
        if not placeholder and dest_name:
            n = len(lines)
            rect = (
                CONTENT_L,
                y_top_baseline - (n - 1) * LEAD_ENTRY - size * 0.3,  # bottom
                CONTENT_R,
                y_top_baseline + size * 0.85,                          # top
            )
            self._links.append(IndexLink(
                dest_name=dest_name,
                target_page=page_number,       # type: ignore[arg-type]  # not None here
                index_page_idx=current_page_idx,
                rect=rect,
            ))

        self._y -= LEAD_ENTRY

    def save(self) -> tuple[int, list[IndexLink]]:
        """Save the PDF and return (page_count, index_links)."""
        self._c.save()
        return self._page, self._links


# ── Public API ─────────────────────────────────────────────────────────────────

def generate_index(
    entries: list[TOCEntry], output_path: Path
) -> tuple[int, list[IndexLink]]:
    """
    Render *entries* as an index PDF at *output_path*.

    Returns
    -------
    (page_count, index_links)
    page_count:   number of pages in the generated index (feeds pagination calculator).
    index_links:  bounding rects of each real document entry, for the merger to use
                  when adding hyperlink annotations to the finished bundle.
    """
    ic = _IndexCanvas(output_path)
    doc_counter = 0

    for entry in entries:
        if entry.entry_type == "section_heading":
            ic.section_heading(entry.title)
        elif entry.entry_type == "heading":
            ic.heading(entry.title)
        elif entry.entry_type == "document":
            doc_counter += 1
            ic.document_entry(entry.title, entry.page_number, entry.dest_name,
                              doc_number=doc_counter)
        else:
            raise ValueError(f"Unknown entry_type: {entry.entry_type!r}")

    return ic.save()
