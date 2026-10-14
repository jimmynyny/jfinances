"""accounts.is_business

Marks business accounts so Insights can keep them out of personal numbers.
Defaults to false for every existing row; code that predates it never reads it.

Revision ID: 9d2e4b6c8a10
Revises: 7c1f0e9a2b44
Create Date: 2026-10-13 22:30:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '9d2e4b6c8a10'
down_revision = '7c1f0e9a2b44'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('accounts', sa.Column('is_business', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('accounts', 'is_business')
