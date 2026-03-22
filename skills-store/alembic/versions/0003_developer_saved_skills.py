"""developer saved skills

Revision ID: 0003_developer_saved_skills
Revises: 0002_skill_detail_content
Create Date: 2026-03-22 22:50:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0003_developer_saved_skills"
down_revision = "0002_skill_detail_content"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "developers",
        sa.Column(
            "saved_skills",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.alter_column("developers", "saved_skills", server_default=None)


def downgrade() -> None:
    op.drop_column("developers", "saved_skills")
