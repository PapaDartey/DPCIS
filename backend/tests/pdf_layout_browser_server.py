"""Guarded loopback server for PDF option layout browser checks; no live Neon."""

import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Literal
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import HTTPException, Request, Response
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.auth import dependencies
from app.config import Settings
from app.database import Base
from app.database.session import get_db
from app.main import create_app
from app.users.models import ApplicationUser
from test_pdf_option_layout import triangle_pdf

if os.environ.get("DPCIS_PDF_LAYOUT_TEST") != "1":
    raise RuntimeError("PDF layout browser harness requires DPCIS_PDF_LAYOUT_TEST=1")

temporary = TemporaryDirectory(prefix="dpcis-option-layout-")
root = Path(temporary.name)
os.environ["EXAM_PDF_STORAGE_DIR"] = str(root / "sources")
engine = create_engine(
    f"sqlite:///{root / 'test.sqlite'}", connect_args={"check_same_thread": False}
)


@event.listens_for(engine, "connect")
def enable_foreign_keys(connection, _record):
    connection.execute("PRAGMA foreign_keys=ON")


Base.metadata.create_all(engine)
sessions = sessionmaker(engine, expire_on_commit=False)
with sessions() as db:
    for role in ["ADMIN", "STUDENT"]:
        db.add(
            ApplicationUser(
                id=uuid4(),
                auth_subject=f"layout-browser-{role}",
                role=role,
                email=f"layout-{role.lower()}@example.test",
                display_name=f"Layout Test {role.title()}",
            )
        )
    db.commit()
private_key = Ed25519PrivateKey.generate()
dependencies._jwks_client = lambda _url: SimpleNamespace(
    get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=private_key.public_key())
)
app = create_app(
    Settings(
        _env_file=None,
        APP_ENV="test",
        DATABASE_URL=None,
        DIRECT_DATABASE_URL=None,
        NEON_AUTH_BASE_URL="https://auth.example.test",
        NEON_AUTH_JWKS_URL="https://auth.example.test/.well-known/jwks.json",
        NEON_AUTH_AUDIENCE="layout-browser",
        CORS_ORIGINS=["http://127.0.0.1:5181", "http://localhost:5181"],
    )
)


def isolated_db():
    with sessions() as db:
        yield db


app.dependency_overrides[get_db] = isolated_db


@app.middleware("http")
async def loopback_only(request: Request, call_next):
    if request.client is None or request.client.host not in {"127.0.0.1", "::1"}:
        return Response(status_code=403)
    return await call_next(request)


@app.get("/__test_session", include_in_schema=False)
def test_session(request: Request, role: Literal["ADMIN", "STUDENT"] = "ADMIN"):
    if request.headers.get("origin") not in {
        None,
        "http://127.0.0.1:5181",
        "http://localhost:5181",
    }:
        raise HTTPException(403, "Test origin required")
    user = {
        "id": f"layout-browser-{role}",
        "email": f"layout-{role.lower()}@example.test",
        "name": f"Layout Test {role.title()}",
    }
    token = jwt.encode(
        {
            "sub": user["id"],
            "email": user["email"],
            "name": user["name"],
            "iss": "https://auth.example.test",
            "aud": "layout-browser",
            "exp": int(time.time()) + 3600,
        },
        private_key,
        algorithm="EdDSA",
    )
    return {"user": user, "token": token, "test_session": True}


@app.get("/__test_paper", include_in_schema=False)
def test_paper():
    return Response(triangle_pdf(), media_type="application/pdf")
