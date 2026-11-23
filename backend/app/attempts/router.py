"""FastAPI routers for student examination attempts and administrator results."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse
from fastapi.responses import Response as BinaryResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.attempts import models as attempt_models
from app.attempts import service
from app.attempts.schemas import (
    AnswerSaveRequest,
    AnswerSaveResponse,
    AttemptDelivery,
    AttemptResultOut,
    AttemptStartRequest,
    AttemptStartResponse,
    AttemptSubmitRequest,
    AttemptSubmittedHiddenOut,
    ExamAdminResultsResponse,
    StudentAttemptSummary,
)
from app.auth.dependencies import AuthIdentity, require_admin, require_student
from app.database.session import get_db
from app.exams import models as exam_models
from app.exams.pdf_option_layout import asset_bytes, confirmed_layout
from app.exams.pdf_storage import load_image, student_image_without_number

exam_attempt_student_router = APIRouter(
    prefix="/api/exams",
    tags=["attempts"],
    dependencies=[Depends(require_student)],
)

attempts_student_router = APIRouter(
    prefix="/api/attempts",
    tags=["attempts"],
    dependencies=[Depends(require_student)],
)

student_history_router = APIRouter(
    prefix="/api/student/attempts",
    tags=["attempts"],
    dependencies=[Depends(require_student)],
)

admin_results_router = APIRouter(
    prefix="/api/admin",
    tags=["admin-results"],
    dependencies=[Depends(require_admin)],
)


# ---------------------------------------------------------------------------
# Student attempt routes
# ---------------------------------------------------------------------------


def _active_image_question(
    attempt_id: UUID,
    question_id: UUID,
    identity: AuthIdentity,
    db: Session,
) -> exam_models.Question:
    student_id = service.require_student_user_id(identity)
    attempt = db.get(attempt_models.ExamAttempt, attempt_id)
    if (
        attempt is None
        or attempt.user_id != student_id
        or attempt.status != "IN_PROGRESS"
        or service.ensure_utc(attempt.expires_at) <= datetime.now(UTC)
    ):
        raise HTTPException(status_code=404, detail="Image not found")
    link = db.execute(
        select(attempt_models.AttemptQuestion).where(
            attempt_models.AttemptQuestion.attempt_id == attempt_id,
            attempt_models.AttemptQuestion.question_id == question_id,
        )
    ).scalar_one_or_none()
    question = db.get(exam_models.Question, question_id) if link else None
    if question is None or question.source_file_id is None or question.source_number is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return question


@attempts_student_router.get("/{attempt_id}/questions/{question_id}/images/{index}")
def get_question_image_route(
    attempt_id: UUID,
    question_id: UUID,
    index: int,
    identity: AuthIdentity = Depends(require_student),
    db: Session = Depends(get_db),
) -> BinaryResponse:
    question = _active_image_question(attempt_id, question_id, identity, db)
    try:
        layout = confirmed_layout(question)
        image = (
            asset_bytes(question.source_file_id, UUID(layout["preview_id"]), "stem", index)
            if layout
            else load_image(question.source_file_id, question.source_number, index)
        )
        image = student_image_without_number(
            question,
            index,
            image,
            stem_regions=layout["layout"]["stem"] if layout else None,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Image not found") from exc
    return BinaryResponse(
        content=image,
        media_type="image/png",
        headers={"Cache-Control": "no-store, private"},
    )


@attempts_student_router.get(
    "/{attempt_id}/questions/{question_id}/options/{option_id}/images/{index}"
)
def get_option_image_route(
    attempt_id: UUID,
    question_id: UUID,
    option_id: UUID,
    index: int,
    identity: AuthIdentity = Depends(require_student),
    db: Session = Depends(get_db),
) -> BinaryResponse:
    question = _active_image_question(attempt_id, question_id, identity, db)
    option = db.get(exam_models.QuestionOption, option_id)
    layout = confirmed_layout(question)
    if option is None or option.question_id != question.id or not layout:
        raise HTTPException(404, "Image not found")
    item = next(o for o in layout["layout"]["options"] if o["label"] == option.label)
    if item["mode"] != "image":
        raise HTTPException(404, "Image not found")
    try:
        data = asset_bytes(question.source_file_id, UUID(layout["preview_id"]), option.label, index)
    except (OSError, ValueError) as exc:
        raise HTTPException(404, "Image not found") from exc
    return BinaryResponse(
        data, media_type="image/png", headers={"Cache-Control": "no-store, private"}
    )


@exam_attempt_student_router.post(
    "/{exam_id}/attempts",
    response_model=AttemptStartResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_attempt_route(
    exam_id: UUID,
    response: Response,
    _payload: AttemptStartRequest | None = Body(default=None),
    identity: AuthIdentity = Depends(require_student),
    db: Session = Depends(get_db),
) -> AttemptStartResponse:
    student_user_id = service.require_student_user_id(identity)
    started = service.start_attempt(
        db,
        exam_id=exam_id,
        student_user_id=student_user_id,
    )
    if started.resumed:
        response.status_code = status.HTTP_200_OK
    return started


@attempts_student_router.get(
    "/{attempt_id}",
    response_model=AttemptDelivery,
)
def get_attempt_delivery_route(
    attempt_id: UUID,
    identity: AuthIdentity = Depends(require_student),
    db: Session = Depends(get_db),
) -> AttemptDelivery | JSONResponse:
    student_user_id = service.require_student_user_id(identity)
    try:
        return service.get_attempt_for_delivery(
            db,
            attempt_id=attempt_id,
            student_user_id=student_user_id,
        )
    except service.AttemptConflictException as exc:
        return JSONResponse(status_code=exc.status_code, content=exc.error_payload)


@attempts_student_router.put(
    "/{attempt_id}/answers/{question_id}",
    response_model=AnswerSaveResponse,
)
def save_answer_route(
    attempt_id: UUID,
    question_id: UUID,
    data: AnswerSaveRequest,
    identity: AuthIdentity = Depends(require_student),
    db: Session = Depends(get_db),
) -> AnswerSaveResponse | JSONResponse:
    student_user_id = service.require_student_user_id(identity)
    try:
        return service.save_answer(
            db,
            attempt_id=attempt_id,
            question_id=question_id,
            selected_option_id=data.selected_option_id,
            student_user_id=student_user_id,
        )
    except service.AttemptConflictException as exc:
        return JSONResponse(status_code=exc.status_code, content=exc.error_payload)


@attempts_student_router.post(
    "/{attempt_id}/submit",
    response_model=AttemptResultOut | AttemptSubmittedHiddenOut,
)
def submit_attempt_route(
    attempt_id: UUID,
    data: AttemptSubmitRequest | None = Body(default=None),
    identity: AuthIdentity = Depends(require_student),
    db: Session = Depends(get_db),
) -> AttemptResultOut | AttemptSubmittedHiddenOut:
    student_user_id = service.require_student_user_id(identity)
    confirm = True if data is None else data.confirm
    return service.submit_attempt(
        db,
        attempt_id=attempt_id,
        student_user_id=student_user_id,
        confirm=confirm,
    )


@attempts_student_router.get(
    "/{attempt_id}/result",
    response_model=AttemptResultOut | AttemptSubmittedHiddenOut,
)
def get_attempt_result_route(
    attempt_id: UUID,
    identity: AuthIdentity = Depends(require_student),
    db: Session = Depends(get_db),
) -> AttemptResultOut | AttemptSubmittedHiddenOut:
    student_user_id = service.require_student_user_id(identity)
    return service.get_attempt_result(
        db,
        attempt_id=attempt_id,
        student_user_id=student_user_id,
    )


@student_history_router.get(
    "",
    response_model=list[StudentAttemptSummary],
)
def list_student_attempts_route(
    identity: AuthIdentity = Depends(require_student),
    db: Session = Depends(get_db),
) -> list[StudentAttemptSummary]:
    student_user_id = service.require_student_user_id(identity)
    return service.list_student_attempts(db, student_user_id=student_user_id)


# ---------------------------------------------------------------------------
# Administrator results routes
# ---------------------------------------------------------------------------


@admin_results_router.get(
    "/exams/{exam_id}/results",
    response_model=ExamAdminResultsResponse,
)
def get_admin_exam_results_route(
    exam_id: UUID,
    identity: AuthIdentity = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ExamAdminResultsResponse:
    admin_user_id = service.require_admin_user_id(identity)
    return service.get_admin_exam_results(
        db,
        exam_id=exam_id,
        admin_user_id=admin_user_id,
    )


@admin_results_router.get(
    "/attempts/{attempt_id}",
    response_model=AttemptResultOut,
)
def get_admin_attempt_detail_route(
    attempt_id: UUID,
    identity: AuthIdentity = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AttemptResultOut:
    admin_user_id = service.require_admin_user_id(identity)
    return service.get_admin_attempt_detail(
        db,
        attempt_id=attempt_id,
        admin_user_id=admin_user_id,
    )


router = APIRouter()
router.include_router(exam_attempt_student_router)
router.include_router(attempts_student_router)
router.include_router(student_history_router)
router.include_router(admin_results_router)
