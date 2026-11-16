# Dependency link removal — 2026-11-16

- Removed Junction `frontend/node_modules/dpcis` targeting `C:\Users\EricAppiahOwusu\Music\DPCIS` using exactly `cmd /c rmdir "frontend\node_modules\dpcis"` (no `/s`, no recursive deletion).
- Stopped repository Node PIDs 29016, 21768, 36040, 40176, 15636, 48308. The latter four appeared during the work. No repository uvicorn or test-browser process was identified; unrelated browser/MCP processes were retained.
- Integrity: `Test-Path` returned True for `backend/app`, `backend/tests`, `frontend/src`, `frontend/package.json`, `docs`, `.git`; False for the link. Git status had 115 lines before, 118 immediately after; first five identical, no removed entries, only the three newly created evidence files added. See `link-removal-integrity.json` and before/after snapshots.
- `git diff -- frontend/package.json` showed only `+    "dpcis": "file:..",`; ran `git restore frontend/package.json`. Final manifest and lockfile diffs are empty; `Select-String -Path frontend/package-lock.json -Pattern '"dpcis"','node_modules/dpcis'` returned no matches; lockfile SHA-256 unchanged.
- `Get-ChildItem -Force -Recurse -Attributes ReparsePoint -ErrorAction SilentlyContinue` from the repository root found **0 other links** (no exclusions).

| Command | Time | Result |
| --- | ---: | --- |
| `npm ci` (frontend) | 117.84 s | FAILED, exit -4048: EPERM unlink of `lightningcss-win32-x64-msvc/lightningcss.win32-x64-msvc.node`; peer-dependency warnings also logged. |
| `npm ls dpcis` | — | NOT RUN: stopped after installation failure. |
| `npm run lint` | — | NOT RUN: stopped after installation failure. |
| `npm test` | — | NOT RUN: stopped after installation failure. |
| `npm run build` | — | NOT RUN: stopped after installation failure; no comparison with prior stalled TypeScript or 116-second Vite build is possible. |
| `node --test frontend/tests/dependencyLinkGuard.test.mjs` | 0.50 s (runner) | 2 passed; run while installation was pending, before failure was reported. |

Loaded-module inspection (`Get-Process` / `.Modules`) found no holder; Windows Restart Manager (`RmStartSession`, `RmRegisterResources`, `RmGetList`, `RmEndSession`) reported **no locking processes** when checked. The EPERM cause/holder is therefore unresolved. No force-delete, retry, or repair was attempted. `node_modules` may be partially changed by the failed install.

Prevention: guard rejects `file:`/`link:` dependency values, `dpcis` names, and nested overrides; documentation prohibits `npm install` with `..` or `../`. Only this test and the one documentation line are included in the separate commit; prior coordination edits remain uncommitted.

Other commands used: `Get-CimInstance Win32_Process`; `Stop-Process -Id <listed PID>`; `git status --short | Select-Object -First 5`; `git rev-parse HEAD`; `Copy-Item -LiteralPath frontend/package.json -Destination output/pdf/recrop-verification/package.json.bak`; `$l = Get-Item frontend/node_modules/dpcis -Force; $l.LinkType; $l.Target; $l.Attributes`; `Compare-Object` on before/after status; `Get-FileHash frontend/package-lock.json`; `git diff --cached --check`; `git add -- frontend/tests/dependencyLinkGuard.test.mjs`; `git apply --cached --unidiff-zero -` and `git hash-object -w --stdin` / `git update-index --cacheinfo` to stage only the documentation line; `git commit -m "Guard frontend against local dependency links"`.
`nCommit: `33464c1` — only the new guard test and one coordination rule (2 files, 39 additions).
