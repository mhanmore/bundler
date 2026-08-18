#!/usr/bin/env python3
"""
add_margin_lines.py – Draw vertical margin-highlight lines on PDF pages.

Reads a TOML config file describing one or more bundles and applies a coloured
vertical line to each specified page range.

Usage:
    .venv/bin/python add_margin_lines.py <config.toml> [--base-dir PATH]

--base-dir  Directory that contains the input/output PDFs.
            Defaults to the directory of the config file.
"""

import argparse
import sys
import tomllib
from pathlib import Path

import pymupdf


MM = 2.8346   # points per mm
CM = 28.3465  # points per cm

COLOR_NAMES = {
    "yellow": (1, 1, 0),
    "red":    (1, 0, 0),
    "green":  (0, 1, 0),
    "blue":   (0, 0, 1),
    "black":  (0, 0, 0),
    "white":  (1, 1, 1),
}


def parse_color(value: str | list) -> tuple[float, float, float]:
    if isinstance(value, str):
        key = value.lower()
        if key not in COLOR_NAMES:
            raise ValueError(f"Unknown colour name '{value}'. "
                             f"Use one of: {', '.join(COLOR_NAMES)}")
        return COLOR_NAMES[key]
    # Allow [r, g, b] lists in the TOML
    r, g, b = value
    return (float(r), float(g), float(b))


def process_bundle(bundle: dict, defaults: dict, base_dir: Path) -> None:
    name   = bundle.get("name", bundle["input"])
    inp    = base_dir / bundle["input"]
    out    = base_dir / bundle["output"]

    # Merge defaults with any per-bundle overrides
    x_mm    = bundle.get("x_from_left_mm",  defaults.get("x_from_left_mm",  2.0))
    lw_mm   = bundle.get("line_width_mm",   defaults.get("line_width_mm",   2.0))
    color   = parse_color(bundle.get("color", defaults.get("color", "yellow")))
    top_cm  = bundle.get("top_margin_cm",   defaults.get("top_margin_cm",   1.5))
    bot_cm  = bundle.get("bottom_margin_cm", defaults.get("bottom_margin_cm", 1.5))

    x  = x_mm * MM
    lw = lw_mm * MM
    top_margin = top_cm * CM
    default_bot_margin = bot_cm * CM

    # Build page override map  {0-indexed page: bottom_margin_pts}
    overrides: dict[int, float] = {}
    for ov in bundle.get("page_overrides", []):
        page_0 = ov["page"] - 1
        overrides[page_0] = ov["bottom_margin_cm"] * CM

    # Collect target pages (0-indexed)
    target_pages: set[int] = set()
    for start, end in bundle["page_ranges"]:
        target_pages.update(range(start - 1, end))

    if not inp.exists():
        print(f"  ERROR: input file not found: {inp}", file=sys.stderr)
        return

    doc = pymupdf.open(str(inp))
    drawn = 0
    for page_idx in sorted(target_pages):
        if page_idx >= doc.page_count:
            print(f"  WARNING: page {page_idx + 1} out of range (doc has "
                  f"{doc.page_count} pages) — skipped", file=sys.stderr)
            continue
        page = doc[page_idx]
        h = page.rect.height
        bot_margin = overrides.get(page_idx, default_bot_margin)
        page.draw_line((x, top_margin), (x, h - bot_margin),
                       color=color, width=lw)
        drawn += 1

    doc.save(str(out), garbage=4, deflate=True)
    doc.close()
    print(f"  {name}: {drawn} pages marked -> {out.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", help="Path to the .toml configuration file")
    parser.add_argument("--base-dir", help="Directory containing the PDFs "
                        "(default: directory of the config file)")
    args = parser.parse_args()

    config_path = Path(args.config).expanduser().resolve()
    if not config_path.exists():
        sys.exit(f"Config file not found: {config_path}")

    base_dir = Path(args.base_dir).expanduser().resolve() if args.base_dir \
               else config_path.parent

    with open(config_path, "rb") as f:
        config = tomllib.load(f)

    defaults = config.get("defaults", {})
    bundles  = config.get("bundle", [])

    if not bundles:
        sys.exit("No [[bundle]] entries found in config.")

    print(f"Config : {config_path.name}")
    print(f"Base   : {base_dir}\n")

    for bundle in bundles:
        process_bundle(bundle, defaults, base_dir)

    print("\nDone.")


if __name__ == "__main__":
    main()
