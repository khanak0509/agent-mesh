"""study plans + practice + daily concepts

Revision ID: 002_path
Revises: 001_initial
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002_path"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "study_plans",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("topic", sa.String(200), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("steps", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(32), server_default="proposed"),
        sa.Column("current_step", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("request_id", name="uq_study_plan_request_id"),
    )
    op.create_index("ix_study_plans_user_id", "study_plans", ["user_id"])
    op.create_index("ix_study_plans_status", "study_plans", ["status"])

    op.create_table(
        "practice_problems",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("slug_day", sa.String(32), nullable=True),
        sa.Column("track", sa.String(64), nullable=False),
        sa.Column("difficulty", sa.String(16), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("hints", postgresql.JSONB(), server_default="[]"),
        sa.Column("solution", sa.Text(), nullable=True),
        sa.Column("rubric", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.JSONB(), server_default="[]"),
        sa.Column("is_daily", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_practice_problems_track", "practice_problems", ["track"])
    op.create_index("ix_practice_problems_slug_day", "practice_problems", ["slug_day"])

    op.create_table(
        "practice_attempts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("problem_id", sa.String(64), sa.ForeignKey("practice_problems.id"), nullable=False),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=False),
        sa.Column("passed", sa.Boolean(), server_default="false"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("request_id", name="uq_practice_attempt_request_id"),
    )
    op.create_index("ix_practice_attempts_user_id", "practice_attempts", ["user_id"])
    op.create_index("ix_practice_attempts_problem_id", "practice_attempts", ["problem_id"])

    op.create_table(
        "daily_concepts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("day", sa.String(16), nullable=False, unique=True),
        sa.Column("track", sa.String(64), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("why_it_matters", sa.Text(), nullable=False),
        sa.Column("try_this", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("daily_concepts")
    op.drop_table("practice_attempts")
    op.drop_table("practice_problems")
    op.drop_table("study_plans")
