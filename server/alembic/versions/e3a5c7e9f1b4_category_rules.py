"""category rules

The person's latest category per merchant, account and direction, learned from
their edits and given to new transactions (services/category_rules.py). A new
table only; older code never reads it.

Revision ID: e3a5c7e9f1b4
Revises: d2f4b6c8e0a3
Create Date: 2026-10-14 13:30:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'e3a5c7e9f1b4'
down_revision = 'd2f4b6c8e0a3'
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        'category_rules',
        sa.Column('id', UUID, primary_key=True),
        sa.Column('account_id', UUID, sa.ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('merchant', sa.String(300), nullable=False),
        sa.Column('direction', sa.String(3), nullable=False),
        sa.Column('user_category', sa.String(80), nullable=False),
        sa.Column('learned_from', UUID, sa.ForeignKey('transactions.id', ondelete='SET NULL')),
        sa.Column('times_applied', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_applied_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('account_id', 'merchant', 'direction', name='uq_category_rules_key'),
    )


def downgrade() -> None:
    op.drop_table('category_rules')
