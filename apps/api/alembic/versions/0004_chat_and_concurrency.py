"""persist chat citations and protect concurrent submissions"""
from alembic import op
import sqlalchemy as sa

revision = "0004_chat_and_concurrency"
down_revision = "0003_learning_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    message_columns = {item["name"] for item in inspector.get_columns("messages")}
    if "citations" not in message_columns:
        op.add_column("messages", sa.Column("citations", sa.JSON(), nullable=False, server_default="[]"))
    task_indexes = {item["name"] for item in inspector.get_indexes("study_tasks")}
    if not ({"uq_study_tasks_plan_date", "uq_study_tasks_plan_date_idx"} & task_indexes):
        op.create_index("uq_study_tasks_plan_date_idx", "study_tasks", ["study_plan_id", "scheduled_date"], unique=True)
    answer_indexes = {item["name"] for item in inspector.get_indexes("quiz_answers")}
    if not ({"uq_quiz_answers_question", "uq_quiz_answers_question_idx"} & answer_indexes):
        op.create_index("uq_quiz_answers_question_idx", "quiz_answers", ["quiz_id", "question_id", "user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_quiz_answers_question_idx", table_name="quiz_answers")
    op.drop_index("uq_study_tasks_plan_date_idx", table_name="study_tasks")
    op.drop_column("messages", "citations")
