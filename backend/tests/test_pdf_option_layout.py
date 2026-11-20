"""Behavioral tests for reviewed PDF answer separation, not production data."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import fitz
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

from app.attempts import service as attempt_service
from app.exams.models import Question
from app.exams.pdf_option_layout import (
    LayoutInput,
    LayoutRegion,
    render_layout,
    suggest_layout,
)
from test_attempts import (
    _assert_no_keys,
    _create_and_publish_exam,
    _sample_question,
)
from test_attempts import (
    attempt_env as attempt_env,
)


def triangle_pdf(*, horizontal: bool = False, diagrams: bool = False) -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 55), "1 In the triangle shown, find the angle marked x.", fontsize=12)
    page.draw_polyline(
        [(200, 100), (110, 230), (290, 230), (200, 100)],
        color=(0, 0, 0),
        fill=(0.85, 0.93, 1),
        width=1,
    )
    for point, value in [((135, 215), "50°"), ((250, 215), "60°"), ((197, 130), "x")]:
        page.insert_text(point, value, fontsize=12)
    for index, (label, value) in enumerate(zip("ABCD", ["60°", "70°", "80°", "90°"], strict=True)):
        x, y = (70 + 120 * index, 300) if horizontal else (70, 300 + 40 * index)
        page.insert_text((x, y), label + ".", fontsize=12)
        if diagrams:
            page.draw_circle((x + 30, y + 40), 13 + index, color=(0, 0, 0), width=1)
        else:
            page.insert_text((x + 30, y), value, fontsize=12)
    page.insert_text((50, 510), "2 Choose the smallest number.", fontsize=12)
    for index, label in enumerate("ABCD"):
        page.insert_text((70, 550 + 40 * index), label + ".", fontsize=12)
        page.insert_text((100, 550 + 40 * index), str(index + 1), fontsize=12)
    data = doc.tobytes()
    doc.close()
    return data


def fake_question(*, horizontal: bool = False, diagrams: bool = False):
    return SimpleNamespace(
        source_file_id=uuid4(),
        source_number=1,
        option_layout=None,
        question_text="Find angle x",
        image_regions=json.dumps(
            [{"page": 1, "bbox": [40, 35, 575, 380 if horizontal else 485 if diagrams else 450]}]
        ),
        pdf_options_text=json.dumps(dict(zip("ABCD", ["60°", "70°", "80°", "90°"], strict=True))),
        options=[
            SimpleNamespace(label=label, position=i, option_text=str(i))
            for i, label in enumerate("ABCD")
        ],
    )


@pytest.mark.parametrize("horizontal,diagrams", [(False, False), (True, False), (True, True)])
def test_suggested_crops_exclude_letters_preserve_figure_and_render(horizontal, diagrams):
    question = fake_question(horizontal=horizontal, diagrams=diagrams)
    with fitz.open(stream=triangle_pdf(horizontal=horizontal, diagrams=diagrams)) as doc:
        layout, warnings = suggest_layout(doc, question)
        assert warnings == []
        assets = render_layout(doc, question, layout)
        assert set(assets) == {"stem-0.png", "A-0.png", "B-0.png", "C-0.png", "D-0.png"}
        stem = fitz.Rect(layout.stem[0].bbox)
        assert stem.contains(fitz.Rect(109, 99, 291, 231))
        for option in layout.options:
            region = fitz.Rect(option.regions[0].bbox)
            words = doc[0].get_text("words", clip=region)
            assert not any(w[4].rstrip(".") in "ABCD" for w in words)
            image = fitz.Pixmap(assets[f"{option.label}-0.png"])
            assert image.width > 10 and image.height > 10
            if not diagrams:
                assert image.width < 160  # Empty paper margins are trimmed for mobile readability.


@pytest.mark.parametrize("failure", ["overlap", "outside", "blank", "letter", "tiny", "nan"])
def test_invalid_crop_proposals_are_rejected(failure):
    question = fake_question()
    with fitz.open(stream=triangle_pdf()) as doc:
        layout, _ = suggest_layout(doc, question)
        with pytest.raises(ValueError):
            if failure == "nan":
                LayoutRegion(page=1, bbox=[0, float("nan"), 200, 100])
            else:
                layout.options[0].regions = [
                    LayoutRegion(
                        page=1,
                        bbox={
                            "overlap": layout.options[1].regions[0].bbox,
                            "outside": [600, 280, 650, 320],
                            "blank": [400, 100, 450, 150],
                            "letter": [65, 280, 140, 320],
                            "tiny": [100, 280, 101, 281],
                        }[failure],
                    )
                ]
                render_layout(doc, question, layout)


def test_ambiguous_labels_require_manual_review():
    question = fake_question()
    with fitz.open(stream=triangle_pdf()) as doc:
        doc[0].insert_text((150, 180), "A", fontsize=12)
        layout, warnings = suggest_layout(doc, question)
        assert warnings
        with pytest.raises(ValueError, match="overlap"):
            render_layout(doc, question, layout)


def test_scanned_pdf_requires_manual_regions_and_can_preserve_answers():
    question = fake_question()
    with fitz.open(stream=triangle_pdf()) as original:
        manual, _ = suggest_layout(original, question)
        pix = original[0].get_pixmap(dpi=120)
        with fitz.open() as scanned:
            page = scanned.new_page(width=595, height=842)
            page.insert_image(page.rect, pixmap=pix)
            _, warnings = suggest_layout(scanned, question)
            assert warnings
            assets = render_layout(scanned, question, manual)
            assert len(assets) == 5


def test_manual_layout_can_span_pages_without_merging_answer_images():
    question = fake_question()
    question.image_regions = json.dumps(
        [
            {"page": 1, "bbox": [0, 0, 300, 400]},
            {"page": 2, "bbox": [0, 0, 300, 400]},
        ]
    )
    with fitz.open() as doc:
        doc.new_page(width=300, height=400).insert_text((40, 50), "Question and figure")
        page = doc.new_page(width=300, height=400)
        options = []
        for index, label in enumerate("ABCD"):
            y = 60 + 65 * index
            page.insert_text((30, y), label + ".")
            page.insert_text((70, y), str(index + 1))
            options.append(
                {
                    "label": label,
                    "mode": "image",
                    "option_text": str(index + 1),
                    "regions": [{"page": 2, "bbox": [60, y - 20, 130, y + 10]}],
                }
            )
        manual = LayoutInput.model_validate(
            {"stem": [{"page": 1, "bbox": [25, 25, 250, 80]}], "options": options}
        )
        assert len(render_layout(doc, question, manual)) == 5


@pytest.fixture
def pdf_layout_env(attempt_env, monkeypatch, tmp_path):
    env = attempt_env
    monkeypatch.setenv("EXAM_PDF_STORAGE_DIR", str(tmp_path))
    draft = _create_and_publish_exam(
        env,
        publish=False,
        randomize_options=True,
        show_correct_answers=True,
        questions=[_sample_question("Temporary draft", position=1)],
    )
    uploaded = env.client.post(
        f"/api/admin/exams/{draft['id']}/import-pdf",
        headers=env.admin_headers,
        files={"file": ("triangles.pdf", triangle_pdf(), "application/pdf")},
        data={"answer_key_text": "1 B\n2 A"},
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["valid_count"] == 2, uploaded.json()
    questions = []
    for item in uploaded.json()["valid_questions"]:
        questions.append(
            {
                "question_text": item["question_text"],
                "source_file_id": item["source_file_id"],
                "source_number": item["source_number"],
                "pdf_options_text": item["pdf_options_text"],
                "position": len(questions),
                "points": "2.00",
                "options": [
                    {**o, "is_correct": o["label"] == item["answer_label"]} for o in item["options"]
                ],
            }
        )
    saved = env.client.put(
        f"/api/admin/exams/{draft['id']}/questions",
        headers=env.admin_headers,
        json={"questions": questions},
    )
    assert saved.status_code == 200, saved.text
    env.exam = saved.json()
    env.question = env.exam["questions"][0]
    env.base = f"/api/admin/exams/{draft['id']}/questions/{env.question['id']}/option-layout"
    yield env


def preview(env, mode="image"):
    first = env.client.post(env.base + "/preview", headers=env.admin_headers, json={})
    assert first.status_code == 200, first.text
    assert first.json()["valid"] is True, first.json()
    payload = {
        "stem": first.json()["layout"]["stem"],
        "options": [
            {k: v for k, v in o.items() if k != "image_urls"}
            for o in first.json()["layout"]["options"]
        ],
    }
    for option in payload["options"]:
        option["mode"] = mode
    response = env.client.post(
        env.base + "/preview", headers=env.admin_headers, json={"layout": payload}
    )
    assert response.status_code == 200, response.text
    return response.json()


def confirm(env, prepared):
    return env.client.post(
        env.base + "/confirm",
        headers=env.admin_headers,
        json={"preview_id": prepared["preview_id"], "confirm": True},
    )


@pytest.mark.parametrize("mode", ["text", "image"])
def test_review_confirm_shuffle_resume_assets_and_grading(pdf_layout_env, monkeypatch, mode):
    env = pdf_layout_env
    original = env.client.get(env.question["image_urls"][0], headers=env.admin_headers).content
    prepared = preview(env, mode)
    detail = env.client.get(f"/api/admin/exams/{env.exam['id']}", headers=env.admin_headers)
    assert detail.json()["questions"][0]["option_layout"] is None
    before_ids = [o["id"] for o in env.question["options"]]
    approved = confirm(env, prepared)
    assert approved.status_code == 200, approved.text
    assert approved.json()["option_layout"]
    assert [o["id"] for o in approved.json()["options"]] == before_ids
    assert approved.json()["points"] == env.question["points"]
    assert [o["is_correct"] for o in approved.json()["options"]] == [False, True, False, False]
    assert confirm(env, prepared).json() == approved.json()
    assert (
        env.client.get(env.question["image_urls"][0], headers=env.admin_headers).content == original
    )
    admin_images = {
        label: env.client.get(o["image_urls"][0], headers=env.admin_headers).content
        for label, o in zip("ABCD", prepared["layout"]["options"], strict=True)
    }
    assert (
        env.client.delete(
            env.base + f"/preview/{prepared['preview_id']}", headers=env.admin_headers
        ).status_code
        == 409
    )
    published = env.client.post(
        f"/api/admin/exams/{env.exam['id']}/publish", headers=env.admin_headers
    )
    assert published.status_code == 200, published.text
    assert confirm(env, prepared).status_code == 409
    monkeypatch.setattr(attempt_service._SYSTEM_RANDOM, "shuffle", lambda values: values.reverse())
    started = env.client.post(
        f"/api/exams/{env.exam['id']}/attempts", headers=env.student_a_headers
    )
    assert started.status_code == 201, started.text
    attempt_id = started.json()["attempt_id"]
    response = env.client.get(f"/api/attempts/{attempt_id}", headers=env.student_a_headers)
    assert response.status_code == 200, response.text
    delivered = response.json()
    _assert_no_keys(
        delivered, {"is_correct", "correct_option_id", "source_file_id", "option_layout"}
    )
    q = delivered["questions"][0]
    assert q["options_in_image"] is False
    assert [o["id"] for o in q["options"]] == list(reversed(before_ids))
    assert [o["option_text"] for o in q["options"]] == ["90°", "80°", "70°", "60°"]
    assert [o["label"] for o in q["options"]] == list("ABCD")
    assert delivered["questions"][1]["options_in_image"] is True
    stem = env.client.get(q["image_urls"][0], headers=env.student_a_headers)
    assert stem.status_code == 200 and stem.content != original
    for index, o in enumerate(q["options"]):
        assert bool(o["image_urls"]) == (mode == "image")
        if mode == "image":
            url = o["image_urls"][0]
            image = env.client.get(url, headers=env.student_a_headers)
            assert image.status_code == 200
            assert image.content == admin_images["DCBA"[index]]
            assert env.client.get(url, headers=env.student_b_headers).status_code == 404
            assert env.client.get(url).status_code == 401
            assert env.client.get(url, headers=env.admin_headers).status_code == 403
            foreign_id = env.exam["questions"][1]["options"][0]["id"]
            assert (
                env.client.get(
                    url.replace(o["id"], foreign_id), headers=env.student_a_headers
                ).status_code
                == 404
            )
    saved = env.client.put(
        f"/api/attempts/{attempt_id}/answers/{q['id']}",
        headers=env.student_a_headers,
        json={"selected_option_id": before_ids[1]},
    )
    assert saved.status_code == 200
    resumed = env.client.post(
        f"/api/exams/{env.exam['id']}/attempts", headers=env.student_a_headers
    )
    assert resumed.status_code == 200 and resumed.json()["attempt_id"] == attempt_id
    refreshed = env.client.get(f"/api/attempts/{attempt_id}", headers=env.student_a_headers).json()
    assert refreshed["questions"] == delivered["questions"]
    assert refreshed["expires_at"] == delivered["expires_at"]
    assert refreshed["saved_answers"][q["id"]] == before_ids[1]
    result = env.client.post(f"/api/attempts/{attempt_id}/submit", headers=env.student_a_headers)
    assert result.status_code == 200
    assert result.json()["percentage"] == "50.00"
    review = result.json()["question_review"][0]
    assert review["is_correct"] is True and review["correct_option_id"] == before_ids[1]
    assert [o["id"] for o in review["options"]] == list(reversed(before_ids))
    if mode == "image":
        assert (
            env.client.get(
                q["options"][0]["image_urls"][0], headers=env.student_a_headers
            ).status_code
            == 404
        )


def test_preview_role_scope_staleness_and_discard(pdf_layout_env):
    env = pdf_layout_env
    assert env.client.post(env.base + "/preview", json={}).status_code == 401
    assert (
        env.client.post(env.base + "/preview", headers=env.student_a_headers, json={}).status_code
        == 403
    )
    prepared = preview(env)
    other = _create_and_publish_exam(env, publish=False)
    wrong_base = env.base.replace(env.exam["id"], other["id"])
    assert (
        env.client.post(
            wrong_base + "/confirm",
            headers=env.admin_headers,
            json={"preview_id": prepared["preview_id"], "confirm": True},
        ).status_code
        == 404
    )
    assert (
        env.client.get(
            prepared["layout"]["stem_urls"][0], headers=env.student_a_headers
        ).status_code
        == 403
    )
    with env.session_factory() as db:
        question = db.get(Question, UUID(env.question["id"]))
        question.points = 3
        db.commit()
    assert confirm(env, prepared).status_code == 409
    discarded = env.client.delete(
        env.base + f"/preview/{prepared['preview_id']}", headers=env.admin_headers
    )
    assert discarded.status_code == 204
    assert confirm(env, prepared).status_code == 404
    assert (
        env.client.get(prepared["layout"]["stem_urls"][0], headers=env.admin_headers).status_code
        == 404
    )


def test_bulk_save_preserves_reviewed_layout_only_for_unchanged_content(pdf_layout_env):
    env = pdf_layout_env
    assert confirm(env, preview(env, "text")).status_code == 200
    url = f"/api/admin/exams/{env.exam['id']}"
    current = env.client.get(url, headers=env.admin_headers).json()
    payload = {"questions": current["questions"]}
    saved = env.client.put(url + "/questions", headers=env.admin_headers, json=payload)
    assert saved.status_code == 200, saved.text
    question = saved.json()["questions"][0]
    assert question["option_layout"]
    assert (
        env.client.get(
            question["option_layout"]["stem_urls"][0], headers=env.admin_headers
        ).status_code
        == 200
    )
    payload = {"questions": saved.json()["questions"]}
    payload["questions"][0]["options"][0]["option_text"] = "Edited answer"
    changed = env.client.put(url + "/questions", headers=env.admin_headers, json=payload)
    assert changed.status_code == 200, changed.text
    assert changed.json()["questions"][0]["option_layout"] is None


def test_unreviewed_empty_descriptions_invalid_regions_and_forged_confirmation_fail(pdf_layout_env):
    env = pdf_layout_env
    prepared = preview(env)
    assert (
        env.client.post(
            env.base + "/confirm",
            headers=env.admin_headers,
            json={"preview_id": prepared["preview_id"]},
        ).status_code
        == 422
    )
    assert (
        env.client.post(
            env.base + "/confirm",
            headers=env.admin_headers,
            json={
                "preview_id": prepared["preview_id"],
                "confirm": True,
                "is_correct": True,
            },
        ).status_code
        == 422
    )
    layout = {
        "stem": prepared["layout"]["stem"],
        "options": [
            {k: v for k, v in o.items() if k != "image_urls"} for o in prepared["layout"]["options"]
        ],
    }
    layout["options"][0]["option_text"] = ""
    empty = env.client.post(
        env.base + "/preview", headers=env.admin_headers, json={"layout": layout}
    )
    assert empty.status_code == 200
    assert confirm(env, empty.json()).status_code == 422
    layout["options"][0]["regions"] = layout["options"][1]["regions"]
    invalid = env.client.post(
        env.base + "/preview", headers=env.admin_headers, json={"layout": layout}
    )
    assert invalid.status_code == 422
    current = env.client.get(f"/api/admin/exams/{env.exam['id']}", headers=env.admin_headers)
    assert current.json()["questions"][0]["option_layout"] is None


def test_migration_adds_nullable_column_without_changing_existing_rows(tmp_path):
    path = Path(__file__).parents[1] / "alembic/versions/0009_pdf_option_layout.py"
    spec = importlib.util.spec_from_file_location("option_layout_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.sqlite'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE questions (id INTEGER PRIMARY KEY)"))
        connection.execute(text("INSERT INTO questions (id) VALUES (1)"))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert (
            connection.execute(text("SELECT option_layout FROM questions WHERE id=1")).scalar()
            is None
        )
        assert inspect(connection).get_columns("questions")[1]["nullable"] is True
        migration.downgrade()
        assert connection.execute(text("SELECT COUNT(*) FROM questions")).scalar() == 1
    engine.dispose()
