"""imports

Bank exports imported into an account's history (services/importer.py):
`imports` (one per uploaded file), `import_rows` (the ledger of every row
added or matched, by fingerprint, so no row is ever added twice) and
`import_profiles` (a bank's column layout, recognized by its header).
transactions gains `source` (plaid | import) and `import_id`, and
`plaid_transaction_id` becomes nullable (imported rows have none). Older code
never reads imported rows' missing id, and every insert it makes sets it.

Revision ID: a4d6f8b0c2e4
Revises: f3c5e7a9b1d3
Create Date: 2026-10-14 08:30:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'a4d6f8b0c2e4'
down_revision = 'f3c5e7a9b1d3'
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def _times():
    return [sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)]


def upgrade() -> None:
    op.create_table(
        'imports',
        sa.Column('id', UUID, primary_key=True),
        sa.Column('account_id', UUID, sa.ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('filename', sa.String(200), nullable=False),
        sa.Column('file_sha256', sa.String(64), nullable=False),
        sa.Column('format', sa.String(8), nullable=False),
        sa.Column('mapping', postgresql.JSONB, nullable=True),
        sa.Column('created_by', UUID, sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('date_from', sa.Date(), nullable=True),
        sa.Column('date_to', sa.Date(), nullable=True),
        sa.Column('rows_total', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('rows_added', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('rows_matched', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('rows_skipped', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('balances_added', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(10), nullable=False, server_default='applied'),
        sa.Column('undone_at', sa.DateTime(timezone=True), nullable=True),
        *_times(),
    )
    op.create_index('ix_imports_account', 'imports', ['account_id'])
    op.add_column('transactions', sa.Column('source', sa.String(10), nullable=False, server_default='plaid'))
    op.add_column('transactions', sa.Column('import_id', UUID, sa.ForeignKey('imports.id', ondelete='SET NULL'),
                                            nullable=True))
    op.alter_column('transactions', 'plaid_transaction_id', existing_type=sa.String(80), nullable=True)
    op.create_index('ix_transactions_import', 'transactions', ['import_id'])
    op.create_table(
        'import_rows',
        sa.Column('id', UUID, primary_key=True),
        sa.Column('import_id', UUID, sa.ForeignKey('imports.id', ondelete='CASCADE'), nullable=False),
        sa.Column('account_id', UUID, sa.ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('amount', sa.Numeric(18, 2), nullable=False),
        sa.Column('description', sa.String(300), nullable=False),
        sa.Column('status', sa.String(12), nullable=False),
        sa.Column('transaction_id', UUID, sa.ForeignKey('transactions.id', ondelete='SET NULL'), nullable=True),
        sa.Column('matched_transaction_id', UUID, sa.ForeignKey('transactions.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('account_id', 'fingerprint', name='uq_import_rows_account_fingerprint'),
    )
    op.create_index('ix_import_rows_import', 'import_rows', ['import_id'])
    op.create_table(
        'import_profiles',
        sa.Column('id', UUID, primary_key=True),
        sa.Column('signature', sa.String(32), nullable=False, unique=True),
        sa.Column('mapping', postgresql.JSONB, nullable=False),
        sa.Column('account_id', UUID, sa.ForeignKey('accounts.id', ondelete='SET NULL'), nullable=True),
        *_times(),
    )


def downgrade() -> None:
    op.drop_table('import_profiles')
    op.drop_table('import_rows')
    op.execute("DELETE FROM transactions WHERE source = 'import'")
    op.drop_index('ix_transactions_import', table_name='transactions')
    op.alter_column('transactions', 'plaid_transaction_id', existing_type=sa.String(80), nullable=False)
    op.drop_column('transactions', 'import_id')
    op.drop_column('transactions', 'source')
    op.drop_index('ix_imports_account', table_name='imports')
    op.drop_table('imports')
