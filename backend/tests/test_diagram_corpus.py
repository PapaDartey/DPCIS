"""Independent geometry oracle; warning cases are not counted as correct crops."""

import json
from pathlib import Path

import fitz
import pytest

from app.exams.pdf_import import (
    detect_pdf_questions,
    detect_scan_questions,
    open_question_upload,
    white_crop_border,
)

ROOT = Path(__file__).parent / "fixtures/pdfs/synthetic"
MANIFESTS = sorted(ROOT.glob("*.expected.json"))


@pytest.mark.parametrize("manifest", MANIFESTS, ids=lambda p: p.name.split(".")[0])
def test_diagram_corpus(manifest):
    spec = json.loads(manifest.read_text())
    with fitz.open(manifest.with_name(manifest.name.replace(".expected.json", ".pdf"))) as doc:
        if spec.get("scan"):
            questions = detect_scan_questions(doc)
            assert questions and all(q.warnings for q in questions)
            suffix = ".png" if spec["dpi"] == 150 else ".jpg"
            with open_question_upload(
                manifest.with_name(manifest.name.replace(".expected.json", suffix)).read_bytes()
            ) as image:
                assert all(q.warnings for q in detect_scan_questions(image))
            return
        questions = detect_pdf_questions(doc)
        assert [q.number for q in questions] == list(map(int, spec["questions"]))
        if spec["review_expected"]:
            assert any(q.warnings for q in questions), "Ambiguity must not be silent"
        for q in questions:
            wanted = spec["questions"][str(q.number)]
            defects = []
            for owned in wanted["must_contain_rects"]:
                if not any(
                    r.page == owned["page"] and fitz.Rect(r.bbox).contains(fitz.Rect(owned["bbox"]))
                    for r in q.regions
                ):
                    defects.append(f"missing owned region {owned}")
            for r in q.regions:
                page = doc[r.page - 1]
                clip = fitz.Rect(r.bbox)
                if not white_crop_border(page.get_pixmap(clip=clip, dpi=220, alpha=False)):
                    defects.append("nonwhite border")
                text = page.get_text(clip=clip)
                for other in spec["questions"]:
                    if other != str(q.number) and f"Question {other}" in text:
                        defects.append(f"contains neighbour {other}")
                for banned in ("EXAM HEADER", "PAGE FOOTER", "WATERMARK"):
                    if banned in text:
                        defects.append(f"contains {banned}")
            # Unsupported geometry must be explicitly listed, and never silently accepted.
            if defects:
                assert spec.get("known_limit"), (manifest.name, q.number, defects, q.warnings)
                assert q.warnings, (q.number, defects)
            else:
                assert q.regions


def test_coverage_catches_dropped_graphic(monkeypatch):
    import app.exams.pdf_import as importer

    with fitz.open() as doc:
        page = doc.new_page(width=400, height=500)
        page.insert_text((40, 80), "1 Question with remote drawing")
        page.insert_text((40, 100), "A one B two C three D four")
        page.draw_rect((100, 170, 220, 240), fill=(0, 0, 0))
        monkeypatch.setattr(importer, "graphic_boxes", lambda *args: [])
        q = importer.detect_pdf_questions(doc)[0]
        assert any("Unassigned content on page 1" in w for w in q.warnings)


def test_manual_side_clipping_and_same_page_regions(tmp_path, monkeypatch):
    from uuid import uuid4

    from app.exams.pdf_import import PdfQuestion, PdfRegion
    from app.exams.pdf_storage import regenerate_crops, store_pdf

    monkeypatch.setenv("EXAM_PDF_STORAGE_DIR", str(tmp_path))
    with fitz.open() as doc:
        page = doc.new_page(width=400, height=500)
        page.draw_rect((60, 70, 130, 130))
        page.draw_rect((210, 250, 290, 310))
        source_id = uuid4()
        store_pdf(source_id, doc.tobytes(), [PdfQuestion(1, [PdfRegion(1, (40, 50, 150, 150))])])
        regions = [
            {"page": 1, "bbox": [40, 50, 150, 150]},
            {"page": 1, "bbox": [190, 230, 310, 330]},
        ]
        assert len(regenerate_crops(source_id, 1, regions)) == 2
        with pytest.raises(ValueError, match="clipped|border"):
            regenerate_crops(source_id, 1, [{"page": 1, "bbox": [90, 50, 150, 150]}])
