"""Source marker masking must leave all other question pixels untouched."""

import json
from pathlib import Path
from uuid import UUID

import fitz
import pytest

from app.attempts import service as attempt_service
from app.exams.models import Question
from app.exams.pdf_question_numbers import find_question_number, mask_png, validate_number_bbox
from app.exams.pdf_storage import (
    load_image,
    load_regions,
    regenerate_crops,
    source_dir,
    student_image_without_number,
)
from test_pdf_option_layout import attempt_env as attempt_env
from test_pdf_option_layout import confirm, preview
from test_pdf_option_layout import pdf_layout_env as pdf_layout_env


def paper(marker="3", *, color=(1, 1, 1), stem="Find the angle marked x."):
    doc = fitz.open()
    page = doc.new_page(width=500, height=500)
    page.draw_rect(page.rect, fill=color, color=color)
    page.insert_text((40, 60), marker + " " + stem, fontsize=12)
    # Geometry extends farther left than the stem, and contains another 3.
    page.draw_polyline([(25, 180), (220, 180), (120, 95), (25, 180)], color=(0, 0, 0))
    page.insert_text((100, 155), "3", fontsize=16)
    page.insert_text((40, 230), "A 3   B 6   C 9   D 12", fontsize=12)
    return doc, fitz.Rect(15, 35, 350, 260)


@pytest.mark.parametrize("marker", ["3", "3.", "3)", "(3)", "Q3", "Q. 3", "Question 3"])
def test_finds_only_expected_leading_marker(marker):
    doc, clip = paper(marker)
    try:
        box = find_question_number(doc[0], clip, 3)
        assert box is not None
        assert fitz.Rect(box).x1 < 115
        assert fitz.Rect(box).y1 < 70
        assert find_question_number(doc[0], clip, 4) is None
    finally:
        doc.close()


@pytest.mark.parametrize("number", [1, 12, 123])
def test_multi_digit_marker(number):
    doc, clip = paper(str(number))
    try:
        assert find_question_number(doc[0], clip, number)
    finally:
        doc.close()


@pytest.mark.parametrize("color", [(1, 1, 1), (0.94, 0.96, 0.93)])
def test_changes_only_marker_pixels_and_keeps_diagram_and_dimensions(color):
    doc, clip = paper(color=color)
    try:
        original = doc[0].get_pixmap(clip=clip, dpi=220, alpha=False).tobytes("png")
        box = find_question_number(doc[0], clip, 3)
        masked = mask_png(original, clip, box)
        before, after = fitz.Pixmap(original), fitz.Pixmap(masked)
        assert (before.width, before.height, before.n) == (after.width, after.height, after.n)
        assert before.samples != after.samples
        changed = []
        a, b = before.samples_mv, after.samples_mv
        for y in range(before.height):
            start = y * before.stride
            if a[start : start + before.stride] != b[start : start + before.stride]:
                changed.append(y)
        assert changed and max(changed) < before.height * 0.2
        word = doc[0].get_text("words")[0]
        left = int((word[0] - clip.x0) * before.width / clip.width)
        right = int((word[2] - clip.x0) * before.width / clip.width) + 1
        for y in changed:
            row = y * before.stride
            assert a[row : row + left * before.n] == b[row : row + left * before.n]
            assert (
                a[row + right * before.n : row + before.stride]
                == b[row + right * before.n : row + before.stride]
            )
        # Full rows below the marker, including the leftward diagram and all answers.
        offset = int(before.height * 0.2) * before.stride
        assert before.samples[offset:] == after.samples[offset:]
        assert mask_png(masked, clip, box) == masked
        assert doc[0].get_text().startswith("3 Find")
    finally:
        doc.close()


def test_no_number_mismatched_number_values_and_cropped_off_marker_are_untouched():
    doc, clip = paper(stem="Use 3 to find the missing angle.")
    try:
        assert find_question_number(doc[0], clip, 4) is None
        original = doc[0].get_pixmap(clip=clip, dpi=150).tobytes("png")
        assert mask_png(original, clip, None) == original
        # A crop of just the diagram must not mistake its numeric label for a header.
        assert find_question_number(doc[0], fitz.Rect(20, 90, 300, 190), 3) is None
        # Removing the source marker from the crop must preserve numeric stem content.
        assert find_question_number(doc[0], fitz.Rect(54, 35, 350, 260), 3) is None
    finally:
        doc.close()


@pytest.mark.parametrize(
    "box",
    [
        [float("nan"), 40, 60, 60],
        [0, 40, 60, 60],
        [40, 40, 450, 200],
        [40, 40, 39, 60],
        [40, 180, 65, 200],
    ],
)
def test_rejects_unsafe_manual_number_rectangles(box):
    with pytest.raises(ValueError):
        validate_number_bbox(box, fitz.Rect(15, 35, 350, 260))


