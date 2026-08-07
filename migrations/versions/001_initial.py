"""initial schema

Revision ID: 001_initial
Revises:
Create Date: 2026-08-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("display_name", sa.String(120), nullable=False, server_default="Student"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "study_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("topic", sa.String(200), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_active_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_study_sessions_user_id", "study_sessions", ["user_id"])

    op.create_table(
        "study_interactions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_id", sa.String(64), sa.ForeignKey("study_sessions.id"), nullable=True),
        sa.Column("topic", sa.String(200), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("request_id", name="uq_study_request_id"),
    )
    op.create_index("ix_study_interactions_request_id", "study_interactions", ["request_id"])
    op.create_index("ix_study_interactions_user_id", "study_interactions", ["user_id"])

    op.create_table(
        "quizzes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("topic", sa.String(200), nullable=False),
        sa.Column("questions", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("request_id", name="uq_quiz_request_id"),
    )
    op.create_index("ix_quizzes_request_id", "quizzes", ["request_id"])
    op.create_index("ix_quizzes_user_id", "quizzes", ["user_id"])

    op.create_table(
        "quiz_attempts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("quiz_id", sa.String(64), sa.ForeignKey("quizzes.id"), nullable=False),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("answers", postgresql.JSONB(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("request_id", name="uq_quiz_attempt_request_id"),
    )
    op.create_index("ix_quiz_attempts_request_id", "quiz_attempts", ["request_id"])
    op.create_index("ix_quiz_attempts_quiz_id", "quiz_attempts", ["quiz_id"])
    op.create_index("ix_quiz_attempts_user_id", "quiz_attempts", ["user_id"])

    op.create_table(
        "flashcards",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("topic", sa.String(200), nullable=False),
        sa.Column("front", sa.Text(), nullable=False),
        sa.Column("back", sa.Text(), nullable=False),
        sa.Column("hint", sa.Text(), nullable=True),
        sa.Column("times_seen", sa.Integer(), server_default="0"),
        sa.Column("times_correct", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("request_id", "front", name="uq_flashcard_req_front"),
    )
    op.create_index("ix_flashcards_request_id", "flashcards", ["request_id"])
    op.create_index("ix_flashcards_user_id", "flashcards", ["user_id"])
    op.create_index("ix_flashcards_topic", "flashcards", ["topic"])

    op.create_table(
        "progress_snapshots",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("topics_studied", postgresql.JSONB(), server_default="{}"),
        sa.Column("quiz_scores", postgresql.JSONB(), server_default="[]"),
        sa.Column("streak_days", sa.Integer(), server_default="0"),
        sa.Column("total_interactions", sa.Integer(), server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_progress_snapshots_user_id", "progress_snapshots", ["user_id"])

    op.create_table(
        "processed_messages",
        sa.Column("request_id", sa.String(64), primary_key=True),
        sa.Column("service", sa.String(64), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("processed_messages")
    op.drop_table("progress_snapshots")
    op.drop_table("flashcards")
    op.drop_table("quiz_attempts")
    op.drop_table("quizzes")
    op.drop_table("study_interactions")
    op.drop_table("study_sessions")
    op.drop_table("users")
