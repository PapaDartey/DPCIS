"""Add PDF page dimensions, question region status, extracted text, and safe FK ondelete.

Revision ID: 0007_pdf_import_workflow
Revises: 0006_submission_reason
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_pdf_import_workflow"
down_revision = "0006_submission_reason"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("exam_source_files", sa.Column("page_dimensions", sa.Text(), nullable=True))
    op.add_column(
        "questions",
        sa.Column(
            "region_status",
            sa.String(length=32),
            nullable=True,
            server_default=sa.text("'detected'"),
        ),
    )
    op.add_column("questions", sa.Column("extracted_text", sa.Text(), nullable=True))

    with op.batch_alter_table("questions") as batch_op:
        batch_op.create_check_constraint(
            "ck_questions_region_status",
            "region_status IS NULL OR region_status IN ('detected', 'needs-review', 'approved')",
        )
        batch_op.drop_constraint("fk_questions_source_file_id", type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_questions_source_file_id",
            "exam_source_files",
            ["source_file_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("questions") as batch_op:
        batch_op.drop_constraint("fk_questions_source_file_id", type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_questions_source_file_id",
            "exam_source_files",
            ["source_file_id"],
            ["id"],
        )
        batch_op.drop_constraint("ck_questions_region_status", type_="check")

    op.drop_column("questions", "extracted_text")
    op.drop_column("questions", "region_status")
    op.drop_column("exam_source_files", "page_dimensions")
