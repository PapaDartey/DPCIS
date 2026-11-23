# Printed question number removal

Implemented locally on branch `codex/pdf-question-number-removal`.

Question images hide the printed source number, while the application shows the
student's current question number. Masking changes only a small number area;
question wording, complete diagrams, scientific values and answer options stay
intact. Original PDFs and existing assets are retained. Recognized text labels
are automatic; scans have **Mark question number** in the full-page crop editor.

| Executed verification | Result |
| --- | --- |
| Full backend suite | 390 passed, 1 existing PostgreSQL opt-in test skipped |
| Focused number-removal cases | 27 passed |
| Real chemistry-paper fixture | All 24 printed question markers detected and removed |
| Ruff | Passed |
| Alembic heads/history | One linear head, unchanged at 0009 |
| Clean npm ci | Passed; no dependency/lockfile changes |
| ESLint + TypeScript | Passed |
| Frontend tests | 17 passed |
| Production build | Passed |
| Browser, real local API | Passed; original Q3 shown as Q2 without printed 3 |
| Question/option ordering + grading | Stable refresh/autosave/deadline; 100% score |
| Manual scan correction | UI selection/keyboard coordinates, regeneration, stored metadata passed |
| Responsive checks | Three student questions + manual editor at all nine 320–1440 widths |
| Final browser errors | Zero console/runtime/failed HTTP responses |
| Source + bundle safety scan | 171 + 60 files, zero findings |
| Test server boundaries | Explicit opt-in required; normal API test-paper route 404 |

Inspected visuals:

- [Before: printed source number](before-numbered.png)
- [After: number removed, diagram and answer values preserved](after-numberless.png)
- [Source Q3 presented as Q2 on mobile](student-source-3-320.png)
- [Manual number-area editor on mobile](manual-number-320.png)
- [Scanned crop after marking the number](scan-number-removed.png)

Machine-readable [browser results](browser-results.json), [backend test log](backend-tests.log),
[frontend tests](frontend-tests.log), [build log](frontend-build.log),
[lint log](frontend-lint.log), [dependency installation](npm-ci.log),
[browser run](browser-run.log), [safety scan](safety-scan.json).

Coverage includes bare/punctuated/Q/Question prefixes, one-to-three digits,
colored paper, pixel equality outside the number area, meaningful numeric stem
starts, continuation pages, two columns/rotation, invalid/nonfinite/oversized
manual masks, scanned sources, new/regenerated/legacy/split delivery, role and
ownership checks, unchanged source bytes, stable attempts, and canonical grading.

Limitations: old crops with undocumented padding need regeneration; scans and
ambiguous headers need explicit manual review. No new migration is required by
this fix; combined code still depends on the prior option-separation migration
0009. Live Neon and deployed behavior remain unverified. Existing npm audit
findings total 12 vulnerabilities; no dependency upgrades were made. Temporary
servers were stopped; no commit/push/PR or production changes for this issue.

Implementation/usage: [handoff](../../../docs/handoffs/pdf-question-number-removal.md).

Publication follow-up (2026-11-23): feature commit `99a9ce4` is pushed to the
original DPCIS fork and included in [upstream PR #19](https://github.com/appiah233/DPCIS/pull/19).
All 296 application/test files match the validated Friday snapshot above;
publication credential/diff checks passed. The PR includes the author's note
that a new method for handling image-based questions is in progress.
