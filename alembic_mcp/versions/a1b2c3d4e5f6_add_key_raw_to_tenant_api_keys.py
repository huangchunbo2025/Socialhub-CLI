"""add_key_raw_to_tenant_api_keys

Revision ID: a1b2c3d4e5f6
Revises: 297f6713cf4b
Create Date: 2026-04-01 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '297f6713cf4b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add key_raw column for plain-text key storage (allows copy from portal)."""
    op.add_column(
        'tenant_api_keys',
        sa.Column('key_raw', sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    """Remove key_raw column."""
    op.drop_column('tenant_api_keys', 'key_raw')
