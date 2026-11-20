"""API regressions for option shuffling, saved sittings, grading, and PDF figures.

Expected behavior: text choices move only when enabled; their IDs and correctness
stay attached to their content. Loading/resuming never reshuffles or resets time.
PDF choices remain positional because their letters are embedded in the image.
All tests use the existing in-memory SQLite fixture and temporary PDF storage.
"""

from pathlib import Path
from types import SimpleNamespace

import fitz
import pytest

from app.attempts import service as attempt_service
from test_attempts import (
    ACTIVE_FORBIDDEN_KEYS,
    _assert_no_keys,
    _create_and_publish_exam,
    _sample_question,
)
from test_attempts import (
    attempt_env as attempt_env,
)


def _angle_question() -> dict:
    question = _sample_question("Find angle x", position=1, correct_label="B")
    for option, value in zip(question["options"], ["60°", "70°", "80°", "90°"], strict=True):
        option["option_text"] = value
    return question


def _start(env: SimpleNamespace, exam_id: str, headers: dict) -> str:
    response = env.client.post(f"/api/exams/{exam_id}/attempts", headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["attempt_id"]


def _delivery(env: SimpleNamespace, attempt_id: str, headers: dict) -> dict:
    response = env.client.get(f"/api/attempts/{attempt_id}", headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    _assert_no_keys(payload, ACTIVE_FORBIDDEN_KEYS)
    return payload


def _save_correct_and_submit(
    env: SimpleNamespace, exam: dict, delivery: dict, headers: dict
) -> dict:
    attempt_id = delivery["attempt_id"]
    for question in exam["questions"]:
        correct_id = next(option["id"] for option in question["options"] if option["is_correct"])
        saved = env.client.put(
            f"/api/attempts/{attempt_id}/answers/{question['id']}",
            headers=headers,
            json={"selected_option_id": correct_id},
        )
        assert saved.status_code == 200, saved.text
    response = env.client.post(f"/api/attempts/{attempt_id}/submit", headers=headers)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["percentage"] == "100.00"
    assert result["correct_answers"] == len(exam["questions"])
    assert result["incorrect_answers"] == 0
    assert result["unanswered_questions"] == 0
    return result


@pytest.mark.parametrize("enabled", [False, True], ids=["disabled", "enabled"])
def test_option_setting_moves_content_and_preserves_correctness_on_resume(
    attempt_env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, enabled: bool
) -> None:
    env = attempt_env
    headers = env.student_a_headers
    exam = _create_and_publish_exam(
        env,
        randomize_options=enabled,
        show_correct_answers=True,
        questions=[_angle_question()],
    )
    # Force a known non-identity permutation, avoiding a flaky "must differ" check.
    monkeypatch.setattr(attempt_service._SYSTEM_RANDOM, "shuffle", lambda values: values.reverse())
    attempt_id = _start(env, exam["id"], headers)
    delivered = _delivery(env, attempt_id, headers)
    question = delivered["questions"][0]
    original_ids = [option["id"] for option in exam["questions"][0]["options"]]
    expected_ids = list(reversed(original_ids)) if enabled else original_ids
    assert [option["id"] for option in question["options"]] == expected_ids
    assert [option["label"] for option in question["options"]] == ["A", "B", "C", "D"]
    assert [option["option_text"] for option in question["options"]] == (
        ["90°", "80°", "70°", "60°"] if enabled else ["60°", "70°", "80°", "90°"]
    )
    correct = next(option for option in question["options"] if option["option_text"] == "70°")
    assert correct["id"] == original_ids[1]
    assert correct["label"] == ("C" if enabled else "B")
    saved = env.client.put(
        f"/api/attempts/{attempt_id}/answers/{question['id']}",
        headers=headers,
        json={"selected_option_id": correct["id"]},
    )
    assert saved.status_code == 200, saved.text

    def unexpected_shuffle(_values: list) -> None:
        pytest.fail("Loading or resuming an existing sitting must not reshuffle")

    monkeypatch.setattr(attempt_service._SYSTEM_RANDOM, "shuffle", unexpected_shuffle)
    resumed = env.client.post(f"/api/exams/{exam['id']}/attempts", headers=headers)
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["attempt_id"] == attempt_id
    assert resumed.json()["resumed"] is True
    refreshed = _delivery(env, attempt_id, headers)
    assert refreshed["questions"] == delivered["questions"]
    assert refreshed["started_at"] == delivered["started_at"]
    assert refreshed["expires_at"] == delivered["expires_at"]
    assert refreshed["saved_answers"] == {question["id"]: correct["id"]}
    result = _save_correct_and_submit(env, exam, delivered, headers)
    review = result["question_review"][0]
    assert review["selected_option_id"] == correct["id"]
    assert review["correct_option_id"] == correct["id"]
    assert [option["id"] for option in review["options"]] == expected_ids
    print(
        f"\nShuffle {'ON' if enabled else 'OFF'}: "
        f"{[option['option_text'] for option in question['options']]}; "
        f"70° displayed as {correct['label']}; refresh/resume stable; grade 100%."
    )


def test_real_randomizer_valid_stable_orders_and_grades_for_multiple_students(
    attempt_env: SimpleNamespace,
) -> None:
    env = attempt_env
    exam = _create_and_publish_exam(
        env, randomize_options=True, max_attempts=8, questions=[_angle_question()]
    )
    original_ids = {option["id"] for option in exam["questions"][0]["options"]}
    orders: set[tuple[str, ...]] = set()
    attempts: set[str] = set()
    for headers in [env.student_a_headers, env.student_b_headers]:
        for _ in range(8):
            attempt_id = _start(env, exam["id"], headers)
            assert attempt_id not in attempts
            attempts.add(attempt_id)
            delivered = _delivery(env, attempt_id, headers)
            options = delivered["questions"][0]["options"]
            assert {option["id"] for option in options} == original_ids
            assert [option["label"] for option in options] == ["A", "B", "C", "D"]
            orders.add(tuple(option["option_text"] for option in options))
            refreshed = _delivery(env, attempt_id, headers)
            assert refreshed["questions"] == delivered["questions"]
            assert refreshed["expires_at"] == delivered["expires_at"]
            _save_correct_and_submit(env, exam, delivered, headers)
    # Randomness permits repeated permutations, including the original order.
    # Actual movement is asserted deterministically by the enabled-setting test.
    print(
        f"\nReal RNG: {len(attempts)} independent attempts across 2 students; "
        f"{len(orders)} distinct option orders observed; all stable and graded 100%."
    )


def test_mixed_pdf_figures_keep_printed_choices_while_text_options_shuffle(
    attempt_env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env = attempt_env
    headers = env.student_a_headers
    monkeypatch.setenv("EXAM_PDF_STORAGE_DIR", str(tmp_path))
    draft = _create_and_publish_exam(
        env, randomize_options=True, show_correct_answers=True, publish=False
    )
    fixtures = Path(__file__).parent / "fixtures/pdfs"
    with fitz.open(fixtures / "answer-keys/cie_igcse_chem_2_2_atomic_structure_ms.pdf") as doc:
        key_text = doc[0].get_text()
    uploaded = env.client.post(
        f"/api/admin/exams/{draft['id']}/import-pdf",
        headers=env.admin_headers,
        files={
            "file": (
                "figure-paper.pdf",
                (fixtures / "cie_igcse_chem_2_2_atomic_structure_qp.pdf").read_bytes(),
                "application/pdf",
            )
        },
        data={"answer_key_text": key_text},
    )
    assert uploaded.status_code == 200, uploaded.text
    # These two corpus questions contain diagram/table answer choices in the PDF.
    preview = [uploaded.json()["valid_questions"][index] for index in [3, 5]]
    questions = [
        {
            "question_text": item["question_text"],
            "source_file_id": item["source_file_id"],
            "source_number": item["source_number"],
            "position": index + 1,
            "points": item["points"],
            "options": [
                {**option, "is_correct": option["label"] == item["answer_label"]}
                for option in item["options"]
            ],
        }
        for index, item in enumerate(preview)
    ]
    text_question = _angle_question()
    text_question["position"] = 3
    saved = env.client.put(
        f"/api/admin/exams/{draft['id']}/questions",
        headers=env.admin_headers,
        json={"questions": [*questions, text_question]},
    )
    assert saved.status_code == 200, saved.text
    exam = saved.json()
    assert exam["randomize_options"] is True
    published = env.client.post(
        f"/api/admin/exams/{exam['id']}/publish", headers=env.admin_headers
    )
    assert published.status_code == 200, published.text
    monkeypatch.setattr(attempt_service._SYSTEM_RANDOM, "shuffle", lambda values: values.reverse())
    delivered = _delivery(env, _start(env, exam["id"], headers), headers)
    for index, (author, question) in enumerate(
        zip(exam["questions"], delivered["questions"], strict=True)
    ):
        assert question["id"] == author["id"]
        original_ids = [option["id"] for option in author["options"]]
        expected_ids = original_ids if index < 2 else list(reversed(original_ids))
        assert [option["id"] for option in question["options"]] == expected_ids
        assert [option["label"] for option in question["options"]] == ["A", "B", "C", "D"]
        if index < 2:
            assert question["image_urls"]
            original_image = env.client.get(
                preview[index]["image_urls"][0], headers=env.admin_headers
            )
            student_image = env.client.get(question["image_urls"][0], headers=headers)
            assert original_image.status_code == student_image.status_code == 200
            assert student_image.content.startswith(b"\x89PNG")
            assert student_image.content == original_image.content
        else:
            assert question["image_urls"] == []
    refreshed = _delivery(env, delivered["attempt_id"], headers)
    assert refreshed["questions"] == delivered["questions"]
    result = _save_correct_and_submit(env, exam, delivered, headers)
    for review, question in zip(result["question_review"], delivered["questions"], strict=True):
        assert [option["id"] for option in review["options"]] == [
            option["id"] for option in question["options"]
        ]
    print(
        "\nMixed exam: 2 PDF figure questions stayed fixed; "
        "text shuffled; images matched; grade 100%."
    )
