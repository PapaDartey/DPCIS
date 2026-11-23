# Remove printed question numbers from PDF crops

## Contract and test plan before implementation (2026-11-20)

Problem: the app's shuffled display number disagrees with the printed source
question number embedded in a PDF crop. The app's display number is authoritative.

- Preserve image dimensions and all question/figure/answer pixels outside a
  narrowly bounded number rectangle; never trim the entire left margin.
- Automatically detect only the leading source-number marker on the first
  region, at the start of the first text line with nearby stem text. Support
  bare numbers, punctuation and explicit Q/Question prefixes. Reject mismatched,
  ambiguous, embedded numeric values and continuation-page candidates.
- Source PDFs and full-page crop-editing images remain original. New/generated
  question crops hide the number. Existing stored student images receive the
  same presentation change without rewriting source assets or attempt state.
- Scans without a trustworthy text layer require a reviewed manual number box;
  do not guess which pixels are digits. Store the optional box in the existing
  crop JSON, validate finite coordinates, size, containment and first-region
  placement. No database column or migration is needed.
- Apply masking to question stems only. Option diagrams, equations, tables,
  labels, meaningful numbers and answer identities remain unchanged. Existing
  RBAC/ownership/active-attempt checks remain authoritative.
- Use the existing draft crop editor for manual correction with accessible
  coordinate fields and source-page preview. Changing crop metadata invalidates
  a previously reviewed split through its existing signature check.

Expected tests: one/two/three-digit and punctuated markers, tight spacing,
multiple columns, a diagram extending left of the stem, real-paper fixtures,
same-number values within diagrams/options, number-only/ambiguous text,
first/continuation regions, rotated pages, source-byte preservation, original
versus sanitized PNG dimensions and byte-for-byte equality outside the mask,
non-white paper, invalid/oversized/outside/nonfinite manual boxes, scanned
manual masking, legacy and split private image delivery, randomized question
positions, stable refresh/deadline/selection/grading, and RBAC/IDOR rejection.

Rendering is O(pixels); text candidate inspection is O(words) for one crop.
Never invoke optional OCR, add dependencies, or modify a live database for tests.

## Implementation and use

Recognized leading numbers are hidden automatically in new PDF crops, regenerated
crops, and separated question stems. Student image delivery also cleans existing
stored full-question/stem PNGs without overwriting those assets. The printed
source number is removed from PDF accessibility/fallback text; the visible
question number still comes from the server's frozen attempt order.

For an ambiguous scan during import, open **Edit on full page** (or **Draw
question from PDF page**), use **Mark question number**, and draw or enter a small
rectangle covering only the printed number. **Apply crop**, inspect the result,
then continue the existing review/save workflow. Coordinate inputs are keyboard
accessible. The source PDF/full-page view stays original. `number_bbox` is stored
in the existing region JSON; `render_bbox` records the actual padded render area.
Only the first region may carry a manual number mask.

Older crops with undocumented padding require regeneration before automatic
removal because their original pixel mapping cannot be established safely.
Scans without a text layer require the manual number area. Ambiguous detection,
non-uniform paper around the label, and a source header already cropped off do
not permit an automatic erasure. Meaningful values in the stem, continuation
pages, figures, equations, tables and options are preserved.

No database migration or dependency change is added by this fix. The local
branch is `codex/pdf-question-number-removal`, based on the option-separation
implementation from PR #18; that existing feature's migration 0009 remains a
prerequisite when running the combined code against an application database.
Local Neon configuration and live deployment remain unverified.

## Executed evidence (2026-11-20)

- Full backend: **390 passed, 1 skipped**. The existing skipped test requires
  explicitly opted-in throwaway PostgreSQL. The number-removal module has
  **27** focused cases, including all 24 questions in the chemistry fixture,
  precise pixel preservation, source bytes, padded legacy images, multi-column/
  rotated papers, continuation values, manual scans, and private API grading.
- Ruff passed; Alembic heads/history remain one linear head at
  `0009_pdf_option_layout`. No migration was executed against an application DB.
- Clean `npm ci --prefer-offline`, ESLint/TypeScript, **17** frontend tests and
  production build passed. Existing audit findings: 12 vulnerabilities (1 low,
  7 moderate, 3 high, 1 critical); no package manifest/lockfile changes.
- Actual isolated FastAPI/SQLite + Playwright/Chromium browser run passed:
  source question **3** appeared as display question **2** with the printed
  number removed; both full and split images, correct answers/autosave/refresh/
  deadline, 100% final grading, and manual scan marking worked through real APIs.
- All three student questions and the manual editor were checked at 320, 360,
  375, 390, 412, 768, 1024, 1280, 1440 px without horizontal overflow. No
  console/runtime errors or failed HTTP responses in the final browser run.
- Visually inspected before/after crops, mobile shuffled question, manual
  editor, and final scanned crop. Source/production scan: **171 + 60** files,
  zero credential/stale-provider/test-harness findings. Normal app test-paper
  endpoint returns 404; the isolated server requires explicit opt-in.

Evidence and screenshots: `output/pdf/question-number-removal/report.md`.
Replay browser checks with the existing guarded Vite test config on port 5181,
the guarded `pdf_number_browser_server:app --app-dir tests` Uvicorn app on port
8031, and `node tests/pdf-question-number-browser-verify.mjs` from `frontend/`.
Both temporary test servers were stopped. Branch creation and quality commands
were shown in VS Code; its UI connection later became unavailable, so remaining
browser verification/cleanup used command tools. No commit, push, new PR,
production migration or deployment was performed for this workstream.

## Original repository publication (2026-11-23)

The user authorized committing and pushing Friday's changes and opening a new
PR against `appiah233/DPCIS`, using the existing `PapaDartey/DPCIS` fork. PR #18
was closed without merging; therefore this branch includes its option-separation
prerequisite as well as the number-removal fix. Upstream main has no intervening
commits. All 296 backend/frontend application and test files are byte-identical
to the Friday snapshot whose executed test and browser evidence appears above.
No application change or dependency reinstall was needed for publication.

Only this feature, tests and evidence are selected for the commit; unrelated
repository-publication files and their coordination row are excluded. The PR
description must include the author's requested note: "I'm also working on a new
method for handling image-based questions." No further technical details of that
method have been supplied, and this PR makes no implementation claim about it.

Commit, remote hash verification and PR URL are pending at this checkpoint.
