# UK Administrative Court Claim Bundle Builder

> **Note:** this document is the original project spec and describes the intended
> end state, not necessarily current behaviour. See `todo.md` for what is
> implemented versus outstanding, and `README.md` for the actual current input
> formats and CLI. As of the current codebase: pagination, index generation with
> hyperlinks/bookmarks, page-number stamping, and both cover styles (court and
> statdec, see README) are implemented. The 20MB pre-flight rule, core/further
> bundle splitting, OCR/searchability validation, filing-mode CLI handling, and
> the compliance report below are **not yet implemented**.

## Project Goal
Automate conversion of PDF documents into claim-filing bundles compliant with UK High Court (Administrative Court) electronic bundle requirements.

## Core Requirements

### Input
- Multiple PDF documents (user-supplied)
- Sequencing file (defines order and document metadata)
- Filing mode metadata (claim / appeal / non-urgent application / urgent application)

### Compliance Rules
- **Pagination**: Match bundle PDF page numbers (1st page = 1, no internal per-document renumbering, Title pages and index pages all numbered)
- **Index**: Generated and formatted with page numbers and internal hyperlinks
- **Searchability**: Final output must be word-searchable (embedded text preferred, all scans run through high quality OCR)
- **Bookmarks**: PDF bookmarks for document navigation
- **View Settings**: Default zoom at 100%, landscape pages shown in landscape orientation
- **Pre-flight size compliance (20MB rule)**:
  - For claim / appeal / non-urgent application filings, predict output size and confirm either:
    - a single filing bundle is <=20MB, or
    - a compliant split is possible: `core_bundle.pdf` <=20MB + `further_bundle.pdf` (remaining documents)
  - For urgent applications, confirm planned output bundle is <=20MB
  - Block output unless a compliant structure is selected

### Output
- One or two compiled PDFs depending on pre-flight result:
  - `single_bundle.pdf` (if <=20MB), or
  - `core_bundle.pdf` + `further_bundle.pdf` (if split is required for non-urgent filing)
- Each output bundle includes:
  - Formatted index (generated directly as PDF via ReportLab) at front with section and document hyperlinks
  - All source PDFs in configured sequence
  - Correct page numbering calculated before index is rendered
  - Bookmarks and named destinations for each document/section
  - Proper metadata and view settings

## Technical Workflow

1. **Parse Input**: Read sequencing file, locate PDFs
2. **Calculate Pagination**: Count pages in each source PDF without merging. Estimate index page count (render with placeholder numbers), then compute final page offsets. Re-render index if estimated and actual page counts differ.
3. **Pre-flight Compliance Check**:
   - Estimate output PDF sizes using source PDFs and planned index pages
   - Validate 20MB rule for selected filing mode
   - Propose compliant output structure (single bundle vs core+further split)
4. **Generate Index**: Render index directly as PDF via ReportLab. Pagination must be calculated first (see below). Re-render once if the index page count changes on first pass (rare but possible).
5. **Build Bundle(s)**: 
   - Merge index PDF + source PDFs per selected structure
   - Apply correct page numbering
   - Add bookmarks
   - Set viewer preferences
6. **Validate Output**: Verify searchability, page counts, hyperlinks, and file size compliance
7. **Compliance Report**: Emit pre-flight and final size results with pass/fail status

## Bookmark Structure

Nested, mirroring the index:
```
Index                          → page 1
├── PLEADINGS                  → first page of section
│   ├── Claim Form (N461)      → document start page
│   └── Statement of Facts...  → document start page
├── DECISION UNDER CHALLENGE
│   └── Appeal Decision...
└── BACKGROUND DOCUMENTS
    ├── Covering Letter...
    └── ...
```
- Named destinations (e.g. `doc_3`) used in preference to absolute page numbers — more robust if the PDF is later manipulated.
- Each real document entry gets one named destination at its first page.
- Section headings get a destination pointing to the first document in that section.
- The index itself gets a top-level "Index" bookmark at page 1.
- Placeholder entries (no file) receive no bookmark.

## Filing Mode

Passed as a CLI flag or config key. Controls the 20MB pre-flight rule:

| Mode | 20MB rule |
|------|-----------|
| `claim` | Single bundle ≤20MB, or compliant core+further split |
| `appeal` | Single bundle ≤20MB, or compliant core+further split |
| `non_urgent_application` | Single bundle ≤20MB, or compliant core+further split |
| `urgent_application` | Single bundle must be ≤20MB; split not permitted |

The filing mode is not stored in the CSV — it is a per-run argument.

## Deliverables
- Executable script/tool
- Configuration template files
- Documentation and usage guide
