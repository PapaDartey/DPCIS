"""Opt-in PostgreSQL concurrency coverage for re-crop approval."""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import ROLE_ADMIN
from app.auth import dependencies as auth_dependencies
from app.config import Settings
from app.database import Base
from app.database.session import get_db, normalize_postgres_url
from app.main import create_app
from app.users.models import ApplicationUser


def _postgres_skip_reason() -> str | None:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url.startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
        return "Skipped: set DATABASE_URL to a throwaway PostgreSQL database."
    if os.environ.get("DPCIS_THROWAWAY_POSTGRES") != "1":
        return "Skipped: set DPCIS_THROWAWAY_POSTGRES=1 to opt into throwaway PostgreSQL tests."
    return None


_POSTGRES_SKIP_REASON = _postgres_skip_reason()


@pytest.mark.skipif(_POSTGRES_SKIP_REASON is not None, reason=_POSTGRES_SKIP_REASON or "")
def test_concurrent_recrop_approval_has_one_winner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Two approvals of one preview serialize so exactly one request succeeds."""
    raw_url = os.environ["DATABASE_URL"]
    settings = Settings(
        _env_file=None,
        APP_ENV="test",
        DATABASE_URL=raw_url,
        DIRECT_DATABASE_URL=raw_url,
        CORS_ORIGINS=["http://localhost:5173"],
        NEON_AUTH_BASE_URL="https://auth.example.com",
        NEON_AUTH_JWKS_URL="https://auth.example.com/.well-known/jwks.json",
        NEON_AUTH_AUDIENCE="examination-hub",
    )
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    monkeypatch.setattr(
        auth_dependencies,
        "_jwks_client",
        lambda _url: SimpleNamespace(
            get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=public_key)
        ),
    )
    engine = create_engine(
        normalize_postgres_url(raw_url),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )
    session_factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    admin_id = uuid4()
    token = jwt.encode(
        {
            "sub": "recrop-postgres-admin",
            "iss": "https://auth.example.com",
            "aud": "examination-hub",
            "exp": int(time.time()) + 300,
        },
        private_key,
        algorithm="EdDSA",
    )
    admin_headers = {"Authorization": f"Bearer {token}"}
    Base.metadata.create_all(engine)
    with session_factory() as db:
        db.add(
            ApplicationUser(
                id=admin_id,
                auth_subject="recrop-postgres-admin",
                email="recrop-postgres@example.test",
                display_name="Recrop PostgreSQL Admin",
                role=ROLE_ADMIN,
            )
        )
        db.commit()

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app = create_app(settings)
    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setenv("EXAM_PDF_STORAGE_DIR", str(tmp_path))

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            exam_response = client.post(
                "/api/admin/exams",
                headers=admin_headers,
                json={"title": "PostgreSQL re-crop race", "duration_minutes": 45, "pass_mark": 50},
            )
            assert exam_response.status_code == 201, exam_response.text
            exam_id = exam_response.json()["id"]
            fixture = Path(__file__).parent / "fixtures" / "two_column.pdf"
            import_response = client.post(
                f"/api/admin/exams/{exam_id}/import-pdf",
                headers=admin_headers,
                files={"file": ("paper.pdf", fixture.read_bytes(), "application/pdf")},
                data={"answer_key_text": "1 A\n2 A\n3 A\n4 A"},
            )
            assert import_response.status_code == 200, import_response.text
            preview = import_response.json()
            questions = sorted(
                preview["valid_questions"] + preview["invalid_questions"],
                key=lambda question: question["position"],
            )
            assert questions and all(question["valid"] for question in questions)
            saved = client.put(
                f"/api/admin/exams/{exam_id}/questions",
                headers=admin_headers,
                json={
                    "questions": [
                        {
                            "question_text": question["question_text"],
                            "source_file_id": question["source_file_id"],
                            "source_number": question["source_number"],
                            "points": "3.50",
                            "options": [
                                {**option, "is_correct": option["label"] == "A"}
                                for option in question["options"]
                            ],
                        }
                        for question in questions
                    ]
                },
            )
            assert saved.status_code == 200, saved.text
            recrop = client.post(
                f"/api/admin/exams/{exam_id}/recrop-preview",
                headers=admin_headers,
            )
            assert recrop.status_code == 200, recrop.text
            recrop_payload = recrop.json()
            question_id = recrop_payload["questions"][0]["question_id"]
            endpoint = (
                f"/api/admin/exams/{exam_id}/recrop-preview/"
                f"{recrop_payload['preview_id']}/apply"
            )

        def apply_once() -> int:
            with TestClient(app, raise_server_exceptions=False) as concurrent_client:
                return concurrent_client.post(
                    endpoint,
                    headers=admin_headers,
                    json={"question_ids": [question_id]},
                ).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(lambda _item: apply_once(), range(2)))
        assert sorted(statuses) == [200, 409]
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()
