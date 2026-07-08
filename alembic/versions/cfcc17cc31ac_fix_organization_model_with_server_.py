"""fix organization model with server defaults

Revision ID: cfcc17cc31ac
Revises: 5ab5d72db8a2
Create Date: 2026-07-08 16:32:11.867627

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'cfcc17cc31ac'
down_revision: Union[str, None] = '5ab5d72db8a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Step 1: Set defaults for existing NULL rows BEFORE adding NOT NULL ──
    op.execute("UPDATE organizations SET plan = 'free' WHERE plan IS NULL")
    op.execute("UPDATE organizations SET max_users = 5 WHERE max_users IS NULL")
    op.execute("UPDATE organizations SET max_products = 100 WHERE max_products IS NULL")
    op.execute("UPDATE organizations SET allow_public_signup = false WHERE allow_public_signup IS NULL")
    op.execute("UPDATE organizations SET is_active = true WHERE is_active IS NULL")
    op.execute("UPDATE organizations SET is_paused = false WHERE is_paused IS NULL")
    op.execute("UPDATE organizations SET subscription_status = 'trialing' WHERE subscription_status IS NULL")

    # ── Step 2: Alter columns to NOT NULL ──
    op.alter_column('organizations', 'plan',
               existing_type=sa.VARCHAR(length=20),
               nullable=False)
    op.alter_column('organizations', 'max_users',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.alter_column('organizations', 'max_products',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.alter_column('organizations', 'allow_public_signup',
               existing_type=sa.BOOLEAN(),
               nullable=False)
    op.alter_column('organizations', 'is_active',
               existing_type=sa.BOOLEAN(),
               nullable=False)
    op.alter_column('organizations', 'is_paused',
               existing_type=sa.BOOLEAN(),
               nullable=False)
    op.alter_column('organizations', 'subscription_status',
               existing_type=sa.VARCHAR(length=20),
               nullable=False)

    # ── Step 3: Fix subscription_ends_at type ──
    op.alter_column('organizations', 'subscription_ends_at',
               existing_type=postgresql.TIMESTAMP(),
               type_=sa.DateTime(timezone=True),
               existing_nullable=True)

    # ── Step 4: Fix owner_id FK with use_alter to break circular dependency ──
    op.create_index(op.f('ix_organizations_owner_id'), 'organizations', ['owner_id'], unique=False)
    
    # Drop old FK only if it exists (idempotent)
    op.execute("""
        ALTER TABLE organizations 
        DROP CONSTRAINT IF EXISTS organizations_owner_id_fkey
    """)
    
    op.create_foreign_key(
        'fk_organization_owner',
        'organizations', 'users',
        ['owner_id'], ['id'],
        ondelete='SET NULL',
        use_alter=True
    )


def downgrade() -> None:
    # ── Reverse FK changes ──
    op.drop_constraint('fk_organization_owner', 'organizations', type_='foreignkey')
    
    op.create_foreign_key(
        'organizations_owner_id_fkey',
        'organizations', 'users',
        ['owner_id'], ['id']
    )
    
    op.drop_index(op.f('ix_organizations_owner_id'), table_name='organizations')

    # ── Reverse type change ──
    op.alter_column('organizations', 'subscription_ends_at',
               existing_type=sa.DateTime(timezone=True),
               type_=postgresql.TIMESTAMP(),
               existing_nullable=True)

    # ── Reverse NOT NULL constraints ──
    op.alter_column('organizations', 'subscription_status',
               existing_type=sa.VARCHAR(length=20),
               nullable=True)
    op.alter_column('organizations', 'is_paused',
               existing_type=sa.BOOLEAN(),
               nullable=True)
    op.alter_column('organizations', 'is_active',
               existing_type=sa.BOOLEAN(),
               nullable=True)
    op.alter_column('organizations', 'allow_public_signup',
               existing_type=sa.BOOLEAN(),
               nullable=True)
    op.alter_column('organizations', 'max_products',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.alter_column('organizations', 'max_users',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.alter_column('organizations', 'plan',
               existing_type=sa.VARCHAR(length=20),
               nullable=True)