"""recurring_streams and dismissed_alerts

Subscriptions found in transactions, with the user's verdict, and the alerts
the user waved off. New tables only, so older code is unaffected.

Revision ID: b3f5a7c9d1e2
Revises: 9d2e4b6c8a10
Create Date: 2026-10-13 23:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'b3f5a7c9d1e2'
down_revision = '9d2e4b6c8a10'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'recurring_streams',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('merchant', sa.String(300), nullable=False),
        sa.Column('name', sa.String(200)),
        sa.Column('cadence', sa.String(12), nullable=False),
        sa.Column('interval_days', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(18, 2), nullable=False),
        sa.Column('last_amount', sa.Numeric(18, 2), nullable=False),
        sa.Column('previous_amount', sa.Numeric(18, 2)),
        sa.Column('price_changed_on', sa.Date()),
        sa.Column('first_date', sa.Date(), nullable=False),
        sa.Column('last_date', sa.Date(), nullable=False),
        sa.Column('next_date', sa.Date(), nullable=False),
        sa.Column('charge_count', sa.Integer(), nullable=False),
        sa.Column('category', sa.String(80)),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('accounts.id', ondelete='SET NULL')),
        sa.Column('status', sa.String(12), nullable=False, server_default='detected'),
        sa.Column('status_set_at', sa.DateTime(timezone=True)),
        sa.Column('seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_recurring_merchant', 'recurring_streams', ['merchant'])
    op.create_table(
        'dismissed_alerts',
        sa.Column('key', sa.String(200), primary_key=True),
        sa.Column('dismissed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('dismissed_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
    )


def downgrade() -> None:
    op.drop_table('dismissed_alerts')
    op.drop_index('ix_recurring_merchant', table_name='recurring_streams')
    op.drop_table('recurring_streams')
