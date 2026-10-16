"""recurring kind

`recurring_streams.kind` (subscription | recurring) and `kind_source` (model |
user): services/subscriptions.py sorts subscriptions from other recurring
charges, and the user's choice is kept. Nullable columns; older code never
reads them.

Revision ID: a5c7e9b1d3f6
Revises: f4b6d8a0c2e5
Create Date: 2026-10-16 10:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'a5c7e9b1d3f6'
down_revision = 'f4b6d8a0c2e5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('recurring_streams', sa.Column('kind', sa.String(12)))
    op.add_column('recurring_streams', sa.Column('kind_source', sa.String(8)))


def downgrade() -> None:
    op.drop_column('recurring_streams', 'kind_source')
    op.drop_column('recurring_streams', 'kind')
