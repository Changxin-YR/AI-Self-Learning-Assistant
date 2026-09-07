"""add storage, vector and agent audit fields"""
from alembic import op
import sqlalchemy as sa

revision = "0002_production_fields"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    document_columns = {column["name"] for column in inspector.get_columns("documents")}
    chunk_columns = {column["name"] for column in inspector.get_columns("document_chunks")}
    if "storage_key" not in document_columns:
        op.add_column("documents", sa.Column("storage_key", sa.String(length=500), nullable=False, server_default=""))
    if "qdrant_point_id" not in chunk_columns:
        op.add_column("document_chunks", sa.Column("qdrant_point_id", sa.String(length=64), nullable=True))
    if "agent_runs" not in inspector.get_table_names():
        op.create_table("agent_runs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.Integer(), nullable=False), sa.Column("agent_name", sa.String(length=80), nullable=False), sa.Column("input_text", sa.Text(), nullable=False), sa.Column("status", sa.String(length=20), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False))
    if "agent_tool_calls" not in inspector.get_table_names():
        op.create_table("agent_tool_calls", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("agent_run_id", sa.Integer(), nullable=False), sa.Column("user_id", sa.Integer(), nullable=False), sa.Column("tool_name", sa.String(length=80), nullable=False), sa.Column("arguments_json", sa.JSON(), nullable=False), sa.Column("result_summary", sa.String(length=255), nullable=False), sa.Column("status", sa.String(length=20), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False))


def downgrade() -> None:
    op.drop_table("agent_tool_calls")
    op.drop_table("agent_runs")
    op.drop_column("document_chunks", "qdrant_point_id")
    op.drop_column("documents", "storage_key")
