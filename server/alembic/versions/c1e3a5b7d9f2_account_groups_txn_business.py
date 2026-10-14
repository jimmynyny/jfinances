"""account groups, transaction business flag

accounts.group_override: where an account counts (cash, investments, real estate,
vehicles, other assets, credit cards, loans, other liabilities) when its type
alone would put it elsewhere, set by the person; it also decides whether the
account is a liability. transactions.business: the person's say on one
transaction (true business, false personal), null to follow its account's
is_business. Both nullable; older code never reads them.

Revision ID: c1e3a5b7d9f2
Revises: b7d9f1a3c5e7
Create Date: 2026-10-14 11:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'c1e3a5b7d9f2'
down_revision = 'b7d9f1a3c5e7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('accounts', sa.Column('group_override', sa.String(24), nullable=True))
    op.add_column('transactions', sa.Column('business', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('transactions', 'business')
    op.drop_column('accounts', 'group_override')
