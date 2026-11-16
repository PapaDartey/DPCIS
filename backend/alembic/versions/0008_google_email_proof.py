"""Record a second email proof for accounts that use Google sign-in.

Revision ID: 0008_google_email_proof
Revises: 0007_pdf_import_workflow
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_google_email_proof"
down_revision = "0007_pdf_import_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application_google_email_proofs",
        sa.Column("auth_subject", sa.String(255), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column(
            "confirmed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("application_google_email_proofs")
