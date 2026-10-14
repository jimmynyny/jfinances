"""mobile_link_codes

The two-minute code a phone trades for its token (auth/mobile.py). A new
table only, so older code is unaffected.

Revision ID: e2b4d6f8a0c2
Revises: d8f0a2c4e6b8
Create Date: 2026-10-14 01:10:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'e2b4d6f8a0c2'
down_revision = 'd8f0a2c4e6b8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'mobile_link_codes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('nonce', sa.String(64), nullable=False),
        sa.Column('code_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('device_name', sa.String(120), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('mobile_link_codes')
