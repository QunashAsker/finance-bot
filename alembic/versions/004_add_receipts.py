"""Add receipts table

Revision ID: 004
Revises: 003
Create Date: 2025-11-14 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade():
    """Создать таблицу receipts для чеков."""
    op.create_table(
        'receipts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('transaction_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('store_name', sa.String(length=255), nullable=True),
        sa.Column('receipt_date', sa.DateTime(), nullable=True),
        sa.Column('total_amount', sa.Float(), nullable=False),
        sa.Column('vat_amount', sa.Float(), nullable=True),
        sa.Column('receipt_number', sa.String(length=100), nullable=True),
        sa.Column('image_data', sa.Text(), nullable=True),
        sa.Column('items', sa.JSON(), nullable=True),
        sa.Column('raw_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_receipts_id'), 'receipts', ['id'], unique=False)


def downgrade():
    """Удалить таблицу receipts."""
    op.drop_index(op.f('ix_receipts_id'), table_name='receipts')
    op.drop_table('receipts')

