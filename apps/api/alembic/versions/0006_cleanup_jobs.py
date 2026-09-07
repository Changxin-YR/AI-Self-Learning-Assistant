"""persist external resource cleanup intents"""
from alembic import op
import sqlalchemy as sa


revision = "0006_cleanup_jobs"
down_revision = "0005_plan_schedule"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("cleanup_jobs"):
        return
    op.create_table(
        "cleanup_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False, index=True),
        sa.Column("resource_type", sa.String(length=40), nullable=False, index=True),
        sa.Column("resource_id", sa.Integer(), nullable=False, index=True),
        sa.Column("operation", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING", index=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=255), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("cleanup_jobs")
