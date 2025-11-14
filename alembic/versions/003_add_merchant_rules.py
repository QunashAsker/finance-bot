"""Add merchant_rules table

Revision ID: 003
Revises: 002
Create Date: 2025-11-14 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    """Создать таблицу merchant_rules для автокатегоризации."""
    op.create_table(
        'merchant_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('merchant_name', sa.String(length=255), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=False),
        sa.Column('default_description', sa.Text(), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_merchant_rules_id'), 'merchant_rules', ['id'], unique=False)
    op.create_index(op.f('ix_merchant_rules_merchant_name'), 'merchant_rules', ['merchant_name'], unique=False)


def downgrade():
    """Удалить таблицу merchant_rules."""
    op.drop_index(op.f('ix_merchant_rules_merchant_name'), table_name='merchant_rules')
    op.drop_index(op.f('ix_merchant_rules_id'), table_name='merchant_rules')
    op.drop_table('merchant_rules')

