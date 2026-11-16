# PDF Importer Hardening & Real-Paper Verification — 2026-11-16

**Branch:** `wip/importer-diagram-hardening` (local commits only, not pushed; PyMuPDF + standard library only; no `package.json`, lockfile, auth, grading, route, or migration changes).

## 1. Synthetic Corpus Coverage Matrix (Types 1–20 + Scan Set)

Verified via `pytest -q tests/test_diagram_corpus.py`, `output/pdf/recrop-verification/corpus-warning-inventory.json` (`63` questions, `0` unexpected warnings on clean fixtures), and visual inspection of `docs/ui-screenshots/importer-verify/corpus-sheet.png`.

| Type | Test case | Result | Warnings (expected / unexpected) | Notes / KNOWN LIMIT & workaround |
| --- | --- | --- | --- | --- |
| 1 Vector drawings | `01-vector` | PASS | 0 / 0 | Apparatus (beaker/funnel), circuit (6 V), ray diagram (lens + F) |
| 2 Raster / alpha | `02-raster_alpha` | PASS | 0 / 0 | Opaque JPEG, RGBA alpha PNG, grayscale raster |
| 3 Clip / soft mask / form | `03-clip_form` | PASS | 0 / 0 | Clipped form XObject + triangular vector clip path |
| 4 Graph | `04-graph` | PASS | 0 / 0 | Negative & decimal tick labels, grid, curve, legend, distant axis title |
| 5 Filled charts | `05-filled_charts` | PASS | 0 / 0 | Bar chart + pie chart with radial dividers & percentage labels |
| 6 Tables | `06-tables` | PASS | 0 / 0 | Ruled, text-only, merged-header, and shaded tables |
| 7 Chemistry | `07-chemistry` | PASS | 0 / 0 | Skeletal bonds, wedged bond, CH3, OH labels |
| 8 Maths | `08-maths` | PASS | 0 / 0 | Triangle, number line tick numerals, coordinate grid `(1, 1)` |
| 9 Callouts | `09-callouts` | PASS | 0 / 0 | Distant `remote label` + leader line |
| 10 Diagram options | `10-picture_options` | PASS | 0 / 0 | Horizontal row, 2×2 grid, vertical stacked options |
| 11 Diagram placement | `11-after_options` | PASS | 0 / 0 | Diagram placed below options |
| 12 Multiple / inline | `12-multiple_inline` | PASS | 0 / 0 | Two figures + small inline circle + `Fig. 1.1` caption |
| 13 Continuation | `13-continuation` | PASS | Expected height-outlier / 0 | Multi-page Q1 diagram + Q2 stem-then-next-page-options |
| 14 Shared stimulus | `14-shared` | PASS | Expected shared-stimulus review / 0 | Flags `"Needs review: shared stimulus..."`; admin includes/duplicates manually if needed |
| 15 Rotation | `15-rotation` | PASS | 0 / 0 | 90° page rotation normalized cleanly |
| 16 Decoration | `16-decoration` | PASS | Expected watermark review / 0 | Uniform tinted border passes; **KNOWN LIMIT:** overlapping `"WATERMARK"` in text stream cannot be erased safely — supply clean source or review manually |
| 17 Two columns | `17-columns` | PASS | 0 / 0 | 4-question 2-column layout |
| 18 Bands | `18-bands` | PASS | 0 / 0 | Header/footer text & thin rule masked cleanly |
| 19 Tight spacing | `19-tight` | PASS | 0 / 0 | 6 pt gap without neighbour bleed |
| 20 Scale extremes | `20-scale` | PASS | Expected height-outlier / 0 | Large full-page figure + sub-20 pt symbol |
| Scan 150 / 300 DPI | `scan-150`, `scan-300` | PASS (flagged) | Expected scan + manual-crop / 0 | Skew (~1°), noise & edge shadow fail closed as `"Crop failed: needs manual crop..."`, never inventing splits |

## 2. Real-Paper & Real-Scan Results

`backend/tests/fixtures/pdfs/real-incoming/` was absent (`0` PDFs). Real scanned exam pages supplied by the user (`docs/ui-screenshots/importer-verify/j1.jpg`, `j2.jpg`) and the CAIE regression anchor (`cie_igcse_chem_2_2_atomic_structure_qp.pdf`) were processed and visually inspected (`docs/ui-screenshots/importer-verify/real/real-scans-sheet.png`):

