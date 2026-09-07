"""hunar_agent_configs.spec — editable per-stage agent profile (objective + collect) (F-009)

Stores the product-safe, recruiter-editable summary of what a stage's voice agent does, so the
UI has clear visibility and the objective/collect can be edited without touching the (possibly
approved/locked) funnel structure.

Revision ID: a1b2c3d4e5f6
Revises: f8a1c2d3e4b5
Create Date: 2026-09-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f8a1c2d3e4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "hunar_agent_configs",
        sa.Column("spec", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("hunar_agent_configs", "spec")
