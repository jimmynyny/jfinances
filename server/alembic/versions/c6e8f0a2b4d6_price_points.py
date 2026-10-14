"""price_points

Daily closes from public market data for benchmarks and held securities. A
new table only, so older code is unaffected.

Revision ID: c6e8f0a2b4d6
Revises: b3f5a7c9d1e2
Create Date: 2026-10-13 23:10:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'c6e8f0a2b4d6'
down_revision = 'b3f5a7c9d1e2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'price_points',
        sa.Column('series', sa.String(48), primary_key=True),
        sa.Column('date', sa.Date(), primary_key=True),
        sa.Column('close', sa.Numeric(24, 8), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('price_points')
