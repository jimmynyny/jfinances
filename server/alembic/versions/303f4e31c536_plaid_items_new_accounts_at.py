"""plaid_items.new_accounts_at

Set by the ITEM/NEW_ACCOUNTS_AVAILABLE webhook, cleared when update mode
finishes. Nullable, so code still running without it is unaffected.

Revision ID: 303f4e31c536
Revises: ba0aeebdf1a6
Create Date: 2026-10-13 18:42:16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '303f4e31c536'
down_revision = 'ba0aeebdf1a6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('plaid_items', sa.Column('new_accounts_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('plaid_items', 'new_accounts_at')
