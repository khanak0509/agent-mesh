"""practice problem formats (mcq/short/code)

Revision ID: 004_practice_fmt
Revises: 003_ratings
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "004_practice_fmt"
down_revision: Union[str, None] = "003_ratings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "practice_problems",
        sa.Column("format", sa.String(16), server_default="short", nullable=False),
    )
    op.add_column(
        "practice_problems",
        sa.Column("options", postgresql.JSONB(), server_default="[]"),
    )
    op.add_column(
        "practice_problems",
        sa.Column("correct_key", sa.String(8), nullable=True),
    )
    op.add_column(
        "practice_problems",
        sa.Column("explanation", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("practice_problems", "explanation")
    op.drop_column("practice_problems", "correct_key")
    op.drop_column("practice_problems", "options")
    op.drop_column("practice_problems", "format")
