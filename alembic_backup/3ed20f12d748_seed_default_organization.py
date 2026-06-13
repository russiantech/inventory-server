"""seed default organization

Revision ID: 3ed20f12d748
Revises: c083b0f34a78
Create Date: 2026-06-11 12:14:02.117499

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3ed20f12d748'
down_revision: Union[str, None] = 'c083b0f34a78'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
