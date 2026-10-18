"""add_po_approval_steps_table

Revision ID: 9b4a1c2e3f5d
Revises: 2ac55145c03b
Create Date: 2026-10-18 19:15:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b4a1c2e3f5d'
down_revision: Union[str, None] = '2ac55145c03b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply migration: add po_approval_steps table and widen users.role column."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    # Widen users.role to 50 chars for purchasing_director / cfo roles
    columns = [col['name'] for col in inspector.get_columns('users')]
    if 'role' in columns:
        op.alter_column(
            'users',
            'role',
            type_=sa.String(length=50),
            existing_type=sa.String(length=20),
            existing_nullable=False,
        )

    if 'po_approval_steps' not in tables:
        op.create_table(
            'po_approval_steps',
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('organization_id', sa.UUID(), nullable=False),
            sa.Column('purchase_order_id', sa.UUID(), nullable=False),
            sa.Column('role', sa.String(length=50), nullable=False),
            sa.Column('status', sa.String(length=20), server_default='pending', nullable=False),
            sa.Column('approver_id', sa.UUID(), nullable=True),
            sa.Column('decision_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('comment', sa.Text(), nullable=True),
            sa.Column('rejection_reason', sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['purchase_order_id'], ['purchase_orders.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['approver_id'], ['users.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('purchase_order_id', 'role', name='uq_po_approval_step_po_role'),
        )
        op.create_index('ix_po_approval_steps_organization_id', 'po_approval_steps', ['organization_id'])
        op.create_index('ix_po_approval_steps_purchase_order_id', 'po_approval_steps', ['purchase_order_id'])
        op.create_index('ix_po_approval_steps_role', 'po_approval_steps', ['role'])
        op.create_index('ix_po_approval_steps_status', 'po_approval_steps', ['status'])
        op.create_index('ix_po_approval_steps_approver_id', 'po_approval_steps', ['approver_id'])


def downgrade() -> None:
    """Revert migration: drop po_approval_steps table and narrow users.role."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if 'po_approval_steps' in tables:
        op.drop_index('ix_po_approval_steps_approver_id', table_name='po_approval_steps')
        op.drop_index('ix_po_approval_steps_status', table_name='po_approval_steps')
        op.drop_index('ix_po_approval_steps_role', table_name='po_approval_steps')
        op.drop_index('ix_po_approval_steps_purchase_order_id', table_name='po_approval_steps')
        op.drop_index('ix_po_approval_steps_organization_id', table_name='po_approval_steps')
        op.drop_table('po_approval_steps')

    columns = [col['name'] for col in inspector.get_columns('users')]
    if 'role' in columns:
        op.alter_column(
            'users',
            'role',
            type_=sa.String(length=20),
            existing_type=sa.String(length=50),
            existing_nullable=False,
        )
