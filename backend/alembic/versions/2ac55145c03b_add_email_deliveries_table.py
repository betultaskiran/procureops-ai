"""add_email_deliveries_table

Revision ID: 2ac55145c03b
Revises: 7c4b92df0a12
Create Date: 2026-10-17 11:18:15.392679
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2ac55145c03b'
down_revision: Union[str, None] = '7c4b92df0a12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply migration: add email_deliveries table with indices and unique idempotency constraint."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if 'email_deliveries' not in tables:
        op.create_table(
            'email_deliveries',
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('organization_id', sa.UUID(), nullable=False),
            sa.Column('rfq_id', sa.UUID(), nullable=True),
            sa.Column('supplier_id', sa.UUID(), nullable=True),
            sa.Column('purchase_order_id', sa.UUID(), nullable=True),
            sa.Column('recipient_email', sa.String(length=320), nullable=False),
            sa.Column('recipient_name', sa.String(length=200), nullable=True),
            sa.Column('subject', sa.String(length=500), nullable=False),
            sa.Column('message_type', sa.String(length=50), server_default='rfq_invitation', nullable=False),
            sa.Column('idempotency_key', sa.String(length=255), nullable=False),
            sa.Column('status', sa.String(length=30), server_default='queued', nullable=False),
            sa.Column('attempt_count', sa.Integer(), server_default='0', nullable=False),
            sa.Column('max_attempts', sa.Integer(), server_default='3', nullable=False),
            sa.Column('last_error', sa.Text(), nullable=True),
            sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('provider_message_id', sa.String(length=255), nullable=True),
            sa.Column('queued_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('metadata_json', sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['rfq_id'], ['rfqs.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['purchase_order_id'], ['purchase_orders.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_email_deliveries_organization_id'), 'email_deliveries', ['organization_id'], unique=False)
        op.create_index(op.f('ix_email_deliveries_rfq_id'), 'email_deliveries', ['rfq_id'], unique=False)
        op.create_index(op.f('ix_email_deliveries_supplier_id'), 'email_deliveries', ['supplier_id'], unique=False)
        op.create_index(op.f('ix_email_deliveries_purchase_order_id'), 'email_deliveries', ['purchase_order_id'], unique=False)
        op.create_index(op.f('ix_email_deliveries_recipient_email'), 'email_deliveries', ['recipient_email'], unique=False)
        op.create_index(op.f('ix_email_deliveries_message_type'), 'email_deliveries', ['message_type'], unique=False)
        op.create_index(op.f('ix_email_deliveries_idempotency_key'), 'email_deliveries', ['idempotency_key'], unique=True)
        op.create_index(op.f('ix_email_deliveries_status'), 'email_deliveries', ['status'], unique=False)
        op.create_index(op.f('ix_email_deliveries_next_retry_at'), 'email_deliveries', ['next_retry_at'], unique=False)


def downgrade() -> None:
    """Revert migration: drop email_deliveries table and indices."""
    op.drop_index(op.f('ix_email_deliveries_next_retry_at'), table_name='email_deliveries')
    op.drop_index(op.f('ix_email_deliveries_status'), table_name='email_deliveries')
    op.drop_index(op.f('ix_email_deliveries_idempotency_key'), table_name='email_deliveries')
    op.drop_index(op.f('ix_email_deliveries_message_type'), table_name='email_deliveries')
    op.drop_index(op.f('ix_email_deliveries_recipient_email'), table_name='email_deliveries')
    op.drop_index(op.f('ix_email_deliveries_purchase_order_id'), table_name='email_deliveries')
    op.drop_index(op.f('ix_email_deliveries_supplier_id'), table_name='email_deliveries')
    op.drop_index(op.f('ix_email_deliveries_rfq_id'), table_name='email_deliveries')
    op.drop_index(op.f('ix_email_deliveries_organization_id'), table_name='email_deliveries')
    op.drop_table('email_deliveries')
