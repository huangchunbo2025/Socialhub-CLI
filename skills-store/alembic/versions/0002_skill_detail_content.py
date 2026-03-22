"""add skill detail content fields

Revision ID: 0002_skill_detail_content
Revises: 0001_initial_schema
Create Date: 2026-03-22 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_skill_detail_content"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("skills", sa.Column("license_name", sa.String(length=120), nullable=True))
    op.add_column("skills", sa.Column("license_url", sa.String(length=255), nullable=True))
    op.add_column("skills", sa.Column("homepage_url", sa.String(length=255), nullable=True))
    op.add_column("skills", sa.Column("runtime_requirements", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("skills", sa.Column("install_guidance", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("skills", sa.Column("security_review", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("skills", sa.Column("docs_sections", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("skills", "docs_sections")
    op.drop_column("skills", "security_review")
    op.drop_column("skills", "install_guidance")
    op.drop_column("skills", "runtime_requirements")
    op.drop_column("skills", "homepage_url")
    op.drop_column("skills", "license_url")
    op.drop_column("skills", "license_name")
