"""relax check_tenure_positive constraint

Revision ID: 43cb57202658
Revises: 95f843c84ff7
Create Date: 2026-02-14 21:50:03.951881

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "43cb57202658"
down_revision: Union[str, Sequence[str], None] = "95f843c84ff7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop the constraint requiring tenure_months > 0
    op.drop_constraint("check_tenure_positive", "loans", type_="check")
    # Add new constraint allowing tenure_months >= 0 (0 for foreclosed loans)
    op.create_check_constraint("check_tenure_valid", "loans", "tenure_months >= 0")


def downgrade() -> None:
    """Downgrade schema."""
    # Revert changes
    op.drop_constraint("check_tenure_valid", "loans", type_="check")
    # Note: This might fail if there are loans with tenure_months=0
    # Add back the strict positive constraint
    op.create_check_constraint("check_tenure_positive", "loans", "tenure_months > 0")
