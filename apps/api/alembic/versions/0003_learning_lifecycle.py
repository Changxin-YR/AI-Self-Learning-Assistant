"""complete document, plan, quiz and memory lifecycle fields"""
from alembic import op
import sqlalchemy as sa

revision = "0003_learning_lifecycle"
down_revision = "0002_production_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    def add(table: str, name: str, column: sa.Column) -> None:
        if name not in {item["name"] for item in inspector.get_columns(table)}:
            op.add_column(table, column)

    add("documents", "original_filename", sa.Column("original_filename", sa.String(255), nullable=False, server_default=""))
    add("users", "status", sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"))
    add("documents", "mime_type", sa.Column("mime_type", sa.String(120), nullable=False, server_default="application/octet-stream"))
    add("documents", "extension", sa.Column("extension", sa.String(10), nullable=False, server_default=""))
    add("documents", "deleted_at", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    add("document_chunks", "created_at", sa.Column("created_at", sa.DateTime(), nullable=True))
    add("conversations", "updated_at", sa.Column("updated_at", sa.DateTime(), nullable=True))
    add("conversations", "deleted_at", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    add("messages", "citations", sa.Column("citations", sa.JSON(), nullable=False, server_default="[]"))
    add("study_plans", "foundation_level", sa.Column("foundation_level", sa.String(20), nullable=False, server_default="一般"))
    add("study_plans", "intensity", sa.Column("intensity", sa.String(20), nullable=False, server_default="标准"))
    add("study_plans", "timezone", sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Shanghai"))
    add("study_plans", "generated_by_ai", sa.Column("generated_by_ai", sa.Boolean(), nullable=False, server_default=sa.true()))
    add("study_tasks", "actual_minutes", sa.Column("actual_minutes", sa.Integer(), nullable=False, server_default="0"))
    add("study_tasks", "scheduled_date", sa.Column("scheduled_date", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")))
    add("study_tasks", "created_at", sa.Column("created_at", sa.DateTime(), nullable=True))
    add("quizzes", "max_score", sa.Column("max_score", sa.Integer(), nullable=True))
    add("quizzes", "submitted_at", sa.Column("submitted_at", sa.DateTime(), nullable=True))
    add("quiz_questions", "reference_answer", sa.Column("reference_answer", sa.Text(), nullable=False, server_default=""))
    add("quiz_questions", "scoring_points", sa.Column("scoring_points", sa.JSON(), nullable=False, server_default="[]"))
    add("quiz_questions", "evidence", sa.Column("evidence", sa.Text(), nullable=False, server_default=""))
    add("quiz_questions", "source_chunk_ids", sa.Column("source_chunk_ids", sa.JSON(), nullable=False, server_default="[]"))
    add("quiz_questions", "difficulty", sa.Column("difficulty", sa.String(20), nullable=False, server_default="medium"))
    add("quiz_answers", "ai_feedback", sa.Column("ai_feedback", sa.Text(), nullable=False, server_default=""))
    add("quiz_answers", "updated_at", sa.Column("updated_at", sa.DateTime(), nullable=True))
    add("wrong_questions", "last_wrong_at", sa.Column("last_wrong_at", sa.DateTime(), nullable=True))
    add("wrong_questions", "mastered", sa.Column("mastered", sa.Boolean(), nullable=False, server_default=sa.false()))
    add("knowledge_mastery", "confidence", sa.Column("confidence", sa.Integer(), nullable=False, server_default="20"))
    add("knowledge_mastery", "quiz_count", sa.Column("quiz_count", sa.Integer(), nullable=False, server_default="0"))
    add("knowledge_mastery", "correct_count", sa.Column("correct_count", sa.Integer(), nullable=False, server_default="0"))
    add("knowledge_mastery", "last_reviewed_at", sa.Column("last_reviewed_at", sa.DateTime(), nullable=True))
    indexes = {item["name"] for item in inspector.get_indexes("study_tasks")}
    if "uq_study_tasks_plan_date_idx" not in indexes:
        op.create_index("uq_study_tasks_plan_date_idx", "study_tasks", ["study_plan_id", "scheduled_date"], unique=True)
    answer_indexes = {item["name"] for item in inspector.get_indexes("quiz_answers")}
    if "uq_quiz_answers_question_idx" not in answer_indexes:
        op.create_index("uq_quiz_answers_question_idx", "quiz_answers", ["quiz_id", "question_id", "user_id"], unique=True)
    if "user_memories" not in inspector.get_table_names():
        op.create_table(
            "user_memories",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False, index=True),
            sa.Column("memory_type", sa.String(40), nullable=False),
            sa.Column("memory_key", sa.String(120), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("importance", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("source", sa.String(80), nullable=False, server_default="user"),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    op.drop_index("uq_quiz_answers_question_idx", table_name="quiz_answers")
    op.drop_index("uq_study_tasks_plan_date_idx", table_name="study_tasks")
    op.drop_table("user_memories")
