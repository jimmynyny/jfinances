"""account_terms

What the person tells us about an account that its bank doesn't report: a
loan's rate, original amount, start, term and payment; a card's APR, limit and
statement day; a savings rate (services/terms.py). A new table only, so older
code is unaffected.

Revision ID: f3c5e7a9b1d3
Revises: e2b4d6f8a0c2
Create Date: 2026-10-14 07:45:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'f3c5e7a9b1d3'
down_revision = 'e2b4d6f8a0c2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'account_terms',
        sa.Column('account_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('accounts.id', ondelete='CASCADE'),
                  primary_key=True),
        sa.Column('interest_rate_pct', sa.Numeric(9, 4), nullable=True),
        sa.Column('rate_type', sa.String(20), nullable=True),
        sa.Column('original_principal', sa.Numeric(18, 2), nullable=True),
        sa.Column('origination_date', sa.Date(), nullable=True),
        sa.Column('term_months', sa.Integer(), nullable=True),
        sa.Column('payment_amount', sa.Numeric(18, 2), nullable=True),
        sa.Column('escrow_amount', sa.Numeric(18, 2), nullable=True),
        sa.Column('payment_day', sa.Integer(), nullable=True),
        sa.Column('statement_day', sa.Integer(), nullable=True),
        sa.Column('credit_limit', sa.Numeric(18, 2), nullable=True),
        sa.Column('minimum_payment', sa.Numeric(18, 2), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('account_terms')