| Paper / Scan | Expected questions | Detected splits | Auto-valid | Needs manual | Warnings by type | Visual inspection & KNOWN LIMIT / workaround |
| --- | --- | --- | --- | --- | --- | --- |
| `cie_igcse_chem_2_2_atomic_structure_qp.pdf` | 24 | 24 | 24 | 0 | `Unassigned content` (p.1, p.7 paper headings), `No option letters detected` (Q4, Q7, Q16, Q21) | All 24 crops contain their graphics cleanly without neighbour or header/footer bleed; 6 flagged questions require acknowledgement before import. |
| `j1.jpg` (real scan: `P 8`, `P 9`, `P 10`) | 3 | 5 | 5 | 0 | `Scan mode: white-gap split` (5) | `P 8` clean (`Q1`); `P 9` stem (`Q2`) split from diagram+options (`Q3`); `P 10` stem (`Q4`) split from options (`Q5`). **KNOWN LIMIT:** white-gap scan splitting without OCR splits stems from widely spaced diagrams/options. **Workaround:** `Merge with next question` in preview (`4546 ms` at `1440px`, `3979 ms` at `390px` including crop-editor edits). |
| `j2.jpg` (real scan: `C.7`, `C 8`) | 2 | 6 | 0 | 6 | `Scan mode: white-gap split` (6), `Crop failed: non-white pixels touch...` (6) | `C.7` split into stem+`a)` (`Q1`), `b)` (`Q2`), `c)` (`Q3`), `d)` (`Q4`); `C 8` split into stem (`Q5`), `a)-d)` (`Q6`). **KNOWN LIMIT:** JPEG compression specks near page edges fail strict 255 border check, flagging all 6 `needs manual crop`. **Workaround:** merge splits and nudge left/right/top/bottom edges in crop editor. |

## 3. 40-Page Performance & Browser Edit Verification

- **40-page benchmark (`120` questions + `pdf_coverage`):** `3.062s` total (`0.077s/page`), within `< 2s/page`.
- **Browser edit pass (`real-scan-browser-verify.mjs` at `1440` and `390` px on `j1.jpg`):**
  - Confirmed scan warnings block `"Add ready questions"` until acknowledged.
  - Merged `5` provisional splits to `3` questions via `"Merge with next question"` (`real-1440-merged.png`, `real-390-merged.png`).
  - Exercised left edge drag, right edge drag, coordinate input (`Region 1 left`), `"Add same page region"`, and `220` DPI `"Regenerate crops"` (`real-1440-crop-edit.png`, `real-390-crop-edit.png`), with zero horizontal overflow and zero unexpected console errors; temporary servers stopped afterward.

## 4. Verification Gates (Observed Output)

- **Backend Ruff:** `python -m ruff check app tests alembic` -> `All checks passed!`
- **Backend Full Suite:** `python -m pytest -q` -> `100%` passed (1 Postgres test skipped).
- **Alembic Head:** `python -m alembic heads` -> `0006_submission_reason (head)`
- **Frontend Lint, Tests, Build:** `eslint . && tsc -b --noEmit`, `npm test` (`14 passed`), `vite build` (checked in `task-3895`).
- **Browser Harnesses:** `importer-browser-verify.mjs` (`1440`, `390` px) -> PASS; `real-scan-browser-verify.mjs` (`1440`, `390` px) -> PASS.

## 5. Not Guaranteed / Not Verified

- **Not guaranteed:** Automated detection cannot guarantee semantic ownership on arbitrary PDFs (overlapping watermarks, shared multi-question stimuli, or white-gap splits on un-OCR'd scans); `pdf_coverage.py` and the manual crop editor are the required safety net.
- **Not verified:** Selectable PDFs in `backend/tests/fixtures/pdfs/real-incoming/` (directory absent); live PostgreSQL concurrency (1 Postgres test skipped; local tests use isolated SQLite); `j2.jpg` interactive merge/crop-editor click-through in browser (inspected via `detect_scan_questions` + `real-scans-sheet.png`, while `j1.jpg` exercised the full browser merge/edit flow).
