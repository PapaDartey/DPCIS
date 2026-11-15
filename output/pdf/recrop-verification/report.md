# Re-crop continuation verification - 2026-11-15

Local FastAPI/SQLite and React/Vite verification only. No production resources, authentication implementation, grading, migrations, dependency versions, package.json, or lockfiles were changed by this workstream. Peer rebrand/redesign work remains separate.

## Failure diagnosis and implementation

The original browser failure was reproduced at 1440 px (see `browser-baseline.txt`). Saved question positions are zero-based. The panel displayed the raw position, so its checkbox labelled "Question 1" selected the second saved question. The backend correctly changed that selected UUID, while the test incorrectly assumed array index zero would change. The panel now displays `position + 1`; the browser compares stable question UUIDs and checks every unapproved question is entirely unchanged.

Re-crop approval continues to update only source/image fields. The executed regressions preserve text, option IDs/text/order/correctness, marks, positions, source numbers, and original source/image bytes. They reject mixed invalid selections atomically, cross-exam image access, stale/replayed previews, and published exams. Candidate images return 401 without authentication and 403 to students.

New cleanup closes previews after approval/discard. After partial approval, only the committed candidate PDF plus approved question metadata/images remain; unused candidate files are deleted. Discard removes candidate directories while keeping original files byte-for-byte. A small closed-preview JSON record remains intentionally for explicit replay rejection. An expired preview may be discarded but cannot be applied. Abandoned previews are not background-swept; this work verifies explicit approve/discard cleanup, not an automatic retention service.

The importer action buttons now wrap at 320 px; the "Replace list with ready questions" button previously produced a one-pixel document overflow. Shared navigation and peer design CSS were not changed.

## Changed files

- Backend: `backend/app/exams/pdf_recrop.py` (cleanup/discard/expiry handling); existing router wiring was inspected and retained.
- Frontend: `frontend/src/features/admin/components/RecropPanel.tsx` (numbering/discard), `BulkParserPanel.tsx` (scoped button wrapping). Existing editor integration was inspected and retained.
- Tests: `backend/tests/test_exams.py`, `test_pdf_fixture_pairs.py`, `test_pdf_import.py`, `test_pdf_graphics.py`, `browser_server.py`, `verify_browser_boundary.py`; `frontend/tests/importer-browser-verify.mjs`, `importer-test-auth.ts`, `vite.importer.config.ts`, `production-boundary-verify.mjs`; relocated PDF fixtures and enriched expected JSON.
- Documentation/evidence: `docs/agent-coordination.md`, `docs/ui-screenshots/importer-verify/`, this directory. Existing graphics-import changes were retained, not attributed as new continuation work.

## Browser results

Each row exercised a real upload and local backend APIs: invalid vector preview and import blocking; 24-question preview; top and bottom handle drags; deliberate text clipping rejected with HTTP 422; saving 24 questions; before/after re-crop preview; partial approval of Q1; unchanged unapproved questions/keys/marks; document overflow checks and console/runtime monitoring.

| Width | Upload/preview | Invalid blocked | Top/bottom drag | Clipping rejected | Import 24 | Re-crop/partial approval | No overflow/unexpected errors |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 320 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| 360 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| 375 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| 390 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| 412 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| 768 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| 1024 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| 1280 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| 1440 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |

Screenshots: `docs/ui-screenshots/importer-verify/<width>-invalid-preview.png`, `<width>-invalid-drag.png`, `<width>-crop-editor.png`, `<width>-recrop-before-after.png`. Exact paths and observations are in `browser-results.json`. Desktop and mobile before/after screenshots were also inspected visually. Each run records one expected browser resource-error message for its deliberate HTTP 422; there were no unexpected console errors or uncaught runtime exceptions. This does not claim a completely empty console during a deliberately failing request.

Harness repairs: the clipping drag now uses the crop response's current geometry and targets a known text line (215 pt), rather than a stale box that could land in whitespace. Test-only Vite watching/HMR is disabled because concurrent peer edits caused full reloads during earlier runs. The eight wider runs precede the final scoped wrapping adjustment; the final 320 px run verifies that adjustment. The local test servers were stopped afterward.

## npm audit triage - no upgrades

Both commands exited 1 because advisories remain. `npm audit --omit=dev`: **16 findings (6 low, 9 high, 1 critical)**. Full `npm audit`: **23 findings (6 low, 7 moderate, 9 high, 1 critical)**. All high/critical entries also occur in the production dependency tree; none is solely a development-tool finding. Installed dependency does not imply emitted or exploitable code.

