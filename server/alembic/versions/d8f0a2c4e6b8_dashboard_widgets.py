"""dashboard_widgets and users.dashboard_columns

Each person's Overview as an ordered list of widgets. A new table and a
column with a default, so older code is unaffected.

Revision ID: d8f0a2c4e6b8
Revises: c6e8f0a2b4d6
Create Date: 2026-10-13 23:40:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'd8f0a2c4e6b8'
down_revision = 'c6e8f0a2b4d6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('dashboard_columns', sa.Integer(), nullable=True))
    op.create_table(
        'dashboard_widgets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('view', sa.String(40), nullable=False),
        sa.Column('settings', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('size', sa.String(8), nullable=False, server_default='wide'),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_dashboard_widgets_user', 'dashboard_widgets', ['user_id', 'position'])


def downgrade() -> None:
    op.drop_index('ix_dashboard_widgets_user', table_name='dashboard_widgets')
    op.drop_table('dashboard_widgets')
    op.drop_column('users', 'dashboard_columns')
