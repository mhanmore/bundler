# Administrative Court Claim Bundle Builder

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
