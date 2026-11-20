"""Draft-only preview/confirmation API for separately rendered PDF answers."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

import fitz
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth.dependencies import AuthIdentity, require_admin
from app.database.session import get_db
from app.exams.models import Exam, Question
from app.exams.pdf_import import validate_pdf
from app.exams.pdf_option_layout import (
    LayoutInput,
    asset_bytes,
    confirmed_layout,
    fingerprint,
    layout_directory,
    public_layout,
    render_layout,
    signature,
    suggest_layout,
    validate_text,
)
from app.exams.pdf_storage import source_dir

router = APIRouter(tags=["admin-exams"])


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    layout: LayoutInput | None = None


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preview_id: UUID
    confirm: Literal[True]


def _question(db: Session, exam_id: UUID, question_id: UUID, *, draft: bool = True) -> Question:
    exam = db.scalar(select(Exam).where(Exam.id == exam_id).with_for_update())
    if exam is None:
        raise HTTPException(404, "Examination not found")
    if draft and exam.status != "DRAFT":
        raise HTTPException(409, "Separate answers only on a draft examination")
    question = db.scalar(
        select(Question)
        .where(Question.id == question_id, Question.exam_id == exam_id)
        .options(selectinload(Question.options))
        .with_for_update()
    )
    if question is None or not question.source_file_id or not question.source_number:
        raise HTTPException(404, "PDF question not found")
    return question


def _manifest(question: Question, preview_id: UUID, *, allow_confirmed: bool = False) -> dict:
    try:
        manifest = json.loads(
            (layout_directory(question.source_file_id, preview_id) / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        saved = confirmed_layout(question) if allow_confirmed else None
        reused = saved is not None and saved["preview_id"] == str(preview_id)
        if manifest["exam_id"] != str(question.exam_id) or (
            manifest["question_id"] != str(question.id) and not reused
        ):
            raise ValueError
        if manifest["source_id"] != str(question.source_file_id):
            raise ValueError
        return manifest
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(404, "Answer preview not found") from exc


@router.post("/{exam_id}/questions/{question_id}/option-layout/preview")
def preview_layout(
    exam_id: UUID,
    question_id: UUID,
    payload: PreviewRequest,
    _identity: AuthIdentity = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    question = _question(db, exam_id, question_id)
    try:
        with validate_pdf((source_dir(question.source_file_id) / "source.pdf").read_bytes()) as doc:
            dimensions = [(p.rect.width, p.rect.height) for p in doc]
            layout, warnings = (
                (payload.layout, []) if payload.layout else suggest_layout(doc, question)
            )
            stem_text = " ".join(
                doc[r.page - 1].get_text("text", clip=fitz.Rect(r.bbox)).strip()
                for r in layout.stem
                if r.page <= len(doc)
            ).strip()
            try:
                assets = render_layout(doc, question, layout)
            except ValueError as exc:
                if payload.layout is not None:
                    raise
                warnings.append(str(exc))
                assets = {}
    except OSError as exc:
        raise HTTPException(503, "Stored PDF is unavailable") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    preview_id = uuid4() if assets else None
    manifest = {
        "exam_id": str(exam_id),
        "question_id": str(question_id),
        "source_id": str(question.source_file_id),
        "source_number": question.source_number,
        "fingerprint": fingerprint(question),
        "layout": layout.model_dump(mode="json"),
        "preview_id": str(preview_id),
        "stem_text": stem_text or "Question with a figure. Choose one answer.",
    }
    if preview_id:
        directory = layout_directory(question.source_file_id, preview_id)
        try:
            directory.mkdir(parents=True, exist_ok=False)
            for name, data in assets.items():
                (directory / name).write_bytes(data)
            (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        except OSError as exc:
            shutil.rmtree(directory, ignore_errors=True)
            raise HTTPException(503, "Answer preview storage is unavailable") from exc
    return {
        "question_id": str(question_id),
        "preview_id": str(preview_id) if preview_id else None,
        "valid": bool(assets),
        "warnings": warnings,
        "page_dimensions": dimensions,
        "layout": public_layout(question, manifest) if assets else layout.model_dump(mode="json"),
    }


@router.post("/{exam_id}/questions/{question_id}/option-layout/confirm")
def confirm_layout(
    exam_id: UUID,
    question_id: UUID,
    payload: ConfirmRequest,
    _identity: AuthIdentity = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    from app.exams.service import _to_question_admin_out

    question = _question(db, exam_id, question_id)
    previous = confirmed_layout(question)
    if previous and previous["preview_id"] == str(payload.preview_id):
        return _to_question_admin_out(question).model_dump(mode="json")
    manifest = _manifest(question, payload.preview_id)
    if manifest["fingerprint"] != fingerprint(question):
        raise HTTPException(409, "The question changed. Generate and review a new preview.")
    try:
        layout = LayoutInput.model_validate(manifest["layout"])
        validate_text(layout)
        # Ensure every candidate still exists before changing any display state.
        for part, regions in [
            ("stem", layout.stem),
            *[(o.label, o.regions) for o in layout.options],
        ]:
            for index in range(len(regions)):
                asset_bytes(question.source_file_id, payload.preview_id, part, index)
    except OSError as exc:
        raise HTTPException(422, "Preview images are unavailable. Generate a new preview.") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    by_label = {o.label: o for o in layout.options}
    for option in question.options:
        option.option_text = by_label[option.label].option_text.strip()
    manifest["signature"] = signature(question)
    question.option_layout = json.dumps(manifest)
    question.updated_at = datetime.now(UTC)
    exam = db.get(Exam, exam_id)
    exam.updated_at = question.updated_at
    db.commit()
    return _to_question_admin_out(question).model_dump(mode="json")


@router.delete(
    "/{exam_id}/questions/{question_id}/option-layout/preview/{preview_id}", status_code=204
)
def discard_preview(
    exam_id: UUID,
    question_id: UUID,
    preview_id: UUID,
    _identity: AuthIdentity = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    question = _question(db, exam_id, question_id)
    _manifest(question, preview_id, allow_confirmed=True)
    saved = confirmed_layout(question)
    if saved and saved["preview_id"] == str(preview_id):
        raise HTTPException(409, "Confirmed images are in use and cannot be discarded")
    shutil.rmtree(layout_directory(question.source_file_id, preview_id))
    return Response(status_code=204)


@router.get("/{exam_id}/questions/{question_id}/option-layout/assets/{preview_id}/{part}/{index}")
def admin_layout_asset(
    exam_id: UUID,
    question_id: UUID,
    preview_id: UUID,
    part: str,
    index: int,
    _identity: AuthIdentity = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    question = _question(db, exam_id, question_id, draft=False)
    _manifest(question, preview_id, allow_confirmed=True)
    try:
        data = asset_bytes(question.source_file_id, preview_id, part, index)
    except OSError as exc:
        raise HTTPException(404, "Image not found") from exc
    return Response(data, media_type="image/png", headers={"Cache-Control": "no-store, private"})
