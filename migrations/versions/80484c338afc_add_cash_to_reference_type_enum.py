"""add CASH to reference_type_enum

Revision ID: 80484c338afc
Revises: bd66b7c9fd4a
Create Date: 2026-02-15 22:56:39.502694

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '80484c338afc'
down_revision: Union[str, Sequence[str], None] = 'bd66b7c9fd4a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Manual SQL to add CASH to reference_type_enum
    # Note: ADD VALUE cannot be executed in a transaction block in some Postgres versions
    # However, newer versions (9.1+) allow it, but not within a transaction that has already accessed the enum.
    # Alembic usually runs migrations in a transaction.
    # We use execute() which might work depending on the environment.
    op.execute("ALTER TYPE reference_type_enum ADD VALUE 'CASH'")


def downgrade() -> None:
    # PostgreSQL does not support removing values from an enum type easily.
    # Usually requires recreating the type and updating all columns.
    pass
