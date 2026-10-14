"""link code challenge method

`mobile_link_codes.challenge_method`: "S256" when the app sent the SHA-256 of a
secret as its nonce and will redeem with the secret (PKCE; the Android app,
whose custom-scheme redirect another app could claim). Null keeps the iOS
flow. A nullable column; older code never reads it.

Revision ID: f4b6d8a0c2e5
Revises: e3a5c7e9f1b4
Create Date: 2026-10-14 15:30:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'f4b6d8a0c2e5'
down_revision = 'e3a5c7e9f1b4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('mobile_link_codes', sa.Column('challenge_method', sa.String(8)))


def downgrade() -> None:
    op.drop_column('mobile_link_codes', 'challenge_method')
