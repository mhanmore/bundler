"""
Cover page generator for UK legal bundles.

Two styles are supported, selected via [cover] style = "..." in the TOML:

  "court" (default)
    Standard Administrative Court bundle format:
      - Court header (left) with case reference (right)
      - Application description (centred, bold)
      - Parties block: BETWEEN / arbitrary parties / -and- separators
      - Bundle title between tramlines

  "statdec"
    Statutory declaration exhibits cover:
      - Matter reference and address lines (top-left, bold)
      - Declaration description (centred, bold) at ~55 % down the page
      - Bundle title between tramlines at ~40 % down the page

Public API
----------
    CaseMeta        — metadata for "court" style
    StatDecMeta     — metadata for "statdec" style
    load_case_meta  — load CaseMeta from a TOML file
    load_statdec_meta — load StatDecMeta from a TOML file
    generate_cover       — render "court" cover
    generate_statdec_cover — render "statdec" cover
    build_cover     — dispatcher: reads style from TOML, calls the right generator
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas


# ── Page geometry ───────────────────────────────────────────────────────────────
PAGE_W, PAGE_H = A4          # 595.28 × 841.89 pt
MARGIN_L = 2.5 * cm
MARGIN_R = 2.5 * cm
MARGIN_T = 2.5 * cm

CONTENT_L  = MARGIN_L
CONTENT_R  = PAGE_W - MARGIN_R
CONTENT_CX = PAGE_W / 2
CONTENT_W  = CONTENT_R - CONTENT_L

# ── Typography ──────────────────────────────────────────────────────────────────
FONT_REGULAR = "Times-Roman"
FONT_BOLD    = "Times-Bold"

SIZE_COVER        = 12   # pt — body text throughout the cover
SIZE_BUNDLE_TITLE = 14   # pt — "CLAIM BUNDLE" inside the tramline box

# ── Spacing ─────────────────────────────────────────────────────────────────────
COVER_LEAD = 16   # pt — standard line leading

# ── Tramlines ───────────────────────────────────────────────────────────────────
TRAMLINE_W     = 220  # pt — width of the horizontal rules
TRAMLINE_V_PAD = 10   # pt — gap between rule and top/bottom of text

# Vertical centre of the "CLAIM BUNDLE" tramline box — vertical page centre
BUNDLE_TITLE_CY = PAGE_H / 2


# ── Data models ─────────────────────────────────────────────────────────────────

@dataclass
class CaseMeta:
    """Metadata for the "court" cover style."""
    court_lines: list[str]            # e.g. ["IN THE HIGH COURT OF JUSTICE", ...]
    court_reference: str              # e.g. "AC-2026"
    application_description: str     # free text; wrapped automatically
    parties: list[tuple[str, str]]   # [(label, name), ...] in TOML order
    bundle_title: str                 # e.g. "CLAIM BUNDLE"


@dataclass
class StatDecMeta:
    """Metadata for the "statdec" cover style."""
    matter_lines: list[str]           # reference + address lines, top-left
    description: str                  # declaration description, centred; \n = forced break
    bundle_title: str                 # e.g. "EXHIBITS"


def _label(key: str) -> str:
    """Convert a TOML key to a display label: underscores → spaces, title-cased."""
    return key.replace("_", " ").title()


def load_case_meta(toml_path: Path) -> CaseMeta:
    """Load CaseMeta (court style) from a TOML file."""
    with toml_path.open("rb") as f:
        data = tomllib.load(f)
    parties = [(_label(k), v) for k, v in data["parties"].items()]
    return CaseMeta(
        court_lines=data["court"]["lines"],
        court_reference=data["court"]["reference"],
        application_description=data["application"]["description"],
        parties=parties,
        bundle_title=data["bundle"]["title"],
    )


def load_statdec_meta(toml_path: Path) -> StatDecMeta:
    """Load StatDecMeta (statdec style) from a TOML file."""
    with toml_path.open("rb") as f:
        data = tomllib.load(f)
    matter = data["matter"]
    matter_lines = [matter["reference"]] + matter.get("address_lines", [])
    return StatDecMeta(
        matter_lines=matter_lines,
        description=data["declaration"]["description"],
        bundle_title=data["bundle"]["title"],
    )


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _wrap(text: str, font: str, size: float, max_w: float) -> list[str]:
    """Word-wrap *text* so each line fits within *max_w* points."""
    words = text.split()
    lines: list[str] = []
    cur: list[str] = []
    for word in words:
        candidate = " ".join(cur + [word])
        if pdfmetrics.stringWidth(candidate, font, size) <= max_w:
            cur.append(word)
        else:
            if cur:
                lines.append(" ".join(cur))
            cur = [word]
    if cur:
        lines.append(" ".join(cur))
    return lines or [text]


def _tramlined_text(
    c: canvas.Canvas,
    text: str,
    cx: float,
    font: str,
    size: float,
    y_center: float,
    width: float = TRAMLINE_W,
) -> None:
    """Draw *text* centred at *cx* between two horizontal rules at *y_center*."""
    # half-height of the box: half a cap-height above + descender below + padding each side
    half = size / 2 + TRAMLINE_V_PAD
    x0 = cx - width / 2
    x1 = cx + width / 2

    c.setLineWidth(0.75)
    c.line(x0, y_center + half, x1, y_center + half)   # top rule
    c.setFont(font, size)
    c.drawCentredString(cx, y_center - size * 0.3, text)  # baseline slightly below centre
    c.line(x0, y_center - half, x1, y_center - half)   # bottom rule


# ── Public API ──────────────────────────────────────────────────────────────────

def generate_cover(meta: CaseMeta, output_path: Path) -> None:
    """Render a one-page A4 cover to *output_path*."""
    c = canvas.Canvas(str(output_path), pagesize=A4)
    y = PAGE_H - MARGIN_T

    # ── Court header ────────────────────────────────────────────────────────────
    c.setFont(FONT_BOLD, SIZE_COVER)
    c.drawString(CONTENT_L, y, meta.court_lines[0])
    c.drawRightString(CONTENT_R, y, meta.court_reference)
    y -= COVER_LEAD

    for line in meta.court_lines[1:]:
        c.drawString(CONTENT_L, y, line)
        y -= COVER_LEAD

    y -= 20  # extra gap after court block

    # ── Application description (centred, bold) ──────────────────────────────
    # Explicit \n in the toml value forces a line break; each segment is then
    # word-wrapped independently to fit the content width.
    for segment in meta.application_description.split("\n"):
        for line in _wrap(segment, FONT_BOLD, SIZE_COVER, CONTENT_W):
            c.setFont(FONT_BOLD, SIZE_COVER)
            c.drawCentredString(CONTENT_CX, y, line)
            y -= COVER_LEAD

    y -= 20  # extra gap

    # ── BETWEEN: ────────────────────────────────────────────────────────────────
    c.setFont(FONT_BOLD, SIZE_COVER)
    c.drawString(CONTENT_L, y, "BETWEEN:")
    y -= COVER_LEAD + 10

    # ── Parties (arbitrary, from TOML) ──────────────────────────────────────────
    for i, (label, name) in enumerate(meta.parties):
        for line in _wrap(name, FONT_BOLD, SIZE_COVER, CONTENT_W):
            c.setFont(FONT_BOLD, SIZE_COVER)
            c.drawCentredString(CONTENT_CX, y, line)
            y -= COVER_LEAD
        c.setFont(FONT_REGULAR, SIZE_COVER)
        c.drawRightString(CONTENT_R, y, label)
        y -= COVER_LEAD
        if i < len(meta.parties) - 1:
            c.drawCentredString(CONTENT_CX, y, "-and-")
            y -= COVER_LEAD

    # ── Bundle title between tramlines ───────────────────────────────────────────
    _tramlined_text(
        c, meta.bundle_title, CONTENT_CX,
        FONT_BOLD, SIZE_BUNDLE_TITLE,
        y_center=BUNDLE_TITLE_CY,
        width=TRAMLINE_W,
    )

    c.save()


def generate_statdec_cover(meta: StatDecMeta, output_path: Path) -> None:
    """Render a one-page A4 StatDec exhibits cover to *output_path*."""
    c = canvas.Canvas(str(output_path), pagesize=A4)

    # ── Matter reference and address (top-left, bold) ────────────────────────────
    y = PAGE_H - MARGIN_T
    c.setFont(FONT_BOLD, SIZE_COVER)
    for line in meta.matter_lines:
        c.drawString(CONTENT_L, y, line)
        y -= COVER_LEAD

    # ── Declaration description (centred, bold) at ~55 % down the page ──────────
    # \n in the TOML value forces a line break; each segment is word-wrapped.
    desc_lines: list[str] = []
    for segment in meta.description.split("\n"):
        desc_lines.extend(_wrap(segment, FONT_BOLD, SIZE_COVER, CONTENT_W))

    desc_block_h = len(desc_lines) * COVER_LEAD
    desc_top_y = PAGE_H * 0.55 + desc_block_h / 2  # centre the block at 55 %
    y = desc_top_y
    c.setFont(FONT_BOLD, SIZE_COVER)
    for line in desc_lines:
        c.drawCentredString(CONTENT_CX, y, line)
        y -= COVER_LEAD

    # ── Bundle title between tramlines at ~40 % down the page ────────────────────
    _tramlined_text(
        c, meta.bundle_title, CONTENT_CX,
        FONT_BOLD, SIZE_BUNDLE_TITLE,
        y_center=PAGE_H * 0.40,
        width=TRAMLINE_W,
    )

    c.save()


def build_cover(toml_path: Path, output_path: Path, style: str | None = None) -> None:
    """Read the cover style from *toml_path* and render the appropriate cover.

    *style* overrides the value in the TOML (useful for a CLI --style flag).
    Falls back to "court" if neither the override nor the TOML specifies a style.
    """
    with toml_path.open("rb") as f:
        data = tomllib.load(f)
    resolved_style = style or data.get("cover", {}).get("style", "court")

    if resolved_style == "statdec":
        generate_statdec_cover(load_statdec_meta(toml_path), output_path)
    elif resolved_style == "court":
        generate_cover(load_case_meta(toml_path), output_path)
    else:
        raise ValueError(f"Unknown cover style {resolved_style!r}. Expected 'court' or 'statdec'.")
