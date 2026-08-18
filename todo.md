# Administrative Court Claim Bundle Builder - Todo List

## Phase 1: Design & Setup — COMPLETE
- [x] Finalise sequencing file format (CSV, row-order definitive, no order column)
- [x] Design and build index generator (ReportLab, direct PDF output)
- [x] Define PDF bookmark structure (see project_outline.md §Bookmark Structure)
- [x] Choose PDF merge library: pypdf (pure Python, actively maintained)
- [x] Define filing_mode concept (see project_outline.md §Filing Mode)

## Phase 2: Core Engine
- [x] Build PDF page-count extractor (pypdf, bundler/paginator.py)
- [x] Implement two-pass pagination calculator (bundler/paginator.py)
- [x] Build PDF merger (bundler/merger.py — pypdf append + page-number stamp)
- [x] Apply sequential page number overlay to merged bundle (ReportLab stamp merged via pypdf)

## Phase 3: Advanced Features
- [x] Implement PDF bookmark generation (nested: Index → sections → documents, bundler/merger.py)
- [x] Wire up index hyperlink annotations to named destinations in merged PDF (IndexLink rects from generate_index, GoTo annotations added by build_bundle)
- [x] Configure viewer settings (zoom 100% on open, on outline click, and on index hyperlink click; named destinations as belt-and-braces)
- [ ] Ensure searchability (OCR if needed)
- [ ] Compliance report output (pre-flight prediction + final size verification)

## Phase 4: Polish & Deployment
- [ ] polish the page number white background position (currently slightly offset / clunky)
- [ ] Build CLI interface
- [ ] Test with sample documents
- [ ] Documentation

## Phase 5: Refinement
- [ ] Implement pre-flight size estimator (sum of source PDF sizes + estimated index size)
- [ ] Implement 20MB rule engine:
  - [ ] Pass single bundle when predicted output <=20MB
  - [ ] For non-urgent filings, propose core+further split plan when needed
  - [ ] For urgent filings, block output plans >20MB
  - [ ] Error handling & validation (hard fail on 20MB non-compliance)
- [ ] Performance optimisation
- [ ] User testing
- [ ] Final adjustments
