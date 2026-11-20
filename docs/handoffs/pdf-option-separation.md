# PDF question and answer separation

## Contract and invariants (2026-11-19)

Problem: legacy PDF images include the question, figure, and printed A-D answers.
Their pixels cannot be shuffled by reordering selection buttons. Keep that
display until an administrator reviews separate assets on a saved DRAFT question.

- Original PDF and full-question images are retained. Preview rendering writes
  immutable UUID-scoped candidate images; it never changes a question.
- A confirmed layout belongs to exactly one exam/source/question number and
  stores stem regions plus each canonical option's image regions or editable
  text. Option assets follow the option UUID, never its shuffled display letter.
- Printed option letters must be excluded from answer crops. The browser adds
  the current A-D labels. Source diagrams, equations, and tables are rasterized
  from the original PDF, never redrawn or generated.
- Automatic suggestions are conservative: four unambiguous A-D anchors in a
  single vertical column or horizontal row. Ambiguous, scanned, or multi-page
  layouts require manual cropping; suggestion failure cannot enable shuffling.
- All crop coordinates must be finite, positive, bounded by the original
  question regions, and non-overlapping. Image crops must contain visible ink.
  Text mode requires a nonempty, distinct reviewed answer. Images require
  nonempty, distinct accessibility descriptions as well.
- Confirmation requires a current preview and explicit review. Lock the exam
  and question; reject published/closed, stale, foreign, malformed, and
  unauthorized requests. Repeating the same confirmation is idempotent.
- Preview fingerprint includes the source reference, full crop, question text,
  option IDs/content/correctness, and marks. Changing authoring state rejects
  stale confirmation. Saved layout signatures include source/crop/content;
  unrelated settings/marks do not lose an otherwise valid split.
- Bulk save preserves a confirmed layout only when the source/crop/question and
  canonical option text are unchanged. Other edits fall back to the full image
  and require review again. No published question/active attempt is rewritten.
- Text questions and confirmed split questions use the existing per-attempt
  frozen option-order snapshot. Legacy full-image questions remain positional.
  Active payloads never disclose answer keys, original labels, or file paths.
- Admin asset routes require ADMIN and exam ownership binding. Student image
  routes require the owning unexpired active attempt and membership of both the
  question and option. No public static-media directory is introduced.
- Additive Alembic 0009_pdf_option_layout adds one nullable JSON-as-text column
  to questions. Historical migrations stay unchanged. No production migration
  or deployment is authorized by this implementation task.

## Verification plan before implementation

Geometry tests: triangle plus vertical choices, horizontal text choices,
diagram choices, ambiguous anchors, image-only scans, manual multi-page regions,
NaN/infinity/out-of-bounds/tiny/blank/overlapping regions, excluded label glyphs.

API tests: preview leaves old question unchanged; edit/regenerate preview;
confirm preserves option IDs, answer key and marks; stale/cross-exam/published/
student/unauthenticated requests fail; repeat confirmation; bulk-save retention
and invalidation; independently served assets and owner isolation; shuffled
content/ID association, normalized labels, stable resume/deadline/answers,
correct grading and answer-key non-disclosure; legacy behavior remains covered.

Browser checks: real isolated FastAPI/SQLite data; admin preview, full-page crop
correction, text/image modes, confirm, save, student shuffled delivery, refresh,
grading; keyboard controls; no overflow at 320, 360, 375, 390, 412, 768, 1024,
1280, and 1440. Capture representative source/stem/option PNGs and inspect them.

Detection is O(W + G) for words and graphic regions of one question. Rendering
cost follows the total requested pixels, bounded by existing upload/render
limits. Preview assets are immutable so failed confirmation cannot corrupt
currently served assets. Local previews use the existing private PDF storage.

## Using the feature

1. Open a draft examination, import its PDF and answer key, then save questions.
2. On the Questions tab, use **Separate answers for shuffling** and choose a
   saved PDF question. Select **Prepare answer preview**.
