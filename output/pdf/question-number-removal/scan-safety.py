"""Report paths/rules only, never matched credential values."""
import json
import re
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[3]
targets = ["backend/app", "backend/alembic", "frontend/src", "frontend/package.json",
           "frontend/package-lock.json", "backend/.env.example", "frontend/.env.example",
           ".env.example", "docs/agent-coordination.md", "docs/handoffs/pdf-question-number-removal.md"]
files = subprocess.check_output(["rg", "--files", *targets], cwd=root, text=True).splitlines()
bundle = [p for p in (root / "frontend/dist").rglob("*") if p.is_file()]
rules = {
    "private-key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "aws-access-key": r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
    "github-token": r"\b(?:ghp_|github_pat_)[A-Za-z0-9_]{30,}\b",
    "openai-key": r"\bsk-(?:proj-)?[A-Za-z0-9_-]{30,}\b",
    "jwt-literal": r"\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b",
    "credential-database-url": r"postgres(?:ql)?(?:\+psycopg)?://[^\s\"'/:]+:[^\s\"'@]+@",
}
findings = []
for path in [root / f for f in files] + bundle:
    value = path.read_text(errors="ignore")
    for name, pattern in rules.items():
        if re.search(pattern, value):
            findings.append({"path": str(path.relative_to(root)), "rule": name})
    if "docs" not in path.relative_to(root).parts and re.search(r"clerk", value, re.I):
        findings.append({"path": str(path.relative_to(root)), "rule": "stale-auth-provider"})
    if path in bundle and any(marker in value for marker in
        ["DPCIS_PDF_LAYOUT_TEST", "__test_session", "layout-browser-role", "__test_number_paper", "layout-browser-ADMIN"]):
        findings.append({"path": str(path.relative_to(root)), "rule": "test-harness-in-bundle"})
result = {"source_files": len(files), "bundle_files": len(bundle), "findings": findings}
(Path(__file__).parent / "safety-scan.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
assert not findings
