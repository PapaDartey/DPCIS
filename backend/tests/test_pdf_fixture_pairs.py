"""Drop a PDF and matching expected JSON here to extend importer acceptance.

Independent expectations cover detection, sections, text/layout, key parsing,
retained graphic containment and rendered white borders. Mark-scheme text is
stored in JSON, so a new paper requires exactly two files and no Python edits.
"""

import json
import re
from collections import Counter
from pathlib import Path

import fitz
import pytest

from app.exams.parser import parse_questions_with_answer_key
from app.exams.pdf_import import (
    detect_pdf_questions,
    graphic_boxes,
    repeated_bands,
    validate_pdf,
    white_horizontal_border,
)

FIXTURES = Path(__file__).parent / "fixtures" / "pdfs"
PAIRS = sorted(FIXTURES.glob("*.expected.json"))


@pytest.mark.parametrize(
    "manifest_path", PAIRS, ids=lambda p: p.name.removesuffix(".expected.json")
)
def test_pdf_fixture_pair(manifest_path: Path) -> None:
    expected = json.loads(manifest_path.read_text(encoding="utf-8"))
    paper = manifest_path.with_name(manifest_path.name.replace(".expected.json", ".pdf"))
    assert paper.is_file(), f"Missing PDF partner: {paper.name}"
    # Fail rather than silently skip a PDF with no manifest.
    assert {p.stem for p in FIXTURES.glob("*.pdf")} == {
        p.name.removesuffix(".expected.json") for p in PAIRS
    }
    with validate_pdf(paper.read_bytes()) as doc:
        questions = detect_pdf_questions(doc)
        assert [q.number for q in questions] == [int(n) for n in expected["questions"]]
        counts = dict(Counter(q.section or "Unsectioned" for q in questions))
        assert counts == expected["section_counts"]
        if "page_count" in expected:
            assert len(doc) == expected["page_count"]
        bands = repeated_bands(doc)
        for question in questions:
            item = expected["questions"][str(question.number)]
            assert question.crop_valid, (question.number, question.warnings)
            assert question.regions[0].page == item["page"]
            assert question.options_kind == item["options_kind"]
            text = re.sub(r"\s+", " ", question.extracted_text).strip()
            text = re.sub(rf"^{question.number}\s+", "", text)
            assert text.startswith(item["first_words"])
            for region in question.regions:
                page = doc[region.page - 1]
                clip = fitz.Rect(region.bbox)
                for graphic in graphic_boxes(page, bands[region.page - 1]):
                    assert not graphic.intersects(clip) or clip.contains(graphic)
                assert white_horizontal_border(page.get_pixmap(clip=clip, dpi=220, alpha=False))
                crop_text = page.get_text(clip=clip)
                for forbidden in expected.get("excluded_text", []):
                    assert forbidden not in crop_text
                # Any full text line identified as a repeated header/footer must
                # stay outside the region, independent of its wording.
                for word in page.get_text("words"):
                    if any(word[1] >= top and word[3] <= bottom
                           for top, bottom in bands[region.page - 1]):
                        assert not clip.intersects(fitz.Rect(word[:4]))
    key_text = expected.get("answer_key_text") or "\n".join(
        f"{n} {answer}" for n, answer in expected["expected_key"].items()
    )
    # Image-only options deliberately use labels; never infer answers from art.
    prompts = "\n".join(f"{n} Fixture question\nA. One\nB. Two\nC. Three\nD. Four"
                        for n in expected["questions"])
    parsed = parse_questions_with_answer_key(prompts, key_text)
    assert not parsed.invalid_questions
    actual_key = {str(q.position): q.answer_label for q in parsed.valid_questions}
    assert actual_key == expected["expected_key"]
