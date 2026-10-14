"""accounts.secured_by_id

The offline asset (home, car) a loan is secured by, set by hand. Nullable,
and code that predates it never reads it, so it is safe while other services
still run the previous release. Deleting the asset clears the link.

Revision ID: 7c1f0e9a2b44
Revises: 303f4e31c536
Create Date: 2026-10-13 22:20:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '7c1f0e9a2b44'
down_revision = '303f4e31c536'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('accounts', sa.Column('secured_by_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_accounts_secured_by', 'accounts', 'accounts', ['secured_by_id'], ['id'],
                          ondelete='SET NULL')
    op.create_index('ix_accounts_secured_by', 'accounts', ['secured_by_id'])


def downgrade() -> None:
    op.drop_index('ix_accounts_secured_by', table_name='accounts')
    op.drop_constraint('fk_accounts_secured_by', 'accounts', type_='foreignkey')
    op.drop_column('accounts', 'secured_by_id')
