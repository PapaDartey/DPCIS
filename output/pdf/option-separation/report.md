# PDF answer separation — local implementation evidence

Implemented locally on 2026-11-19. Image questions can have a reviewed stem/figure
plus independent text or image options. The existing server-owned option UUID
snapshot shuffles those options, adds current A-D labels, preserves refresh and
saved answers, and grades canonical IDs. Original PDF assets remain available.

Use a saved draft's **Questions → Separate answers for shuffling → Prepare
answer preview**, adjust crops/text, regenerate, review, and confirm. Enable
the exam's **Randomize option order** setting. Automatic proposals cover
unambiguous four-choice vertical/horizontal layouts; scanned/ambiguous or
multi-page papers require manual crop review. Legacy full-image questions stay
fixed until confirmed. No published exam is modified.

| Executed check | Observed result |
| --- | --- |
| Full backend pytest | 363 passed, 1 existing throwaway-PostgreSQL opt-in test skipped |
| Focused separation + prior randomization cases | 22 passed |
| Ruff `app tests alembic` | Passed |
| Alembic heads/history | One linear head: `0009_pdf_option_layout` |
| Migration test | Upgrade/downgrade preserves existing SQLite row |
| PostgreSQL offline SQL | Nullable `questions.option_layout TEXT`; no data rewrite |
| Clean `npm ci` | Passed; unchanged dependency manifests/lockfile |
| Global frontend lint + TypeScript | Passed |
| Configured frontend tests | 17 passed |
| Production `tsc -b && vite build` | Passed |
| Real API browser workflow | Passed; correct UI-selected shuffled answers grade 100% |
| Responsive rendered checks | Admin and both student modes: all nine widths, 320–1440 px |
| Browser errors | Zero console/runtime errors and failed HTTP responses in final run |
| Test harness boundaries | Default-off backend guard; normal API test routes 404; test Vite build rejected |
| Safety scans | 170 source/config files + 60 production files; zero findings |
| `git diff --check` | Passed |

Backend behavior cases cover geometric validation, blank/clipped/overlapping/
nonfinite/out-of-bounds crops, horizontal text/diagram choices, scanned manual
and multi-page crops, preview without mutation, idempotent confirmation,
stale/cross-exam/role rejection, correct option-to-image association, private
asset access, published read-only behavior, unchanged bulk-save retention,
content-change invalidation, stable attempts, canonical grading, and active
answer-key non-disclosure.

The browser check caught and corrected an existing broad CSS rule hiding all
answer content on image questions. Visibility is now explicitly checked for
every answer at every viewport. It also checks the real randomization checkbox,
crop coordinate editing, editable text and image modes, explicit review,
autosave, refresh, selection, server deadline, and submission.

Final machine-readable results: [browser-results.json](browser-results.json).
Logs: [backend tests](backend-tests.log), [frontend lint](frontend-lint.log),
[frontend tests](frontend-tests.log), [production build](frontend-build.log),
[dependency install](npm-ci.log), [browser run](browser-run.log),
[safety scan](safety-scan.json).

Inspected assets: [original question](source.png), [separated stem](stem.png),
[answer 70°](answer-B.png). Rendered examples:
[student text/mobile](student-1-320.png),
[student image/desktop](student-2-1440.png),
[admin mobile](admin-320.png), [crop editor mobile](crop-dialog.png).

Limits: live Neon/deployed browser and PostgreSQL locking concurrency were not
tested. Apply migration 0009 to the verified development database before normal
application use. Local Neon authentication setup remains pending. No live
database migration or production deployment was performed. Unused preview
pruning is manual. Existing npm audit reports 12 vulnerabilities (1 low,
7 moderate, 3 high, 1 critical); dependency upgrades are outside this feature.

Implementation and replay instructions:
[docs/handoffs/pdf-option-separation.md](../../../docs/handoffs/pdf-option-separation.md).
