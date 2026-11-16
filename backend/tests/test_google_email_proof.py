"""Independent proof gate and remote OTP rejection tests; no Neon calls."""

import json
from urllib.error import HTTPError

import pytest
from fastapi import HTTPException

from app.auth import google_email_proof as proof
from app.auth.dependencies import AuthIdentity
from app.config import Settings


class Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class Database:
    def __init__(self, results):
        self.results = iter(results)
        self.statements = []
        self.committed = False

    def get_bind(self):
        return type("Bind", (), {"dialect": type("Dialect", (), {"name": "postgresql"})()})()

    def execute(self, statement, params=None):
        self.statements.append((statement, params))
        return Result(next(self.results, None))

    def commit(self):
        self.committed = True


IDENTITY = AuthIdentity(subject="google-user", email="student@example.test", name="Student")


def test_google_session_is_denied_until_matching_email_proof():
    with pytest.raises(HTTPException, match="GOOGLE_EMAIL_PROOF_REQUIRED"):
        proof.require_google_email_proof(Database([1, None]), IDENTITY)
    with pytest.raises(HTTPException, match="GOOGLE_EMAIL_PROOF_REQUIRED"):
        proof.require_google_email_proof(Database([1, "old@example.test"]), IDENTITY)
    proof.require_google_email_proof(Database([1, "STUDENT@example.test"]), IDENTITY)
    proof.require_google_email_proof(Database([None]), IDENTITY)


def test_wrong_code_never_records_proof(monkeypatch):
    db = Database([])
    monkeypatch.setattr(proof, "google_email_needs_proof", lambda *_: True)

    def reject(*_args, **_kwargs):
        raise HTTPError("https://auth.example.test", 400, "invalid", None, None)

    monkeypatch.setattr(proof, "urlopen", reject)
    settings = Settings(
        _env_file=None, APP_ENV="test", NEON_AUTH_BASE_URL="https://auth.example.test"
    )
    with pytest.raises(HTTPException) as error:
        proof.confirm_google_email_and_password(
            db, IDENTITY, settings, "000000", "fake-test-password"
        )
    assert error.value.status_code == 400
    assert not db.committed and not db.statements


def test_valid_code_records_subject_and_verified_email(monkeypatch):
    db = Database([None])
    monkeypatch.setattr(proof, "google_email_needs_proof", lambda *_: True)
    seen = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def accept(request, timeout):
        seen.update(json.loads(request.data))
        assert timeout == 8
        return Response()

    monkeypatch.setattr(proof, "urlopen", accept)
    settings = Settings(
        _env_file=None, APP_ENV="test", NEON_AUTH_BASE_URL="https://auth.example.test"
    )
    proof.confirm_google_email_and_password(db, IDENTITY, settings, "123456", "fake-test-password")
    assert seen == {"email": IDENTITY.email, "otp": "123456", "password": "fake-test-password"}
    assert db.committed
    assert len(db.statements) == 2
