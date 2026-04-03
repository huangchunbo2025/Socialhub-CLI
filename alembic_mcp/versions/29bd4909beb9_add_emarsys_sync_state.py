"""add_emarsys_sync_state

Revision ID: 29bd4909beb9
Revises: b2c3d4e5f6a7
Create Date: 2026-04-03 12:55:47.414631

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '29bd4909beb9'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "emarsys_sync_state",
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("dataset_id", sa.String(128), nullable=False),
        sa.Column("table_name", sa.String(128), nullable=False),
        sa.Column("last_sync_time", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("rows_synced_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_synced_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("tenant_id", "dataset_id", "table_name"),
    )


def downgrade() -> None:
    op.drop_table("emarsys_sync_state")
