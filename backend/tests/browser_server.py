"""Loopback-only browser test server; never imported by the production app.

Run from backend: .venv/Scripts/python -m uvicorn browser_server:app
--app-dir tests --host 127.0.0.1 --port 8000
Uses a fresh isolated SQLite file and local signing key; no live Neon access.
"""

import os
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import HTTPException, Request
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.auth import dependencies
from app.config import Settings
from app.database import Base
from app.database.session import get_db
from app.main import create_app
from app.users.models import ApplicationUser

if os.environ.get("DPCIS_BROWSER_TEST") != "1":
    raise RuntimeError("Local browser harness requires DPCIS_BROWSER_TEST=1")

ROOT = Path(__file__).resolve().parents[1] / "var" / "browser-confirmation" / str(uuid4())
ROOT.mkdir(parents=True)
os.environ["EXAM_PDF_STORAGE_DIR"] = str(ROOT / "sources")
engine = create_engine(
    f"sqlite+pysqlite:///{ROOT / 'test.sqlite'}", connect_args={"check_same_thread": False}
)


@event.listens_for(engine, "connect")
def enable_foreign_keys(connection, _record):
    connection.execute("PRAGMA foreign_keys=ON")


Base.metadata.create_all(engine)
sessions = sessionmaker(engine, expire_on_commit=False)
with sessions() as db:
    db.add(
        ApplicationUser(
            id=uuid4(),
            auth_subject="browser-test-admin",
            role="ADMIN",
            email="browser-admin@example.test",
            display_name="Browser Test Admin",
        )
    )
    db.commit()
private_key = Ed25519PrivateKey.generate()
dependencies._jwks_client = lambda _url: SimpleNamespace(
    get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=private_key.public_key()),
)
app = create_app(
    Settings(
        _env_file=None,
        APP_ENV="test",
        DATABASE_URL=None,
        DIRECT_DATABASE_URL=None,
        NEON_AUTH_BASE_URL="https://auth.example.test",
        NEON_AUTH_JWKS_URL="https://auth.example.test/.well-known/jwks.json",
        NEON_AUTH_AUDIENCE="browser-test",
        CORS_ORIGINS=["http://127.0.0.1:5173", "http://localhost:5173"],
    )
)


def isolated_db():
    with sessions() as db:
        yield db


app.dependency_overrides[get_db] = isolated_db


@app.middleware("http")
async def loopback_only(request: Request, call_next):
    if request.client is None or request.client.host not in {"127.0.0.1", "::1"}:
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": "Loopback test server only"}, status_code=403)
    return await call_next(request)


@app.get("/__test_session", include_in_schema=False)
def test_session(request: Request):
    if request.headers.get("origin") not in {
        None,
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    }:
        raise HTTPException(403, "Test origin required")
    user = {
        "id": "browser-test-admin",
        "name": "Browser Test Admin",
        "email": "browser-admin@example.test",
    }
    token = jwt.encode(
        {
            "sub": user["id"],
            "email": user["email"],
            "name": user["name"],
            "iss": "https://auth.example.test",
            "aud": "browser-test",
            "exp": int(time.time()) + 3600,
        },
        private_key,
        algorithm="EdDSA",
    )
    return {"user": user, "token": token, "test_session": True}
