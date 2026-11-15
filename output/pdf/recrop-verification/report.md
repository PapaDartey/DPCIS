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

The stale audit snapshots were deleted and fresh audits were run from `frontend/` without editing `package.json` or the lockfile. Both commands exited 1 because advisories remain. Fresh `npm audit --omit=dev --json` reported **10 findings (6 low, 3 high, 1 critical)**; fresh full `npm audit --json` reported **17 findings (6 low, 7 moderate, 3 high, 1 critical)**. The critical finding is **GHSA-965c-763c-88jm: Better Auth OAuth state can be used as a Magic Link to sign in as another user**. The high findings are Better Auth OAuth Proxy (**GHSA-r4xp-prcw-77qf**) and Zod oversized constrained collections (**GHSA-mrhx-c7xc-m3w5**). No remediation was applied.

Advisory references: [BA-M: OAuth state/Magic Link (critical)](https://github.com/advisories/GHSA-965c-763c-88jm), [BA-P: OAuth Proxy (high)](https://github.com/advisories/GHSA-r4xp-prcw-77qf), [Z: Zod oversized collection memory exhaustion (high)](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5). Rows marked "inherited" are npm's transitive dependency findings, not additional independent advisories.

| Package / installed version(s) | Severity / advisory | Production bundle evidence | Smallest remediation candidate (not applied) |
| --- | --- | --- | --- |
| `better-auth` 1.7.6 (nested under Neon packages) | Critical BA-M; high BA-P; inherited Z | **Yes** in the previously saved Vite module graph (32 modules); the flagged server handlers were not identified in emitted client code | Vendor-supported Neon/Better Auth release, or a separately reviewed compatible override; validate all auth flows. |
| `zod` 4.5.4 (nested under Neon packages) | High Z | **Yes** in the previously saved Vite module graph (18 modules); app-specific exploitability was not proven | Vendor-supported patched Zod subtree or reviewed override to 4.6.6 with auth-schema tests. |
| `@neondatabase/auth` 0.6.0-beta | High, inherited BA/Z; direct dependency | **Yes** in the previously saved Vite module graph (54 modules) | Vendor release replacing affected nested pins; npm reports no safe automatic fix. |
| `@neondatabase/auth-ui` 0.4.0-beta | High, inherited BA/Z; transitive | **No** in the previously saved Vite module graph | Update through a supported Neon release; this package is not emitted by the current client graph. |
| `@better-auth/api-key`, `@better-auth/passkey`, `@daveyplate/better-auth-ui`, `@hookform/resolvers`, `better-call` | Inherited findings only; transitive | **No** for the flagged nodes in the previously saved graph | Resolve the Better Auth/Zod dependency tree through a supported vendor update; no independent app rewrite is indicated. |

Evidence: `audit-production-rerun.json`, `audit-full-rerun.json`, `production-modules.json`, and the saved prior bundle reachability scan. The fresh production bundle scan could not be rerun because the clean install did not complete and removed the local Vite binary; therefore the Yes/No bundle column is explicitly based on the previously saved module graph, not a new build. npm registry queries and dependency remediation were not repeated or changed in this pass.

The local app uses managed Neon authentication, not a self-hosted Better Auth server. Its deployed service version/plugin configuration was not inspected, so server vulnerability applicability remains unverified. The minimum versions above are advisory remediation candidates, not a claim that overrides are compatibility-safe. Authorization is needed before dependency remediation, as requested.

## Two-file fixture workflow

Drop `<name>.pdf` and `<name>.expected.json` into `backend/tests/fixtures/pdfs/`. JSON contains `section_counts`, `questions` keyed by printed question number with `{page, first_words, options_kind}`, and `expected_key`. Use `Unsectioned` for papers with no detected section. Optionally include verbatim `answer_key_text` and `excluded_text` phrases. The single parametrized `test_pdf_fixture_pair` discovers pairs; a missing partner fails instead of silently skipping it.

Current pair: `cie_igcse_chem_2_2_atomic_structure_qp` - 24 questions, Paper 1 = 18 and Paper 2 = 6. Its JSON includes text extracted from the original mark scheme. The mark-scheme PDF was moved to `pdfs/answer-keys/cie_igcse_chem_2_2_atomic_structure_ms.pdf` for provenance and existing upload/key-extraction tests. New papers need only the two paired files. Existing synthetic geometry fixtures remain separate regression fixtures.

## Production boundary

`DPCIS_BROWSER_TEST=1` is required explicitly by the test backend and Vite configuration; both default to rejection. The normal app returns 404 for `/__test_session`. The Vite test config rejects production builds even with the test variable set. Backend Docker packaging excludes `tests/` and copies only `app/`, Alembic, and configuration. The production module graph contains no harness modules or test-token markers. No production authentication code was modified.

Executed boundary output is in `backend-boundary.txt` and `frontend-boundary.txt`. The backend check emitted an existing Starlette/httpx deprecation warning; no dependency was added to silence it.

## Verification gates

| Command | Observed result | Log |
| --- | --- | --- |
| `ruff check app tests alembic` | All checks passed | `ruff.txt` |
| `python -m pytest -q tests/test_exams.py -k recrop` | **4 passed** | `recrop-tests-rerun.txt` |
| `python -m pytest -q tests/test_pdf_fixture_pairs.py` | **1 passed** | `fixture-tests-rerun.txt` |
| `python -m pytest -q` | **307 passed** | `backend-full-rerun.txt` |
| `python -m ruff check app tests alembic` | **All checks passed** | `ruff-rerun.txt` |
| `python -m alembic heads` | **`0006_submission_reason (head)`** | `alembic-heads-rerun.txt` |
| `python -m alembic history` | **One linear chain, 0001 through 0006** | `alembic-history-rerun.txt` |
| `npm ci` | **Blocked**: repeated archive-entry errors and did not terminate in the shared Windows worktree; stopped only my process | `npm-ci-rerun.txt` |
| `npm run lint` | **Blocked**: `eslint` binary unavailable after incomplete install | `lint-rerun.txt` |
| `tsc -b --noEmit` | **Blocked**: TypeScript binary unavailable | `tsc-rerun.txt` |
| `npm test` | **12 passed** | `frontend-tests-rerun.txt` |
| `npm run build` | **Blocked**: `tsc` binary unavailable | `build-rerun.txt` |
| Backend default-off boundary | **PASS**; `/__test_session` returned 404 | `backend-boundary-rerun.txt` |
| Frontend production boundary / new bundle scan | **Not run**; Vite unavailable after incomplete install | `browser-frontend-start-rerun.txt` |
| Changed-file secret-pattern scan | **No live credential found**; test-only token/session literals are expected in harness files | `security-scan-rerun.txt` |

The additional browser pass requested at 1440 and 390 px was **not verified**. The isolated backend could not bind because a prior reload process retained port 8000, and the test frontend could not start without Vite. The earlier multi-width browser evidence remains documented above, but it is not a substitute for this requested final rerun. No new migration, production DB connection, deployment, or dependency remediation was performed.

## Open items

- Dependency remediation requires user authorization and compatibility validation; no upgrades were attempted.
- Managed Neon server patch status and live PostgreSQL concurrency were not verified. Tests use isolated SQLite; this is not production/PostgreSQL concurrency evidence.
- Explicit approve/discard cleanup is verified. Automatic sweeping of abandoned previews is not implemented.
- Local Windows/Chromium coverage does not establish Safari/Firefox parity.
- The fresh production bundle, frontend lint/typecheck/build, and final 1440/390 browser rerun were not verified because the shared Windows dependency install did not complete.
- Neon Managed Auth's deployed Better Auth/Zod patch status cannot be verified from this repository; the managed service is external to this local codebase.
