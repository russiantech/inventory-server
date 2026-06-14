"""add_pending_expired_to_subscriptionstatus_enum

Revision ID: a1b2c3d4e5f6
Revises: <replace_with_your_current_head_revision>
Create Date: 2026-06-14

Adds 'pending' and 'expired' to the subscriptionstatus PostgreSQL enum.

PostgreSQL does not support removing enum values, so downgrade is a no-op.
Both values use IF NOT EXISTS so this migration is safe to re-run and
idempotent across local and production.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '6bf1f119a5a0'  # ← REPLACE with your current head: run `alembic heads`
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Alembic wraps migrations in a transaction by default, but PostgreSQL
    # does NOT allow ALTER TYPE ... ADD VALUE inside a transaction block.
    # We must execute outside the implicit transaction using COMMIT first.
    op.execute("COMMIT")
    op.execute("ALTER TYPE subscriptionstatus ADD VALUE IF NOT EXISTS 'pending'")
    op.execute("ALTER TYPE subscriptionstatus ADD VALUE IF NOT EXISTS 'expired'")


def downgrade() -> None:
    # PostgreSQL has no DROP VALUE for enums — this is intentional and safe.
    # The values simply go unused if you roll back application code.
    pass