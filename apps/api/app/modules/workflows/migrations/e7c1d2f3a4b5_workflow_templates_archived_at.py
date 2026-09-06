"""workflow_templates.archived_at

Add a nullable archived_at so org funnels (workflow templates) can be archived without
deletion — jobs that already adopted a funnel keep working (source_template_id is ON DELETE
SET NULL regardless), and archived funnels are hidden from the default library list.

Revision ID: e7c1d2f3a4b5
Revises: d3e4f5a6b7c8
Create Date: 2026-09-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7c1d2f3a4b5"
down_revision: Union[str, None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workflow_templates",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workflow_templates", "archived_at")
