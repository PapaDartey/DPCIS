# Option randomization verification — 2026-11-19

Local backend API verification passed. Application behavior was unchanged; four
regression cases were added in `backend/tests/test_option_randomization.py`.
The tests use in-memory SQLite, temporary PDF storage, and locally generated
test identities. No live Neon database or deployed examination was used.

| Check | Observed result |
| --- | --- |
| Option shuffling disabled | `60°, 70°, 80°, 90°` stayed in its original order; 70° remained B. |
| Option shuffling enabled | A controlled non-identity permutation delivered `90°, 80°, 70°, 60°`; 70° moved to C while retaining its option ID. |
| Reload and resume | Options, labels, saved answer, attempt identity, and deadline stayed unchanged. The test rejects any attempt to call the shuffler during reload/resume. |
| Correctness after movement | Selecting the canonical correct option ID still graded 100%; authorized post-submission review matched the delivered order. |
| Actual random generator | The focused run produced 11 distinct orders across 16 independent attempts by two students. All refreshed orders stayed stable and all correctly answered attempts graded 100%. Repeated permutations are valid. |
| Mixed PDF/text examination | Two PDF figure questions kept their printed option order; the text question shuffled. Delivered figure PNGs exactly matched the administrator's source images. The completed exam graded 100%. |
| Answer-key disclosure | Active delivery responses omitted the forbidden answer-key fields checked by the existing security helper. |

Focused run: **4 passed in 1.54 seconds**. Full backend suite: **345 passed,
1 skipped in 17.28 seconds**. The skipped PostgreSQL test requires explicit
throwaway-database opt-in, which was not enabled.

Ruff passed. Alembic reported one linear head, `0008_google_email_proof`, and its
history was inspected without applying migrations. Source/config scans covered
164 files and the existing frontend bundle scan covered 35 files, with zero
credential-marker or stale-auth findings. Full quality-check output is saved in
`backend-quality.log` alongside this report.

This verifies local API behavior. The deployed site's checkbox and authenticated
browser flow were not exercised in this run. VS Code terminal control became
unavailable; opening Apple Terminal was rejected by Computer Use, so the rerun
used the command tool and its output was saved here.

To repeat the focused checks from `backend/`:

```bash
env -u DATABASE_URL -u DIRECT_DATABASE_URL \
  -u NEON_AUTH_BASE_URL -u NEON_AUTH_JWKS_URL -u NEON_AUTH_AUDIENCE \
  -u DPCIS_THROWAWAY_POSTGRES \
  ./.venv/bin/python -m pytest -vv -s tests/test_option_randomization.py
```
