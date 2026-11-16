"""Attribution, fail-closed clipping, and dependency-free scan regressions."""
from pathlib import Path

import fitz
import pytest

from app.exams.pdf_import import (
    detect_pdf_questions,
    detect_scan_questions,
    graphic_boxes,
    graphics_crop,
    open_question_upload,
    repeated_bands,
    white_horizontal_border,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def reference():
    with fitz.open(FIXTURES / "pdfs/cie_igcse_chem_2_2_atomic_structure_qp.pdf") as doc:
        yield doc, detect_pdf_questions(doc)


@pytest.mark.parametrize("number", [4, 6, 7, 9, 14, 15, 16, 21])
def test_reference_complete_graphics_white_edges(reference, number):
    doc, questions = reference
    question = questions[number - 1]
    assert question.crop_valid, question.warnings
    region = question.regions[0]
    page = doc[region.page - 1]
    rect = fitz.Rect(region.bbox)
    # Independent ownership interval from the numbered text, not the crop itself.
    header = next(w for w in page.get_text("words") if w[4] == str(number) and w[0] < 100)
    next_headers = [w for w in page.get_text("words")
                    if w[4] == str(number + 1) and w[0] < 100 and w[1] > header[1]]
    bottom = next_headers[0][1] - 8 if next_headers else page.rect.height
    owned = [fitz.Rect(d["rect"]) for d in page.get_drawings()
             if not fitz.Rect(d["rect"]).is_empty
             and header[1] - 8 <= d["rect"].y0 < bottom]
    assert owned
    assert all(rect.contains(box) for box in owned)
    pix = page.get_pixmap(clip=rect, dpi=220, alpha=False)
    assert white_horizontal_border(pix)
    text = page.get_text(clip=rect)
    assert "PMT" not in text and "PhysicsAndMathsTutor.com" not in text
    assert "Paper 1" not in text and "Paper 2" not in text


def test_low_drawing_and_straddling_drawing():
    with fitz.open(FIXTURES / "graphics_boundaries.pdf") as doc:
        questions = detect_pdf_questions(doc)
        assert len(questions) == 3
        assert questions[0].crop_valid
        assert fitz.Rect(questions[0].regions[0].bbox).contains(fitz.Rect(100, 190, 250, 290))
        assert not questions[1].crop_valid
        assert any("next question" in w for w in questions[1].warnings)
        assert not questions[2].crop_valid
        assert any("partially clipped" in w for w in questions[2].warnings)


def test_transitive_expansion_and_raster_boxes():
    with fitz.open() as doc:
        page = doc.new_page(width=400, height=500)
        page.insert_text((40, 80), "1 Question")
        page.draw_rect(fitz.Rect(80, 100, 150, 170))
        page.draw_rect(fitz.Rect(100, 165, 180, 220))
        image = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 10, 10), False)
        image.clear_with(0)
        page.insert_image(fitz.Rect(200, 120, 240, 180), pixmap=image)
        boxes = graphic_boxes(page, [])
        rect, _, warnings = graphics_crop(
            page, page.get_text("words"), boxes, 50, 150, 0, 400, 300,
        )
        assert not warnings
        assert rect.y1 == 228
        assert all(rect.contains(box) for box in boxes)


def test_background_empty_and_band_exclusions():
    with fitz.open() as doc:
        page = doc.new_page(width=400, height=500)
        page.draw_rect(page.rect)
        page.draw_line((40, 100), (200, 100))
        page.draw_rect(fitz.Rect(20, 10, 100, 20))
        page.draw_rect(fitz.Rect(20, 460, 100, 480))
        page.draw_rect(fitz.Rect(40, 150, 150, 250))
        assert graphic_boxes(page, [(0, 25), (450, 500)]) == [
            fitz.Rect(39.5, 99.5, 200.5, 100.5), fitz.Rect(40, 150, 150, 250)
        ]
        page.insert_text((40, 80), "1 Question outside the table")
        assert [q.number for q in detect_pdf_questions(doc)] == [1]


def test_pixel_border_guard_for_ink_not_in_graphic_boxes():
    with fitz.open() as doc:
        page = doc.new_page(width=400, height=500)
        page.insert_text((40, 80), "Question")
        # A degenerate line is intentionally excluded from geometric boxes.
        word = page.get_text("words")[0]
        page.draw_line((30, word[3] + 8), (150, word[3] + 8), width=2)
        _, _, warnings = graphics_crop(page, [word], [], 40, 150, 0, 400, None)
        assert any("2px border" in warning for warning in warnings)


def test_scan_png_splits_fixture_and_preserves_content():
    with fitz.open(FIXTURES / "scanned_image_only.pdf") as source:
        png = source[0].get_pixmap(dpi=120, alpha=False).tobytes("png")
    with open_question_upload(png) as doc:
        assert not doc[0].get_text("words")
        questions = detect_scan_questions(doc)
        assert len(questions) == 2
        assert all(q.crop_valid for q in questions)
        assert all("Scan mode" in q.warnings[0] for q in questions)
        for q in questions:
            assert white_horizontal_border(doc[0].get_pixmap(clip=q.regions[0].bbox, dpi=220))


def test_noisy_scan_requires_manual_crop():
    with fitz.open(FIXTURES / "scanned_image_only.pdf") as source:
        pix = source[0].get_pixmap(dpi=120, colorspace=fitz.csGRAY)
    data = bytearray(pix.samples)
    # Five black pixels per row exceed the .3% noise tolerance.
    for y in range(pix.height):
        data[y * pix.stride:y * pix.stride + 5] = b"\0" * 5
    noisy = fitz.Pixmap(fitz.csGRAY, pix.width, pix.height, bytes(data), False)
    with open_question_upload(noisy.tobytes("png")) as doc:
        questions = detect_scan_questions(doc)
        assert len(questions) == 1
        assert not questions[0].crop_valid
        assert any("needs manual crop" in w for w in questions[0].warnings)


def test_only_section_underlines_are_unattributed(reference):
    doc, questions = reference
    bands = repeated_bands(doc)
    unassigned = []
    for index, page in enumerate(doc):
        for box in graphic_boxes(page, bands[index]):
            owners = [q.number for q in questions for r in q.regions
                      if r.page == index + 1 and fitz.Rect(r.bbox).contains(box)]
            if len(owners) != 1:
                unassigned.append((index + 1, tuple(box), owners))
    assert [(page, tuple(round(v, 1) for v in box), owners)
            for page, box, owners in unassigned] == [
        (1, (260.5, 68.8, 311.1, 70.2), []),
        (7, (264.5, 75.1, 314.6, 76.6), []),
    ]