def test_new_crops_and_regeneration_hide_number_without_modifying_source(pdf_layout_env):
    env = pdf_layout_env
    sid = UUID(env.question["source_file_id"])
    original = (source_dir(sid) / "source.pdf").read_bytes()
    regions = load_regions(sid, 1)
    assert regions[0]["number_bbox"]
    first = load_image(sid, 1, 0)
    assert regenerate_crops(sid, 1)[0]["number_bbox"] == regions[0]["number_bbox"]
    assert load_image(sid, 1, 0) == first
    assert (source_dir(sid) / "source.pdf").read_bytes() == original


def test_manual_scan_number_bbox_is_validated_and_persisted(pdf_layout_env):
    env = pdf_layout_env
    sid = UUID(env.question["source_file_id"])
    with fitz.open(source_dir(sid) / "source.pdf") as doc:
        pix = doc[0].get_pixmap(dpi=120, alpha=False)
        scan = fitz.open()
        page = scan.new_page(width=doc[0].rect.width, height=doc[0].rect.height)
        page.insert_image(page.rect, pixmap=pix)
        (source_dir(sid) / "source.pdf").write_bytes(scan.tobytes())
        scan.close()
    region = load_regions(sid, 1)[0]
    region["number_bbox"] = [49, 40, 58, 60]
    result = regenerate_crops(sid, 1, [region], strict=False)
    assert result[0]["number_bbox"] == region["number_bbox"]
    assert json.loads((source_dir(sid) / "1.json").read_text())[0]["number_bbox"]
    region["number_bbox"] = [40, 40, 400, 400]
    with pytest.raises(ValueError):
        regenerate_crops(sid, 1, [region], strict=False)


def test_reference_paper_headers_are_removed_without_touching_scientific_values():
    from app.exams.pdf_import import detect_pdf_questions

    path = Path(__file__).parent / "fixtures/pdfs/cie_igcse_chem_2_2_atomic_structure_qp.pdf"
    with fitz.open(path) as doc:
        questions = detect_pdf_questions(doc)
        assert len(questions) == 24
        for question in questions:
            region = question.regions[0]
            clip = fitz.Rect(region.bbox)
            box = find_question_number(doc[region.page - 1], clip, question.number)
            assert box is not None, question.number
            raw = doc[region.page - 1].get_pixmap(clip=clip, dpi=150, alpha=False).tobytes("png")
            clean = mask_png(raw, clip, box)
            assert fitz.Pixmap(raw).samples != fitz.Pixmap(clean).samples, question.number


@pytest.mark.parametrize("split", [False, True])
def test_old_numbered_images_are_cleaned_for_shuffled_students_only(
    pdf_layout_env, monkeypatch, split
):
    env = pdf_layout_env
    sid = UUID(env.question["source_file_id"])
    raw_images = {}
    with env.session_factory() as db, fitz.open(source_dir(sid) / "source.pdf") as doc:
        for saved in env.exam["questions"]:
            question = db.get(Question, UUID(saved["id"]))
            regions = json.loads(question.image_regions)
            # Simulate records and PNGs imported before number removal existed.
            regions = [{"page": r["page"], "bbox": r["bbox"]} for r in regions]
            question.image_regions = json.dumps(regions)
            region = regions[0]
            data = (
                doc[region["page"] - 1]
                .get_pixmap(clip=region["bbox"], dpi=220, alpha=False)
                .tobytes("png")
            )
            raw_images[question.id] = data
            (source_dir(sid) / f"{question.source_number}-0.png").write_bytes(data)
        db.commit()
    if split:
        prepared = preview(env, "image")
        assert confirm(env, prepared).status_code == 200
        with env.session_factory() as db, fitz.open(source_dir(sid) / "source.pdf") as doc:
            question = db.get(Question, UUID(env.question["id"]))
            manifest = json.loads(question.option_layout)
            region = manifest["layout"]["stem"][0]
            raw = (
                doc[region["page"] - 1]
                .get_pixmap(clip=region["bbox"], dpi=220, alpha=False)
                .tobytes("png")
            )
            from app.exams.pdf_option_layout import layout_directory

            stem_path = layout_directory(sid, UUID(manifest["preview_id"])) / "stem-0.png"
            stem_path.write_bytes(raw)
    exam_url = f"/api/admin/exams/{env.exam['id']}"
    assert (
        env.client.patch(
            exam_url, headers=env.admin_headers, json={"randomize_questions": True}
        ).status_code
        == 200
    )
    assert env.client.post(exam_url + "/publish", headers=env.admin_headers).status_code == 200
    monkeypatch.setattr(attempt_service._SYSTEM_RANDOM, "shuffle", lambda items: items.reverse())
    started = env.client.post(
        f"/api/exams/{env.exam['id']}/attempts", headers=env.student_a_headers
    ).json()
    attempt_url = f"/api/attempts/{started['attempt_id']}"
    delivery = env.client.get(attempt_url, headers=env.student_a_headers).json()
    assert delivery["questions"][0]["id"] == env.exam["questions"][1]["id"]
    for delivered in delivery["questions"]:
        with env.session_factory() as db:
            question = db.get(Question, UUID(delivered["id"]))
            assert not delivered["question_text"].startswith(str(question.source_number) + " ")
            url = delivered["image_urls"][0]
            response = env.client.get(url, headers=env.student_a_headers)
            assert response.status_code == 200
            assert "no-store" in response.headers["cache-control"]
            assert env.client.get(url).status_code == 401
            assert env.client.get(url, headers=env.student_b_headers).status_code == 404
            if split and question.id == UUID(env.question["id"]):
                assert response.content != stem_path.read_bytes()
                assert stem_path.read_bytes() == raw
            else:
                original = load_image(sid, question.source_number, 0)
                assert original == raw_images[question.id]
                assert response.content == student_image_without_number(question, 0, original)
                assert response.content != original
        correct = next(
            o["id"]
            for o in next(q for q in env.exam["questions"] if q["id"] == delivered["id"])["options"]
            if o["is_correct"]
        )
        assert (
            env.client.put(
                attempt_url + f"/answers/{delivered['id']}",
                headers=env.student_a_headers,
                json={"selected_option_id": correct},
            ).status_code
            == 200
        )
    refreshed = env.client.get(attempt_url, headers=env.student_a_headers).json()
    assert refreshed["questions"] == delivery["questions"]
    assert refreshed["expires_at"] == delivery["expires_at"]
    assert (
        env.client.post(attempt_url + "/submit", headers=env.student_a_headers).json()["percentage"]
        == "100.00"
    )


