"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-03-21 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


developer_role = sa.Enum("developer", "store_admin", name="developer_role")
developer_status = sa.Enum("active", "suspended", "pending_verification", name="developer_status")
skill_category = sa.Enum("data", "analytics", "marketing", "integration", "utility", name="skill_category")
skill_status = sa.Enum("active", "suspended", name="skill_status")
version_status = sa.Enum(
    "draft",
    "reviewing",
    "published",
    "rejected",
    "deprecated",
    "revoked",
    name="version_status",
)
review_status = sa.Enum("pending", "in_review", "approved", "rejected", name="review_status")


def upgrade() -> None:
    bind = op.get_bind()
    developer_role.create(bind, checkfirst=True)
    developer_status.create(bind, checkfirst=True)
    skill_category.create(bind, checkfirst=True)
    skill_status.create(bind, checkfirst=True)
    version_status.create(bind, checkfirst=True)
    review_status.create(bind, checkfirst=True)

    op.create_table(
        "developers",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("role", developer_role, nullable=False),
        sa.Column("status", developer_status, nullable=False, server_default="active"),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("website", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("email", name="uq_developers_email"),
    )
    op.create_index("idx_developers_role_status", "developers", ["role", "status"])

    op.create_table(
        "skills",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("developer_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", skill_category, nullable=False),
        sa.Column("status", skill_status, nullable=False, server_default="active"),
        sa.Column("featured", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("icon_url", sa.String(length=255), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("download_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["developer_id"], ["developers.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("name", name="uq_skills_name"),
    )
    op.create_index("idx_skills_developer_id", "skills", ["developer_id"])
    op.create_index("idx_skills_category_status", "skills", ["category", "status"])
    op.create_index("idx_skills_featured_status", "skills", ["featured", "status"])

    op.create_table(
        "skill_versions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("skill_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("status", version_status, nullable=False, server_default="draft"),
        sa.Column("package_filename", sa.String(length=255), nullable=False),
        sa.Column("package_path", sa.String(length=500), nullable=False),
        sa.Column("package_size", sa.BigInteger(), nullable=False),
        sa.Column("package_hash", sa.String(length=128), nullable=False),
        sa.Column("manifest_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("scan_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("release_notes", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("skill_id", "version", name="uq_skill_versions_skill_id_version"),
    )
    op.create_index("idx_skill_versions_skill_id", "skill_versions", ["skill_id"])
    op.create_index("idx_skill_versions_status", "skill_versions", ["status"])
    op.create_index("idx_skill_versions_skill_status", "skill_versions", ["skill_id", "status"])

    op.create_table(
        "skill_certifications",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("skill_version_id", sa.BigInteger(), nullable=False),
        sa.Column("certificate_serial", sa.String(length=120), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.String(length=128), nullable=False),
        sa.Column("public_key_id", sa.String(length=120), nullable=False),
        sa.Column("issued_by", sa.BigInteger(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["issued_by"], ["developers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["skill_version_id"], ["skill_versions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("certificate_serial", name="uq_skill_certifications_certificate_serial"),
        sa.UniqueConstraint("skill_version_id", name="uq_skill_certifications_skill_version_id"),
    )
    op.create_index("idx_skill_certifications_revoked_at", "skill_certifications", ["revoked_at"])
    op.create_index("idx_skill_certifications_issued_by", "skill_certifications", ["issued_by"])

    op.create_table(
        "skill_reviews",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("skill_version_id", sa.BigInteger(), nullable=False),
        sa.Column("reviewer_id", sa.BigInteger(), nullable=True),
        sa.Column("status", review_status, nullable=False, server_default="pending"),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("scan_result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["reviewer_id"], ["developers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["skill_version_id"], ["skill_versions.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_skill_reviews_skill_version_id", "skill_reviews", ["skill_version_id"])
    op.create_index("idx_skill_reviews_reviewer_id", "skill_reviews", ["reviewer_id"])
    op.create_index("idx_skill_reviews_status", "skill_reviews", ["status"])


def downgrade() -> None:
    op.drop_index("idx_skill_reviews_status", table_name="skill_reviews")
    op.drop_index("idx_skill_reviews_reviewer_id", table_name="skill_reviews")
    op.drop_index("idx_skill_reviews_skill_version_id", table_name="skill_reviews")
    op.drop_table("skill_reviews")
    op.drop_index("idx_skill_certifications_issued_by", table_name="skill_certifications")
    op.drop_index("idx_skill_certifications_revoked_at", table_name="skill_certifications")
    op.drop_table("skill_certifications")
    op.drop_index("idx_skill_versions_skill_status", table_name="skill_versions")
    op.drop_index("idx_skill_versions_status", table_name="skill_versions")
    op.drop_index("idx_skill_versions_skill_id", table_name="skill_versions")
    op.drop_table("skill_versions")
    op.drop_index("idx_skills_featured_status", table_name="skills")
    op.drop_index("idx_skills_category_status", table_name="skills")
    op.drop_index("idx_skills_developer_id", table_name="skills")
    op.drop_table("skills")
    op.drop_index("idx_developers_role_status", table_name="developers")
    op.drop_table("developers")

    bind = op.get_bind()
    review_status.drop(bind, checkfirst=True)
    version_status.drop(bind, checkfirst=True)
    skill_status.drop(bind, checkfirst=True)
    skill_category.drop(bind, checkfirst=True)
    developer_status.drop(bind, checkfirst=True)
    developer_role.drop(bind, checkfirst=True)
