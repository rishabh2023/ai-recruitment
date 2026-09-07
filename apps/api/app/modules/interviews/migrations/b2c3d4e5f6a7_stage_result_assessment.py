"""stage_results.assessment — LLM recruiter assessment of a completed call (F-009 follow-up)

Stores the platform-LLM evaluation of a screening/interview call against the stage's success
criteria (recommendation + per-criterion notes + recruiter summary), shown in Evidence & Results.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "stage_results",
        sa.Column("assessment", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("stage_results", "assessment")
