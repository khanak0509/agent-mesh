"""ratings

Revision ID: 003_ratings
Revises: 002_path
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003_ratings"
down_revision: Union[str, None] = "002_path"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ratings",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(128), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "target_type", "target_id", name="uq_rating_user_target"),
    )
    op.create_index("ix_ratings_user_id", "ratings", ["user_id"])
    op.create_index("ix_ratings_target", "ratings", ["target_type", "target_id"])


def downgrade() -> None:
    op.drop_table("ratings")
