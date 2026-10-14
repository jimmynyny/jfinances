"""valuations

Monthly market values for offline homes and vehicles (services/valuations.py):
`asset_details` (a home's address, a vehicle's VIN and mileage) and
`valuations` (every request to RentCast or MarketCheck, recorded before it is
sent, unique per account, provider, kind and month: the database itself refuses
a second request in a month). New tables only; older code never reads them.

Revision ID: d2f4b6c8e0a3
Revises: c1e3a5b7d9f2
Create Date: 2026-10-14 12:30:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'd2f4b6c8e0a3'
down_revision = 'c1e3a5b7d9f2'
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
MONEY = sa.Numeric(18, 2)


def upgrade() -> None:
    op.create_table(
        'asset_details',
        sa.Column('account_id', UUID, sa.ForeignKey('accounts.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('valuation_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('address_line', sa.String(200)), sa.Column('city', sa.String(100)), sa.Column('state', sa.String(2)),
        sa.Column('zip', sa.String(10)), sa.Column('property_type', sa.String(40)), sa.Column('bedrooms', sa.Integer()),
        sa.Column('bathrooms', sa.Numeric(4, 1)), sa.Column('square_feet', sa.Integer()),
        sa.Column('vin', sa.String(17)), sa.Column('mileage', sa.Integer()), sa.Column('mileage_as_of', sa.Date()),
        sa.Column('miles_per_month', sa.Integer()),
        sa.Column('garage_account_id', UUID, sa.ForeignKey('accounts.id', ondelete='SET NULL')),
        sa.Column('vehicle_label', sa.String(200)), sa.Column('decoded_vin', sa.String(17)),
        sa.Column('updated_by', UUID, sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        'valuations',
        sa.Column('id', UUID, primary_key=True),
        sa.Column('account_id', UUID, sa.ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider', sa.String(20), nullable=False),
        sa.Column('kind', sa.String(10), nullable=False),
        sa.Column('month', sa.Date(), nullable=False),
        sa.Column('as_of', sa.Date(), nullable=False),
        sa.Column('status', sa.String(10), nullable=False, server_default='pending'),
        sa.Column('value', MONEY), sa.Column('low', MONEY), sa.Column('high', MONEY),
        sa.Column('inputs', postgresql.JSONB), sa.Column('detail', postgresql.JSONB),
        sa.Column('error', sa.String(300)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('account_id', 'provider', 'kind', 'month', name='uq_valuations_once_a_month'),
    )
    op.create_index('ix_valuations_provider_month', 'valuations', ['provider', 'month'])


def downgrade() -> None:
    op.drop_index('ix_valuations_provider_month', table_name='valuations')
    op.drop_table('valuations')
    op.drop_table('asset_details')
