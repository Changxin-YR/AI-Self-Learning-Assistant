"""persist moderation decisions and user reports"""
from alembic import op
import sqlalchemy as sa


revision = "0007_content_safety"
down_revision = "0006_cleanup_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("moderation_logs"):
        op.create_table(
            "moderation_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=True, index=True),
            sa.Column("content_type", sa.String(length=30), nullable=False),
            sa.Column("decision", sa.String(length=20), nullable=False, index=True),
            sa.Column("reason", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("content_hash", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    if not inspector.has_table("user_reports"):
        op.create_table(
            "user_reports",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False, index=True),
            sa.Column("target_type", sa.String(length=30), nullable=False),
            sa.Column("target_id", sa.Integer(), nullable=False),
            sa.Column("reason", sa.String(length=500), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="OPEN", index=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )


def downgrade() -> None:
    op.drop_table("user_reports")
    op.drop_table("moderation_logs")