3. Check the question/figure and each answer against the original. Choose image
   mode for diagrams/equations or editable text for ordinary answers. Give each
   image an accurate, distinct description. Automatic text extraction is a
   suggestion and needs review.
4. Use **Adjust ... crop** to move/resize/draw regions or edit the keyboard
   coordinate fields. Add regions for content on another page. Exclude printed
   A-D letters and keep all figures/notation inside their crops.
5. Regenerate after edits, check the review box, and confirm. Repeat for the
   other image questions. Enable **Randomize option order** in exam settings
   and publish when the complete paper is ready.

Unseparated PDF questions retain their original full-image presentation and
fixed option order. Confirming a layout does not enable the exam-wide setting.
Published exams remain read-only. Source files and previously confirmed assets
are retained; unused previews have an explicit discard action. There is no
automatic orphan-preview retention/pruning policy in this change.

## Local verification and rollout handoff

Executed on 2026-11-19: full backend **363 passed, 1 skipped**; Ruff passed;
Alembic heads/history show one linear head `0009_pdf_option_layout`; migration
upgrade/downgrade preserved an existing SQLite row, and offline PostgreSQL SQL
adds only the nullable `questions.option_layout` column. The skipped existing
test requires an explicitly opted-in throwaway PostgreSQL instance. Live Neon
and PostgreSQL row-lock concurrency remain unverified.

Clean `npm ci`, global ESLint/TypeScript, all **17** configured frontend tests,
and production `tsc -b && vite build` passed. Existing dependency audit reports
12 vulnerabilities (1 low, 7 moderate, 3 high, 1 critical); no dependency or
lockfile changes were made for this feature.

Actual Playwright/installed Chromium verification used a real isolated
FastAPI/SQLite backend, temporary source storage, signed local test identities,
and real HTTP authoring/student APIs. Admin preview/crop/text/image/confirm,
visible student answer content, selection/autosave/refresh/deadline, and 100%
grading passed. Admin and both student modes passed 320, 360, 375, 390, 412,
768, 1024, 1280, and 1440 px without horizontal overflow. Final run had no
console/runtime errors or failed HTTP responses. Source, stem, option crops,
and representative rendered screenshots were visually inspected.

The existing student CSS hid answer content whenever a fieldset contained an
image. It now uses the explicit legacy `data-options-in-image` flag, preserving
compact full-image controls while showing separated answer text/images.

Evidence: `output/pdf/option-separation/report.md`, `browser-results.json`,
test/build logs, and PNGs. The guarded harness in
`backend/tests/pdf_layout_browser_server.py` requires
`DPCIS_PDF_LAYOUT_TEST=1`; normal app routes do not expose test-session or
test-paper endpoints. The alternate Vite config is serve-only and explicitly
rejects builds. Production source/auth modules remain unchanged. Source and
production-bundle scans found no credential, stale-provider, or harness leakage.

To rerun browser verification, use three terminals from the indicated folders:

```sh
# backend/
DPCIS_PDF_LAYOUT_TEST=1 ./.venv/bin/python -m uvicorn pdf_layout_browser_server:app --app-dir tests --host 127.0.0.1 --port 8031
```

```sh
# frontend/
DPCIS_PDF_LAYOUT_TEST=1 npm run dev -- --config tests/vite.option-layout.config.ts
```

```sh
# frontend/ (requires an installed Playwright and Chromium/Brave)
node tests/pdf-option-layout-browser-verify.mjs
```

Stop the two temporary servers afterward. They use disposable data, no live
Neon branch, and no production credentials. Do not use that alternate auth
configuration for normal development or deployment.

Before running the feature against the application's actual database, configure
and verify the intended development database, then apply Alembic head there.
Deployment requires the same private persistent PDF storage used by the existing
import feature. No application database migration, production mutation,
deployment, commit, or push was performed. Local development authentication
configuration is still pending the user's Neon login/access.
