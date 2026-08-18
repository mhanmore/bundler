# Administrative Court Claim Bundle Builder

Builds a paginated, hyperlinked, bookmarked PDF bundle (cover + index + documents)
from a directory of source PDFs and two input files: a sequence CSV and a case TOML.

## Input files

A source directory (default: `source/`) contains:

- `_case.toml` — case/matter metadata and bundle settings (see below)
- `_sequence.csv` — document order, sections, and titles (see below)
- the source PDFs referenced by the CSV

## Running

```
.venv/bin/python preview_bundle.py [--source PATH] [--docs PATH] [--style court|statdec] [--output PATH]
.venv/bin/python export_bundle.py  [--source PATH] [--output PATH] [--style court|statdec] [--stamp]
```

`--source` accepts either a directory containing `_case.toml` (default: `source/`)
or a path to a `.toml` file directly.

- **`preview_bundle.py`** — end-to-end build: cover → index → merged, page-stamped
  bundle. Writes `output/cover.pdf`, `output/index.pdf`, and
  `output/single_bundle.pdf` (or `--output PATH`).
- **`export_bundle.py`** — builds a self-contained ZIP: source PDFs copied into a
  numbered folder structure mirroring the index, plus a freestanding `cover.pdf`,
  `index.pdf`, `_config.toml`, and `_structure.csv` so the archive can be
  re-ingested by the bundler later. `--stamp` additionally stamps bundle page
  numbers onto each copied PDF and the cover/index.
- **`--style`** overrides `[cover] style` in the TOML (`"court"` or `"statdec"`,
  see below); default is `"court"`.
- **`--docs`** (preview only) overrides `docs_root` from the TOML.

`[bundle]` in the TOML may set:
```toml
[bundle]
title      = "CLAIM BUNDLE"   # required — used as the bundle title / export ZIP name
docs_root  = "relative/or/absolute/path"   # where source PDFs live (default: same dir as the toml)
sequence   = "_sequence.csv"               # path to the CSV, relative to the toml (default: _sequence.csv)
style      = "court"                       # or "statdec" — default cover layout (default: court)
```

## `_case.toml` specification

Two mutually exclusive metadata shapes are supported, selected by `[cover] style`
(or the `--style` CLI flag, which takes precedence). Both share the `[bundle]`
table described above.

### `style = "court"` (default) — Administrative Court claim bundle cover

```toml
[bundle]
title = "CLAIM BUNDLE"

[court]
lines = ["IN THE HIGH COURT OF JUSTICE", "KING'S BENCH DIVISION", "ADMINISTRATIVE COURT"]
reference = "AC                    2026"   # spaces are deliberate — gap for a handwritten case number

[application]
description = "Claim for Judicial Review"   # centred, bold; "\n" forces a line break

[parties]
claimant         = "..."
first_defendant  = "..."
second_defendant = "..."
# any number of party keys; underscores become spaces and the label is title-cased
# (e.g. first_defendant -> "First Defendant"); rendered in TOML key order with
# "-and-" between each party
```

Renders: court header (left) with case reference (right), application description
(centred), `BETWEEN:` + party blocks separated by `-and-`, bundle title between
tramlines.

### `style = "statdec"` — statutory declaration exhibits cover

```toml
[bundle]
title = "EXHIBITS"

[cover]
style = "statdec"

[matter]
reference     = "Matter ref / exhibit ref"
address_lines = ["Line 2 of the matter/address block", "Line 3", "..."]
# rendered top-left, bold: reference line followed by each address_lines entry

[declaration]
description = "Exhibits referred to in the Statutory Declaration of ..."
# centred, bold, ~55% down the page; "\n" forces a line break
```

Renders: matter reference/address block (top-left), declaration description
(centred, ~55% down the page), bundle title between tramlines (~40% down the page).

## Sequence CSV Specification

The sequence file defines the order and labels used to build the claim bundle index and merge documents.
Row order in the file is definitive — no order column is needed. Reorder rows to reorder the bundle.

### File location

Use: `templates/sequence_template.csv` as the starter format.

### Required columns

1. `section`
2. `entry_type`
3. `title`
4. `file_name`

Header row must exactly match:

```csv
section,entry_type,title,file_name
```

### Column rules

1. `section`
- Section label used for grouping (for example: `Pleadings`, `Background Documents`).
- Repeated across rows belonging to the same section.

2. `entry_type`
- Allowed values:
  - `section_heading`
  - `document`

3. `title`
- Display text used in the index.
- For `section_heading` rows: the heading text as it should appear (for example `PLEADINGS`).
  If blank, the `section` value is used as a fallback (uppercased).
- For `document` rows: the entry label as it should appear in the index.

4. `file_name`
- For `document` rows: PDF file name to include. Leave blank for placeholder entries
  (documents not yet available — rendered in the index but excluded from the bundle).
- For `section_heading` rows: leave blank.

### Example

```csv
section,entry_type,title,file_name
Pleadings,section_heading,PLEADINGS,
Pleadings,document,Claim Form (N461),
Pleadings,document,Statement of Facts and Grounds,
Background Documents,section_heading,BACKGROUND DOCUMENTS,
Background Documents,document,Decision Notice,Decision Notice.pdf
Background Documents,document,Witness Statement of Jane Smith dated 04 March 2026,ws_jane_smith_2026-03-04.pdf
```

### Validation expectations

1. CSV must include all required columns.
2. `entry_type` must be `section_heading` or `document`.
3. `entry_type=document` rows with a non-empty `file_name` must resolve to an existing PDF.
4. `entry_type=section_heading` rows must have an empty `file_name`.