def test_continuation_numbers_and_legacy_unknown_padding_are_preserved(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from uuid import uuid4

    from app.exams.pdf_import import PdfQuestion, PdfRegion
    from app.exams.pdf_storage import store_pdf

    monkeypatch.setenv("EXAM_PDF_STORAGE_DIR", str(tmp_path))
    doc, clip = paper("1")
    page = doc.new_page(width=500, height=500)
    page.insert_text((40, 60), "1 atom remains in the continued diagram.", fontsize=12)
    regions = [PdfRegion(1, tuple(clip)), PdfRegion(2, (15, 35, 350, 130))]
    sid = uuid4()
    store_pdf(sid, doc.tobytes(), [PdfQuestion(number=1, regions=regions)])
    saved = load_regions(sid, 1)
    question = SimpleNamespace(source_file_id=sid, source_number=1, image_regions=json.dumps(saved))
    continuation = load_image(sid, 1, 1)
    assert "number_bbox" not in saved[1]
    assert student_image_without_number(question, 1, continuation) == continuation
    raw = doc[0].get_pixmap(clip=clip + (-2, -2, 2, 2), dpi=220, alpha=False).tobytes("png")
    saved[0].pop("render_bbox")
    saved[0].pop("number_bbox")
    question.image_regions = json.dumps(saved)
    assert student_image_without_number(question, 0, raw) == raw
    doc.close()


def test_rotated_and_two_column_pdf_uses_the_crop_column():
    from app.exams.pdf_import import validate_pdf

    doc = fitz.open()
    page = doc.new_page(width=600, height=500)
    page.insert_text((40, 60), "1 Which item belongs on the left?", fontsize=12)
    page.insert_text((330, 60), "3 Which item belongs on the right?", fontsize=12)
    page.insert_text((330, 100), "A 3   B 4   C 5   D 6", fontsize=12)
    page.set_rotation(90)
    data = doc.tobytes()
    doc.close()
    with validate_pdf(data) as doc:
        left, right = fitz.Rect(30, 35, 295, 140), fitz.Rect(320, 35, 595, 140)
        assert find_question_number(doc[0], left, 1)
        assert find_question_number(doc[0], right, 3)
        assert find_question_number(doc[0], right, 1) is None


def test_numeric_stem_start_after_the_source_header_is_cropped_off_is_not_erased():
    with fitz.open() as doc:
        page = doc.new_page(width=500, height=500)
        page.insert_text((40, 60), "3 Read the diagram below.", fontsize=12)
        page.insert_text((40, 110), "3 sides define this shape.", fontsize=12)
        assert find_question_number(page, fitz.Rect(25, 85, 350, 185), 3) is None


def test_number_area_api_rejects_invalid_and_unauthorized_changes(pdf_layout_env):
    env = pdf_layout_env
    sid = UUID(env.question["source_file_id"])
    url = f"/api/admin/exams/{env.exam['id']}/sources/{sid}/questions/1/crops"
    before = load_image(sid, 1, 0)
    region = load_regions(sid, 1)[0]
    region["number_bbox"] = [0, 0, 500, 500]
    payload = {"regions": [region], "strict": False}
    assert env.client.put(url, headers=env.student_a_headers, json=payload).status_code == 403
    assert env.client.put(url, json=payload).status_code == 401
    assert env.client.put(url, headers=env.admin_headers, json=payload).status_code == 422
    assert load_image(sid, 1, 0) == before
