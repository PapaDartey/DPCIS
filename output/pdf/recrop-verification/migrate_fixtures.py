import json
from pathlib import Path

import fitz

root = Path(__file__).resolve().parents[3]
fixtures = root / "backend/tests/fixtures"
pair = "cie_igcse_chem_2_2_atomic_structure_qp"
destination = fixtures / "pdfs"
archive = destination / "answer-keys"
archive.mkdir(exist_ok=True)
mapping = {
    "atomic_structure_qp.pdf": f"pdfs/{pair}.pdf",
    "atomic_structure_ms.pdf": "pdfs/answer-keys/cie_igcse_chem_2_2_atomic_structure_ms.pdf",
}
for old, new in mapping.items():
    source, target = fixtures / old, fixtures / new
    assert source.resolve().is_relative_to(root) and target.resolve().is_relative_to(root)
    if source.exists():
        assert not target.exists()
        source.rename(target)
for file in [root / "backend/tests" / name for name in
             ("test_exams.py", "test_pdf_import.py", "test_pdf_graphics.py")]:
    text = file.read_text(encoding="utf-8")
    for old, new in mapping.items():
        text = text.replace(old, new)
    file.write_text(text, encoding="utf-8")
file = root / "frontend/tests/importer-browser-verify.mjs"
text = file.read_text(encoding="utf-8").replace('upload("atomic_structure_qp.pdf"',
                                             f'upload("pdfs/{pair}.pdf"')
file.write_text(text, encoding="utf-8")
manifest = destination / f"{pair}.expected.json"
expected = json.loads(manifest.read_text(encoding="utf-8"))
expected["section_counts"] = {"Paper 1": 18, "Paper 2": 6}
expected["excluded_text"] = ["PhysicsAndMathsTutor.com", "PMT", "Paper 1", "Paper 2"]
with fitz.open(fixtures / mapping["atomic_structure_ms.pdf"]) as doc:
    expected["answer_key_text"] = "\n".join(page.get_text() for page in doc)
manifest.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
