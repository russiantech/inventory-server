"""add branches, departments and branch memberships; scope inventory data by branch

Revision ID: 20261031_branches
Revises: <PUT YOUR CURRENT HEAD HERE>   # run `alembic heads`
Create Date: 2026-10-31

Backfill (so nothing existing breaks):
  * every organization gets a default branch  "Main Branch" (code HQ)
  * every distinct legacy free-text `dept` becomes a Department of that branch
  * all existing categories / items / stock / sales / expenses are attached to
    that branch (+ matching department)
  * every non-admin user is assigned to the default branch (manager -> manager, else staff)
Org owners / admins need no assignment: they are org-wide.

Columns stay NULLABLE on purpose: old app instances keep working during a rolling
deploy. Once every instance runs the new code you may tighten them (see README).
Requires PostgreSQL 13+ (gen_random_uuid()).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision = "20261031_branches"
revision = "20261031_branches"
down_revision = "a22ffebc3678"
branch_labels = None
depends_on = None

SCOPED_TABLES = ["categories", "items", "stock_history", "sales", "expenses"]
DEPT_SOURCES = ["items", "categories", "sales", "expenses"]  # tables that carry a legacy `dept` label

UUID = postgresql.UUID(as_uuid=True)


def _ts():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = set(insp.get_table_names())

    if "branches" not in existing:
        op.create_table(
            "branches",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("code", sa.String(30), nullable=False),
            sa.Column("address", sa.String(255)),
            sa.Column("phone", sa.String(30)),
            sa.Column("description", sa.Text),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
            sa.Column("is_default", sa.Boolean, nullable=False, server_default=sa.text("false")),
            sa.Column("deleted", sa.Boolean, nullable=False, server_default=sa.text("false")),
            *_ts(),
            sa.UniqueConstraint("organization_id", "code", name="uq_branch_org_code"),
        )
        op.create_index("ix_branches_organization_id", "branches", ["organization_id"])

    if "departments" not in existing:
        op.create_table(
            "departments",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("branch_id", UUID, sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(80), nullable=False),
            sa.Column("description", sa.Text),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
            sa.Column("deleted", sa.Boolean, nullable=False, server_default=sa.text("false")),
            *_ts(),
            sa.UniqueConstraint("branch_id", "name", name="uq_department_branch_name"),
        )
        op.create_index("ix_departments_organization_id", "departments", ["organization_id"])
        op.create_index("ix_departments_branch_id", "departments", ["branch_id"])

    if "branch_memberships" not in existing:
        op.create_table(
            "branch_memberships",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("branch_id", UUID, sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
            sa.Column("department_id", UUID, sa.ForeignKey("departments.id", ondelete="CASCADE")),
            sa.Column("role", sa.String(20), nullable=False, server_default="staff"),
            sa.Column("assigned_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
            *_ts(),
            sa.UniqueConstraint("user_id", "branch_id", "department_id", name="uq_membership_user_branch_dept"),
        )
        for col in ("organization_id", "user_id", "branch_id", "department_id"):
            op.create_index(f"ix_branch_memberships_{col}", "branch_memberships", [col])
        op.create_index("ix_membership_user_branch", "branch_memberships", ["user_id", "branch_id"])

    # ── scope columns on existing tables ────────────────────────────────────
    for table in SCOPED_TABLES:
        cols = {c["name"] for c in sa.inspect(bind).get_columns(table)}
        if "branch_id" not in cols:
            op.add_column(table, sa.Column("branch_id", UUID, sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=True))
            op.create_index(f"ix_{table}_branch_id", table, ["branch_id"])
        if "department_id" not in cols:
            op.add_column(table, sa.Column("department_id", UUID, sa.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True))
            op.create_index(f"ix_{table}_department_id", table, ["department_id"])

    # ── backfill ────────────────────────────────────────────────────────────
    orgs = bind.execute(sa.text("SELECT id FROM organizations")).fetchall()
    for (org_id,) in orgs:
        branch_id = bind.execute(
            sa.text("SELECT id FROM branches WHERE organization_id=:o AND deleted=false ORDER BY is_default DESC, created_at LIMIT 1"),
            {"o": org_id},
        ).scalar()
        if not branch_id:
            branch_id = bind.execute(
                sa.text(
                    "INSERT INTO branches (id, organization_id, name, code, is_default, is_active, deleted) "
                    "VALUES (gen_random_uuid(), :o, 'Main Branch', 'HQ', true, true, false) RETURNING id"
                ),
                {"o": org_id},
            ).scalar()

        union = " UNION ".join(
            f"SELECT btrim(dept) AS d FROM {t} WHERE organization_id=:o AND dept IS NOT NULL" for t in DEPT_SOURCES
        )
        bind.execute(
            sa.text(
                "INSERT INTO departments (id, organization_id, branch_id, name, is_active, deleted) "
                f"SELECT gen_random_uuid(), :o, :b, x.d, true, false FROM ({union} UNION SELECT 'general') x "
                "WHERE x.d <> '' AND NOT EXISTS (SELECT 1 FROM departments dd WHERE dd.branch_id=:b AND dd.name=x.d)"
            ),
            {"o": org_id, "b": branch_id},
        )

        for table in SCOPED_TABLES:
            if table in DEPT_SOURCES:
                bind.execute(
                    sa.text(
                        f"UPDATE {table} t SET branch_id=:b, department_id=d.id FROM departments d "
                        "WHERE t.organization_id=:o AND t.branch_id IS NULL AND d.branch_id=:b AND d.name=btrim(t.dept)"
                    ),
                    {"o": org_id, "b": branch_id},
                )
            bind.execute(
                sa.text(f"UPDATE {table} SET branch_id=:b WHERE organization_id=:o AND branch_id IS NULL"),
                {"o": org_id, "b": branch_id},
            )

        # stock_history has no dept label: inherit from its item
        bind.execute(
            sa.text(
                "UPDATE stock_history s SET department_id=i.department_id FROM items i "
                "WHERE s.item_id=i.id AND s.organization_id=:o AND s.department_id IS NULL AND i.department_id IS NOT NULL"
            ),
            {"o": org_id},
        )

        # non-admin users -> default branch
        bind.execute(
            sa.text(
                "INSERT INTO branch_memberships (id, organization_id, user_id, branch_id, role) "
                "SELECT gen_random_uuid(), :o, u.id, :b, "
                "  CASE WHEN EXISTS (SELECT 1 FROM user_roles ur JOIN roles r ON r.id=ur.role_id "
                "                    WHERE ur.user_id=u.id AND r.name='manager') THEN 'manager' ELSE 'staff' END "
                "FROM users u WHERE u.organization_id=:o AND u.deleted=false AND u.is_org_admin=false "
                "AND NOT EXISTS (SELECT 1 FROM user_roles ur JOIN roles r ON r.id=ur.role_id "
                "                WHERE ur.user_id=u.id AND r.name IN ('admin','super_admin')) "
                "AND NOT EXISTS (SELECT 1 FROM branch_memberships m WHERE m.user_id=u.id AND m.branch_id=:b)"
            ),
            {"o": org_id, "b": branch_id},
        )


def downgrade() -> None:
    for table in SCOPED_TABLES:
        op.drop_index(f"ix_{table}_department_id", table_name=table)
        op.drop_column(table, "department_id")
        op.drop_index(f"ix_{table}_branch_id", table_name=table)
        op.drop_column(table, "branch_id")
    op.drop_table("branch_memberships")
    op.drop_table("departments")
    op.drop_table("branches")
