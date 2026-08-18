#!/usr/bin/env python3
"""
ruler_overlay.py – Add a left-margin ruler to every page of a PDF.

Useful as a reference when creating or tweaking line_config.toml files.

Two scales share one spine:
  RIGHT of spine  – counts downward from the TOP edge
  LEFT  of spine  – counts upward  from the BOTTOM edge

Both scales run the full page height, so a highlight anywhere on the page
can be measured from whichever edge is more convenient.

  Minor ticks  every 10 mm  (1 cm)
  Major ticks  every 50 mm  (5 cm)  – longer tick, larger label

Usage:
    .venv/bin/python ruler_overlay.py <input.pdf> [--output PATH]
"""

import argparse
import sys
from pathlib import Path

import pymupdf

# ── Geometry (all in points) ───────────────────────────────────────────────────
MM = 2.8346

SPINE_X     = 15 * MM   # x of spine — inset enough for left-side labels
MINOR_LEN   =  3 * MM
MAJOR_LEN   =  6 * MM

MINOR_STEP  = 10 * MM   # 10 mm
MAJOR_STEP  = 50 * MM   # 50 mm

# Label offsets from spine
RIGHT_LABEL_X = SPINE_X + MAJOR_LEN + 1.5 * MM   # "from top" labels
LEFT_TICK_GAP =                        1.5 * MM   # gap between left tick end and label

# ── Appearance ─────────────────────────────────────────────────────────────────
GREY_TOP    = (0.65, 0.65, 0.65)   # slightly darker  — from-top  scale
GREY_BOT    = (0.78, 0.78, 0.78)   # slightly lighter — from-bottom scale
SPINE_COLOR = (0.70, 0.70, 0.70)
SPINE_WIDTH = 0.4
MINOR_WIDTH = 0.3
MAJOR_WIDTH = 0.5
MINOR_FS    = 5.5
MAJOR_FS    = 7.0


def add_ruler(page: pymupdf.Page) -> None:
    h = page.rect.height

    # ── Spine ──────────────────────────────────────────────────────────────────
    page.draw_line((SPINE_X, 0), (SPINE_X, h),
                   color=SPINE_COLOR, width=SPINE_WIDTH)

    # ── From-top scale (ticks + labels to the RIGHT) ───────────────────────────
    y = MINOR_STEP
    while y <= h:
        cm = y / (10 * MM)
        is_major = abs(round(y / MAJOR_STEP) * MAJOR_STEP - y) < 0.5
        tick_end = SPINE_X + (MAJOR_LEN if is_major else MINOR_LEN)

        page.draw_line((SPINE_X, y), (tick_end, y),
                       color=GREY_TOP,
                       width=MAJOR_WIDTH if is_major else MINOR_WIDTH)

        if abs(cm - round(cm)) < 0.05:
            fs = MAJOR_FS if is_major else MINOR_FS
            page.insert_text(
                (RIGHT_LABEL_X, y + fs * 0.35),
                str(round(cm)),
                fontsize=fs, color=GREY_TOP, fontname="helv",
            )
        y += MINOR_STEP

    # ── From-bottom scale (ticks + labels to the LEFT) ─────────────────────────
    y = h - MINOR_STEP
    while y >= 0:
        dist = h - y          # distance from bottom edge
        cm   = dist / (10 * MM)
        is_major = abs(round(dist / MAJOR_STEP) * MAJOR_STEP - dist) < 0.5
        tick_end = SPINE_X - (MAJOR_LEN if is_major else MINOR_LEN)

        page.draw_line((SPINE_X, y), (tick_end, y),
                       color=GREY_BOT,
                       width=MAJOR_WIDTH if is_major else MINOR_WIDTH)

        if abs(cm - round(cm)) < 0.05:
            fs    = MAJOR_FS if is_major else MINOR_FS
            label = str(round(cm))
            tw    = pymupdf.get_text_length(label, fontname="helv", fontsize=fs)
            page.insert_text(
                (tick_end - LEFT_TICK_GAP - tw, y + fs * 0.35),
                label,
                fontsize=fs, color=GREY_BOT, fontname="helv",
            )
        y -= MINOR_STEP


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", help="Input PDF file")
    parser.add_argument("--output",
                        help="Output PDF path (default: <input> (ruler).pdf)")
    args = parser.parse_args()

    inp = Path(args.input).expanduser().resolve()
    if not inp.exists():
        sys.exit(f"File not found: {inp}")

    out = (Path(args.output).expanduser().resolve() if args.output
           else inp.with_name(f"{inp.stem} (ruler){inp.suffix}"))

    doc = pymupdf.open(str(inp))
    for page in doc:
        add_ruler(page)

    page_count = doc.page_count
    doc.save(str(out), garbage=4, deflate=True)
    doc.close()
    print(f"{page_count} pages  ->  {out}")


if __name__ == "__main__":
    main()
