"""persist AI-generated study plan schedule"""
from alembic import op
import sqlalchemy as sa


revision = "0005_plan_schedule"
down_revision = "0004_chat_and_concurrency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("study_plans")}
    if "generated_schedule" not in columns:
        op.add_column("study_plans", sa.Column("generated_schedule", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("study_plans", "generated_schedule")
