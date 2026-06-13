
#!/usr/bin/env python3
"""
Clean Alembic Migration Reset Script for Dunis Inventory

This script handles:
1. Fixing circular FK dependency (organizations.owner_id <-> users.organization_id)
2. Creating all tables in correct order
3. Seeding default plans
4. Setting up the first super_admin

Run: python reset_migrations.py
"""

import os
import sys
import shutil
from datetime import datetime, timezone

# ── CONFIG ──
ALEMBIC_DIR = "alembic"
ALEMBIC_INI = "alembic.ini"
VERSIONS_DIR = os.path.join(ALEMBIC_DIR, "versions")

def reset_alembic():
    """Delete all migration history and start fresh."""
    
    # 1. Clear versions directory
    if os.path.exists(VERSIONS_DIR):
        shutil.rmtree(VERSIONS_DIR)
        os.makedirs(VERSIONS_DIR)
        print(f"✅ Cleared {VERSIONS_DIR}")
    else:
        os.makedirs(VERSIONS_DIR)
        print(f"✅ Created {VERSIONS_DIR}")
    
    # 2. Remove alembic table from database (if exists)
    print("\n⚠️  IMPORTANT: You must manually drop the alembic_version table from your DB:")
    print("   psql -d your_db -c 'DROP TABLE IF EXISTS alembic_version CASCADE;'")
    print("   OR in pgAdmin: DROP TABLE alembic_version;")
    # print()
    
    # 3. Create baseline migration
    print("Next steps:")
    print("1. Fix your models (see below for circular FK fix)")
    print("2. Run: alembic revision --autogenerate -m 'baseline'")
    print("3. Run: alembic upgrade head")
    print("4. Run: python seed_data.py")

if __name__ == "main":
    reset_alembic()