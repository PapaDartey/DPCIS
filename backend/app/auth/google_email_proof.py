"""Application access gate for Google users' independent email proof.

Google verifies its own account email, but a separate OTP proves control of the
mailbox for Examination Hub. Only the backend may record this proof. The OTP is
validated and consumed by Neon Managed Auth, and is never stored or logged here.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException
from sqlalchemy import Column, DateTime, MetaData, String, Table, select, text
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthIdentity
from app.config import Settings

_metadata = MetaData()
proofs = Table(
    "application_google_email_proofs",
    _metadata,
    Column("auth_subject", String(255), primary_key=True),
    Column("email", String(320), nullable=False),
    Column("confirmed_at", DateTime(timezone=True), nullable=False),
)


def google_email_needs_proof(db: Session, identity: AuthIdentity) -> bool:
    if db.get_bind().dialect.name != "postgresql":
        return False  # Isolated SQLite tests do not have Neon's managed schema.
    if not identity.email:
        raise HTTPException(403, "Verified email required")
    google_account = db.execute(
        text(
            'SELECT 1 FROM neon_auth.account WHERE "userId" = :subject '
            'AND "providerId" = :provider LIMIT 1'
        ),
        {"subject": identity.subject, "provider": "google"},
    ).scalar_one_or_none()
    if not google_account:
        return False
    confirmed = db.execute(
        select(proofs.c.email).where(proofs.c.auth_subject == identity.subject)
    ).scalar_one_or_none()
    return confirmed is None or confirmed.casefold() != identity.email.casefold()


def require_google_email_proof(db: Session, identity: AuthIdentity) -> None:
    if google_email_needs_proof(db, identity):
        raise HTTPException(403, "GOOGLE_EMAIL_PROOF_REQUIRED")


def confirm_google_email_and_password(
    db: Session, identity: AuthIdentity, settings: Settings, otp: str, password: str
) -> None:
    if not google_email_needs_proof(db, identity):
        raise HTTPException(409, "Google email proof is not required")
    if not settings.NEON_AUTH_BASE_URL:
        raise HTTPException(503, "Authentication provider is not configured")
    if not settings.NEON_AUTH_BASE_URL.startswith("https://"):
        raise HTTPException(503, "Authentication provider URL must use HTTPS")
    payload = json.dumps({"email": identity.email, "otp": otp, "password": password}).encode()
    request = Request(  # noqa: S310 - validated HTTPS Neon Auth origin above
        settings.NEON_AUTH_BASE_URL.rstrip("/") + "/email-otp/reset-password",
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=8) as response:  # noqa: S310
            if response.status >= 300:
                raise HTTPException(400, "Verification code was not accepted")
    except HTTPError as exc:
        raise HTTPException(400, "Verification code or password was not accepted") from exc
    except (URLError, TimeoutError) as exc:
        raise HTTPException(503, "Authentication provider is temporarily unavailable") from exc
    now = datetime.now(UTC)
    existing = db.execute(
        select(proofs.c.auth_subject).where(proofs.c.auth_subject == identity.subject)
    ).scalar_one_or_none()
    if existing:
        db.execute(
            proofs.update()
            .where(proofs.c.auth_subject == identity.subject)
            .values(email=identity.email, confirmed_at=now)
        )
    else:
        db.execute(
            proofs.insert().values(
                auth_subject=identity.subject, email=identity.email, confirmed_at=now
            )
        )
    db.commit()
