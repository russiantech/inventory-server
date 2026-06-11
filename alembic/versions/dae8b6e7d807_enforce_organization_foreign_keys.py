"""enforce organization foreign keys

Revision ID: dae8b6e7d807
Revises: 3ed20f12d748
Create Date: 2026-06-11 12:14:05.921582

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dae8b6e7d807'
down_revision: Union[str, None] = '3ed20f12d748'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
