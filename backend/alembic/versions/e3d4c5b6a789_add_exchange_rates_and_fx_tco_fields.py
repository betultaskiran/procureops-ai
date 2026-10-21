"""add_exchange_rates_and_fx_tco_fields

Revision ID: e3d4c5b6a789
Revises: 9b4a1c2e3f5d
Create Date: 2026-10-21 13:35:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3d4c5b6a789'
down_revision: Union[str, None] = '9b4a1c2e3f5d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create exchange_rates table
    op.create_table(
        'exchange_rates',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('source_currency', sa.String(length=3), nullable=False),
        sa.Column('target_currency', sa.String(length=3), nullable=False),
        sa.Column('rate', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('rate_type', sa.String(length=20), nullable=False, server_default='ForexSelling'),
        sa.Column('source', sa.String(length=20), nullable=False, server_default='TCMB'),
        sa.Column('rate_date', sa.Date(), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('unit', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('bulletin_no', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_currency', 'target_currency', 'rate_type', 'rate_date', 'source', name='uq_exchange_rates_entry')
    )
    op.create_index('ix_exchange_rates_source_currency', 'exchange_rates', ['source_currency'], unique=False)
    op.create_index('ix_exchange_rates_target_currency', 'exchange_rates', ['target_currency'], unique=False)
    op.create_index('ix_exchange_rates_rate_date', 'exchange_rates', ['rate_date'], unique=False)
    op.create_index('ix_exchange_rates_lookup', 'exchange_rates', ['source_currency', 'target_currency', 'rate_date'], unique=False)

    # 2. Add nullable FX fields to tco_results
    op.add_column('tco_results', sa.Column('converted_total_tco', sa.Numeric(precision=14, scale=4), nullable=True))
    op.add_column('tco_results', sa.Column('target_currency', sa.String(length=3), nullable=True))
    op.add_column('tco_results', sa.Column('exchange_rate', sa.Numeric(precision=18, scale=6), nullable=True))
    op.add_column('tco_results', sa.Column('exchange_rate_date', sa.Date(), nullable=True))
    op.add_column('tco_results', sa.Column('exchange_rate_source', sa.String(length=20), nullable=True))
    op.add_column('tco_results', sa.Column('exchange_rate_type', sa.String(length=20), nullable=True))


def downgrade() -> None:
    # 1. Drop FX fields from tco_results
    op.drop_column('tco_results', 'exchange_rate_type')
    op.drop_column('tco_results', 'exchange_rate_source')
    op.drop_column('tco_results', 'exchange_rate_date')
    op.drop_column('tco_results', 'exchange_rate')
    op.drop_column('tco_results', 'target_currency')
    op.drop_column('tco_results', 'converted_total_tco')

    # 2. Drop exchange_rates table and indexes
    op.drop_index('ix_exchange_rates_lookup', table_name='exchange_rates')
    op.drop_index('ix_exchange_rates_rate_date', table_name='exchange_rates')
    op.drop_index('ix_exchange_rates_target_currency', table_name='exchange_rates')
    op.drop_index('ix_exchange_rates_source_currency', table_name='exchange_rates')
    op.drop_table('exchange_rates')