Advisory references: [BA-M: OAuth state/Magic Link (critical)](https://github.com/advisories/GHSA-965c-763c-88jm), [BA-P: OAuth Proxy (high)](https://github.com/advisories/GHSA-r4xp-prcw-77qf), [Z: Zod oversized collection memory exhaustion (high)](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5). Rows marked "inherited" are npm's transitive dependency findings, not additional independent advisories.

| Package / installed version(s) | Severity / advisory | Production bundle evidence | Smallest remediation candidate (not applied) |
| --- | --- | --- | --- |
| `better-auth` 1.7.6 | Critical BA-M; high BA-P; inherited Z | 32 emitted client/helper modules; vulnerable server OAuth/Magic Link handlers absent | Better Auth 1.7.7, with compatible related Better Auth packages kept aligned. Neon pins 1.7.6, so use a vendor-supported Neon update or explicitly reviewed override; validate auth flows. |
| `zod` 4.5.4 | High Z | 18 emitted modules, including collection/schema parsing; exploitability of specific app inputs not proven | 4.6.6 in both pinned Neon subtrees; requires vendor update or reviewed override plus auth-schema tests. |
| `@neondatabase/auth` 0.6.0-beta | High, inherited BA/Z | 54 emitted modules; pins affected Better Auth/Zod | Vendor update that replaces those exact pins, or reviewed nested overrides to minimum patched versions. npm reports no direct automatic fix. |
| `@neondatabase/auth-ui` 0.4.0-beta | High, inherited BA/Z | 0 emitted modules | Update its pinned Better Auth/passkey and Zod subtree through a supported Neon release; no runtime UI patch needed here. |
| `@better-auth/api-key` 1.7.21 | High, inherited BA/Z | 0 emitted modules | Resolve affected Better Auth/Zod dependencies; no independent API-key advisory in this audit. |
| `@better-auth/core` 1.7.21 | High, inherited Z via Better Call | 0 emitted modules for flagged node | Resolve Zod to 4.6.6 in affected subtree; keep Better Auth family compatible. |
| `@better-auth/passkey` 1.7.6 | High, inherited BA/Z | 0 emitted modules | Align with patched Better Auth release and patched Zod through vendor dependency update. |
| `@daveyplate/better-auth-ui` 3.4.0 | High, inherited BA/Z | 0 emitted modules | Resolve affected child dependencies; no independent advisory requiring a UI rewrite. |
| `@hookform/resolvers` 5.9.2 | High, inherited Z | 0 emitted modules | Resolve affected Zod peer/subtree to 4.6.6 and validate resolver compatibility. |
| `better-call` 2.0.2 (flagged nested copy) | High, inherited Z | 0 emitted modules for flagged copy | Resolve affected Zod dependency to 4.6.6; no independent high Better Call advisory here. |

Evidence: `audit-production.json`, `audit-full.json`, `audit-bundle-reachability.json`, `production-modules.json`, `production-boundary.txt`. A Vite production build with `write:false` recorded actual nonzero rendered module lengths rather than guessing from package names. npm registry queries confirmed Better Auth 1.7.7 and Zod 4.6.6 exist. The advisory prose still says the Better Auth release was planned; registry availability was checked separately.

The local app uses managed Neon authentication, not a self-hosted Better Auth server. Its deployed service version/plugin configuration was not inspected, so server vulnerability applicability remains unverified. The minimum versions above are advisory remediation candidates, not a claim that overrides are compatibility-safe. Authorization is needed before dependency remediation, as requested.

## Two-file fixture workflow

Drop `<name>.pdf` and `<name>.expected.json` into `backend/tests/fixtures/pdfs/`. JSON contains `section_counts`, `questions` keyed by printed question number with `{page, first_words, options_kind}`, and `expected_key`. Use `Unsectioned` for papers with no detected section. Optionally include verbatim `answer_key_text` and `excluded_text` phrases. The single parametrized `test_pdf_fixture_pair` discovers pairs; a missing partner fails instead of silently skipping it.

Current pair: `cie_igcse_chem_2_2_atomic_structure_qp` - 24 questions, Paper 1 = 18 and Paper 2 = 6. Its JSON includes text extracted from the original mark scheme. The mark-scheme PDF was moved to `pdfs/answer-keys/cie_igcse_chem_2_2_atomic_structure_ms.pdf` for provenance and existing upload/key-extraction tests. New papers need only the two paired files. Existing synthetic geometry fixtures remain separate regression fixtures.

## Production boundary

`DPCIS_BROWSER_TEST=1` is required explicitly by the test backend and Vite configuration; both default to rejection. The normal app returns 404 for `/__test_session`. The Vite test config rejects production builds even with the test variable set. Backend Docker packaging excludes `tests/` and copies only `app/`, Alembic, and configuration. The production module graph contains no harness modules or test-token markers. No production authentication code was modified.

Executed boundary output is in `backend-boundary.txt` and `frontend-boundary.txt`. The backend check emitted an existing Starlette/httpx deprecation warning; no dependency was added to silence it.

## Final gates

Final frontend installation/build/scan results are being recorded before this report is closed.

| Command | Observed result | Log |
| --- | --- | --- |
| `ruff check app tests alembic` | All checks passed | `ruff.txt` |
| `pytest -ra` | 307 passed in 77.01s | `backend-full.txt` |
| `alembic heads` | `0006_submission_reason (head)` | `alembic-heads.txt` |
| `alembic history` | One linear chain, 0001 through 0006 | `alembic-history.txt` |
| `npm ci` | Pending final output | `npm-ci.txt` |
| `npm run lint` (ESLint + TypeScript) | Pending post-install run | `lint.txt` |
| `npm test` | Pending final run | `frontend-tests.txt` |
| `npm run build` (TypeScript + Vite) | Pending final run | `build.txt` |
| Secret/test-token/stale-auth pattern scans | Pending final bundle | `security-scan.json` |

Focused evidence: baseline re-crop tests 3 passed; expanded re-crop tests 4 passed; discovered fixture pair 1 passed. No new migration, production DB connection, deployment, or dependency remediation was performed.

## Open items

- Dependency remediation requires user authorization and compatibility validation; no upgrades were attempted.
- Managed Neon server patch status and live PostgreSQL concurrency were not verified. Tests use isolated SQLite; this is not production/PostgreSQL concurrency evidence.
- Explicit approve/discard cleanup is verified. Automatic sweeping of abandoned previews is not implemented.
- Local Windows/Chromium coverage does not establish Safari/Firefox parity.
- Final frontend gate output and checkpoint details will be filled before completion.
