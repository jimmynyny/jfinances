"""investment imports

Investment statements (QFX/OFX from a broker or 401(k)) imported into a linked
investment account (services/invimport.py). investment_transactions gains
`source` (plaid | import) and `import_id`, and `plaid_investment_transaction_id`
becomes nullable (imported rows have none). Older code never reads an imported
row's missing id, and every insert it makes sets it.

Revision ID: b7d9f1a3c5e7
Revises: a4d6f8b0c2e4
Create Date: 2026-10-14 10:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'b7d9f1a3c5e7'
down_revision = 'a4d6f8b0c2e4'
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column('investment_transactions',
                  sa.Column('source', sa.String(10), nullable=False, server_default='plaid'))
    op.add_column('investment_transactions',
                  sa.Column('import_id', UUID, sa.ForeignKey('imports.id', ondelete='SET NULL'), nullable=True))
    op.alter_column('investment_transactions', 'plaid_investment_transaction_id', existing_type=sa.String(80),
                    nullable=True)
    op.create_index('ix_invtx_import', 'investment_transactions', ['import_id'])


def downgrade() -> None:
    op.execute("DELETE FROM investment_transactions WHERE plaid_investment_transaction_id IS NULL")
    op.drop_index('ix_invtx_import', table_name='investment_transactions')
    op.alter_column('investment_transactions', 'plaid_investment_transaction_id', existing_type=sa.String(80),
                    nullable=False)
    op.drop_column('investment_transactions', 'import_id')
    op.drop_column('investment_transactions', 'source')
