"""Report counts/paths only, never matching credential values."""
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[3]
patterns = {
    "private key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "cloud access key": r"(?:AKIA|ASIA)[A-Z0-9]{16}",
    "service key": r"(?:sk-proj-|sk_live_|ghp_|github_pat_)[A-Za-z0-9_-]{20,}",
    "database credential": r"postgres(?:ql)?(?:\+\w+)?://[^\s\"']+@",
    "literal signed token": r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}",
}
findings = []
extensions = {".py", ".ts", ".tsx", ".mjs", ".js", ".json", ".html", ".css", ".md"}
scanned = 0
for folder in ["backend/app", "backend/tests", "frontend/src", "frontend/tests", "frontend/dist"]:
    for path in (root / folder).rglob("*"):
        if not path.is_file() or path.suffix not in extensions:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        scanned += 1
        for label, pattern in patterns.items():
            if re.search(pattern, text):
                findings.append({"path": str(path.relative_to(root)), "pattern": label})
        if folder in {"backend/app", "frontend/src", "frontend/dist"}:
            for label, pattern in {
                "test-session marker": r"__test_session|browser-test-admin|importer-test-auth|DPCIS_BROWSER_TEST",
                "removed auth provider": r"clerk",
            }.items():
                if re.search(pattern, text, re.I):
                    findings.append({"path": str(path.relative_to(root)), "pattern": label})
report = {"files_scanned": scanned, "findings": findings,
          "scope": "Pattern scan, not a comprehensive security audit"}
(Path(__file__).parent / "security-scan.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report))
raise SystemExit(bool(findings))
