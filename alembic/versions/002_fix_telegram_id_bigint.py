"""Fix telegram_id to BigInteger

Revision ID: 002
Revises: 001
Create Date: 2024-11-13

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Изменяем тип telegram_id с Integer на BigInteger
    op.alter_column('users', 'telegram_id',
                    type_=sa.BigInteger(),
                    existing_type=sa.Integer(),
                    existing_nullable=False)


def downgrade() -> None:
    # Откат обратно к Integer (может вызвать ошибку если есть большие значения)
    op.alter_column('users', 'telegram_id',
                    type_=sa.Integer(),
                    existing_type=sa.BigInteger(),
                    existing_nullable=False)

