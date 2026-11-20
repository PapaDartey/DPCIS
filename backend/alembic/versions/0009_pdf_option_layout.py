"""Add reviewed PDF question/answer display layouts.

Revision ID: 0009_pdf_option_layout
Revises: 0008_google_email_proof
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_pdf_option_layout"
down_revision = "0008_google_email_proof"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("questions", sa.Column("option_layout", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("questions", "option_layout")
