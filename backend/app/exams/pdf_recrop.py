"""Review immutable crop candidates, then atomically switch approved references.

Preview writes only new private files. Approval locks the draft exam/questions,
checks the original crop fingerprint and every candidate before any DB update.
The old source and PNGs remain intact even on validation/commit failure. A repeat
or concurrent approval of a changed question fails stale. Keys, options, marks,
positions and text are deliberately absent from the update path. Work is linear
in selected image bytes, plus the graphics detector's cost per unique source.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthIdentity, require_admin
from app.database.session import get_db
from app.exams.models import Exam, ExamSourceFile, Question
from app.exams.pdf_import import detect_pdf_questions, validate_pdf
from app.exams.pdf_storage import (
    load_image,
    load_regions,
    regenerate_crops,
    source_dir,
    storage_root,
    store_pdf,
)

router = APIRouter(prefix="/api/admin/exams", tags=["Admin re-crop"])


class RecropApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_ids: list[UUID] = Field(min_length=1, max_length=1000)


def _draft(db: Session, exam_id: UUID) -> Exam:
    exam = db.scalar(select(Exam).where(Exam.id == exam_id).with_for_update())
    if exam is None:
        raise HTTPException(404, "Examination not found")
    if exam.status != "DRAFT":
        raise HTTPException(409, "Only draft examinations can be re-cropped")
    return exam


def _manifest_path(preview_id: UUID):
    directory = storage_root() / "recrop-previews"
    directory.mkdir(exist_ok=True)
    return directory / f"{preview_id}.json"


def _load_manifest(
    preview_id: UUID, exam_id: UUID, identity: AuthIdentity, *, allow_expired: bool = False
) -> dict:
    try:
        manifest = json.loads(_manifest_path(preview_id).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HTTPException(404, "Re-crop preview not found") from exc
    if manifest["exam_id"] != str(exam_id) or manifest["admin_id"] != str(identity.user_id):
        raise HTTPException(404, "Re-crop preview not found")
    if manifest.get("status"):
        raise HTTPException(409, "Re-crop preview already closed; generate a new preview")
    if not allow_expired and datetime.fromisoformat(manifest["expires_at"]) < datetime.now(UTC):
        raise HTTPException(409, "Re-crop preview expired; generate a new preview")
    return manifest


def _close_preview(db: Session, preview_id: UUID, manifest: dict, status: str) -> None:
    """Keep only files referenced by committed questions; never delete old sources.

    Candidate directories are UUID children of the private storage root, contain
    only flat files, and are unique to this preview. A completed manifest is a
    small tombstone so replay fails explicitly. Cleanup follows the DB commit:
    committed image references always win over the selected request payload.
    """
    for candidate in set(manifest.get("candidate_ids", [])):
        candidate_id = UUID(candidate)
        directory = source_dir(candidate_id).resolve()
        if directory.parent != storage_root().resolve() or directory.is_symlink():
            raise ValueError("Invalid candidate directory")
        referenced = list(db.scalars(
            select(Question).where(Question.source_file_id == candidate_id)
        ))
        keep = {"source.pdf"} if referenced else set()
        for question in referenced:
            keep.add(f"{question.source_number}.json")
            keep.update(json.loads(question.image_paths or "[]"))
        if directory.exists():
            for path in directory.iterdir():
                if path.name not in keep and path.is_file():
                    path.unlink()
            if not keep:
                directory.rmdir()
    manifest["status"] = status
    manifest["questions"] = []
    manifest["candidate_ids"] = []
    _manifest_path(preview_id).write_text(json.dumps(manifest), encoding="utf-8")


def _fingerprint(question: Question) -> str:
    digest = hashlib.sha256(
        json.dumps(
            [
                str(question.source_file_id),
                question.source_number,
                question.image_regions,
            ]
        ).encode()
    )
    if question.source_file_id and question.source_number:
        directory = source_dir(question.source_file_id)
        digest.update((directory / "source.pdf").read_bytes())
        regions = load_regions(question.source_file_id, question.source_number)
        digest.update(json.dumps(regions, sort_keys=True).encode())
        for index in range(len(regions)):
            digest.update(load_image(question.source_file_id, question.source_number, index))
    return digest.hexdigest()


@router.post("/{exam_id}/recrop-preview")
def preview_recrop(
    exam_id: UUID,
    identity: AuthIdentity = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    _draft(db, exam_id)
    questions = list(
        db.scalars(
            select(Question)
            .where(
                Question.exam_id == exam_id,
                Question.source_file_id.is_not(None),
            )
            .order_by(Question.position)
        )
    )
    preview_id = uuid4()
    candidates: dict[UUID, dict] = {}
    candidate_ids = []
    rows = []
    for question in questions:
        source_id = question.source_file_id
        row = {
            "question_id": str(question.id),
            "position": question.position,
            "valid": False,
            "warnings": [],
            "before_urls": [],
            "after_urls": [],
        }
        try:
            source = db.get(ExamSourceFile, source_id)
            if source is None or source.exam_id != exam_id or not question.source_number:
                raise ValueError("Stored source is not available for this question")
            row["fingerprint"] = _fingerprint(question)
            old_regions = load_regions(source_id, question.source_number)
            row["before_urls"] = [
                f"/api/admin/exams/{exam_id}/source-images/{source_id}/{question.source_number}/{i}"
                for i in range(len(old_regions))
            ]
            if source_id not in candidates:
                data = (source_dir(source_id) / "source.pdf").read_bytes()
                with validate_pdf(data) as doc:
                    detected = detect_pdf_questions(doc)
                    page_count = len(doc)
                if not detected:
                    raise ValueError("No selectable numbered questions; use the manual crop editor")
                candidate_id = uuid4()
                candidate_ids.append(str(candidate_id))
                store_pdf(candidate_id, data, detected)
                candidates[source_id] = {
                    "id": str(candidate_id),
                    "questions": {q.number: q for q in detected},
                    "filename": source.original_filename,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "page_count": page_count,
                }
            candidate = candidates[source_id]
            detected_question = candidate["questions"].get(question.source_number)
            if detected_question is None or not detected_question.regions:
                raise ValueError("Original question number not detected; keep the existing crop")
            row.update(
                {
                    "source_id": str(source_id),
                    "candidate_id": candidate["id"],
                    "source_number": question.source_number,
                    "filename": candidate["filename"],
                    "sha256": candidate["sha256"],
                    "page_count": candidate["page_count"],
                    "valid": detected_question.crop_valid,
                    "warnings": detected_question.warnings,
                    "regions": load_regions(UUID(candidate["id"]), question.source_number),
                    "after_urls": [
                        f"/api/admin/exams/{exam_id}/recrop-preview/{preview_id}/{question.id}/{i}"
                        for i in range(len(detected_question.regions))
                    ],
                }
            )
        except (OSError, ValueError) as exc:
            row["warnings"] = [f"Cannot re-crop: {exc}"]
        rows.append(row)
    manifest = {
        "exam_id": str(exam_id),
        "admin_id": str(identity.user_id),
        "questions": rows,
        "candidate_ids": candidate_ids,
        "expires_at": (datetime.now(UTC) + timedelta(hours=24)).isoformat(),
    }
    _manifest_path(preview_id).write_text(json.dumps(manifest), encoding="utf-8")
    return {
        "preview_id": preview_id,
        "questions": [
            {
                key: row[key]
                for key in (
                    "question_id",
                    "position",
                    "valid",
                    "warnings",
                    "before_urls",
                    "after_urls",
                )
            }
            for row in rows
        ],
    }


@router.get("/{exam_id}/recrop-preview/{preview_id}/{question_id}/{index}")
def preview_image(
    exam_id: UUID,
    preview_id: UUID,
    question_id: UUID,
    index: int,
    identity: AuthIdentity = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    _draft(db, exam_id)
    manifest = _load_manifest(preview_id, exam_id, identity)
    row = next((q for q in manifest["questions"] if q["question_id"] == str(question_id)), None)
    if row is None or not row.get("candidate_id"):
        raise HTTPException(404, "Preview image not found")
    try:
        image = load_image(UUID(row["candidate_id"]), row["source_number"], index)
    except (OSError, ValueError) as exc:
        raise HTTPException(404, "Preview image not found") from exc
    return Response(image, media_type="image/png")


@router.post("/{exam_id}/recrop-preview/{preview_id}/apply")
def apply_recrop(
    exam_id: UUID,
    preview_id: UUID,
    payload: RecropApproval,
    identity: AuthIdentity = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    _draft(db, exam_id)
    manifest = _load_manifest(preview_id, exam_id, identity)
    selected = set(payload.question_ids)
    if len(selected) != len(payload.question_ids):
        raise HTTPException(422, "Approve each question only once")
    rows = {UUID(q["question_id"]): q for q in manifest["questions"]}
    prepared = []
    # Validate the entire approval batch before altering any database reference.
    for question_id in sorted(selected, key=str):
        row = rows.get(question_id)
        if row is None or not row["valid"]:
            raise HTTPException(422, "Selection includes an invalid re-crop candidate")
        question = db.scalar(
            select(Question)
            .where(
                Question.id == question_id,
                Question.exam_id == exam_id,
            )
            .with_for_update()
        )
        try:
            if question is None or _fingerprint(question) != row["fingerprint"]:
                raise HTTPException(409, "Question crop changed; generate a new preview")
            candidate_id = UUID(row["candidate_id"])
            # Recheck geometry/pixels before any reference switches. Only candidate
            # files are rendered; original crops and answer-key archives stay intact.
            regenerate_crops(candidate_id, row["source_number"], row["regions"], dpi=220)
        except (OSError, ValueError) as exc:
            raise HTTPException(
                422, "Candidate clipping/storage check failed; old crop kept"
            ) from exc
        prepared.append((question, row, candidate_id))
    for question, row, candidate_id in prepared:
        if db.get(ExamSourceFile, candidate_id) is None:
            db.add(
                ExamSourceFile(
                    id=candidate_id,
                    exam_id=exam_id,
                    original_filename=row["filename"],
                    sha256=row["sha256"],
                    page_count=row["page_count"],
                )
            )
            db.flush()
        question.source_file_id = candidate_id
        question.image_regions = json.dumps(row["regions"])
        question.image_paths = json.dumps(
            [f"{row['source_number']}-{index}.png" for index in range(len(row["regions"]))]
        )
    db.commit()
    _close_preview(db, preview_id, manifest, "applied")
    return {"applied_question_ids": [str(qid) for qid in sorted(selected, key=str)]}


@router.delete("/{exam_id}/recrop-preview/{preview_id}")
def discard_recrop(
    exam_id: UUID,
    preview_id: UUID,
    identity: AuthIdentity = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    _draft(db, exam_id)
    manifest = _load_manifest(preview_id, exam_id, identity, allow_expired=True)
    _close_preview(db, preview_id, manifest, "discarded")
    return {"discarded": True}
