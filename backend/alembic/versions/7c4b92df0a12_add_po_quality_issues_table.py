"""add po_quality_issues table

Revision ID: 7c4b92df0a12
Revises: 6a2b411ec3eb
Create Date: 2026-10-16 10:50:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c4b92df0a12'
down_revision: Union[str, None] = '6a2b411ec3eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply migration: add po_quality_issues table with indices and foreign keys."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if 'po_quality_issues' not in tables:
        op.create_table(
            'po_quality_issues',
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('organization_id', sa.UUID(), nullable=False),
            sa.Column('purchase_order_id', sa.UUID(), nullable=False),
            sa.Column('supplier_id', sa.UUID(), nullable=False),
            sa.Column('reported_by_id', sa.UUID(), nullable=True),
            sa.Column('issue_type', sa.String(length=50), nullable=False),
            sa.Column('severity', sa.String(length=20), nullable=False),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('rejection_count', sa.Integer(), server_default='0', nullable=False),
            sa.Column('status', sa.String(length=20), server_default='open', nullable=False),
            sa.Column('resolution_notes', sa.Text(), nullable=True),
            sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['purchase_order_id'], ['purchase_orders.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['reported_by_id'], ['users.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_po_quality_issues_organization_id'), 'po_quality_issues', ['organization_id'], unique=False)
        op.create_index(op.f('ix_po_quality_issues_purchase_order_id'), 'po_quality_issues', ['purchase_order_id'], unique=False)
        op.create_index(op.f('ix_po_quality_issues_supplier_id'), 'po_quality_issues', ['supplier_id'], unique=False)
        op.create_index(op.f('ix_po_quality_issues_reported_by_id'), 'po_quality_issues', ['reported_by_id'], unique=False)
        op.create_index(op.f('ix_po_quality_issues_status'), 'po_quality_issues', ['status'], unique=False)
    else:
        # Check and add columns if upgrading a database where the table was previously created
        cols = [c['name'] for c in inspector.get_columns('po_quality_issues')]
        if 'status' not in cols:
            op.add_column('po_quality_issues', sa.Column('status', sa.String(length=20), server_default='open', nullable=False))
            op.create_index(op.f('ix_po_quality_issues_status'), 'po_quality_issues', ['status'], unique=False)
        if 'resolution_notes' not in cols:
            op.add_column('po_quality_issues', sa.Column('resolution_notes', sa.Text(), nullable=True))
        if 'resolved_at' not in cols:
            op.add_column('po_quality_issues', sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Revert migration: drop po_quality_issues table and indices."""
    op.drop_index(op.f('ix_po_quality_issues_status'), table_name='po_quality_issues')
    op.drop_index(op.f('ix_po_quality_issues_reported_by_id'), table_name='po_quality_issues')
    op.drop_index(op.f('ix_po_quality_issues_supplier_id'), table_name='po_quality_issues')
    op.drop_index(op.f('ix_po_quality_issues_purchase_order_id'), table_name='po_quality_issues')
    op.drop_index(op.f('ix_po_quality_issues_organization_id'), table_name='po_quality_issues')
    op.drop_table('po_quality_issues')
