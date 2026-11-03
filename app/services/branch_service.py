# app/services/branch_service.py
"""Branch, department and membership business logic."""
import logging
import re
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.branch import (
    Branch, Department, BranchMembership, BRANCH_ROLES, BRANCH_ROLE_RANK,
)
from app.models.category import Category
from app.models.items import Items
from app.models.sales import Sales
from app.models.expenses import Expenses
from app.models.stock_history import StockHistory
from app.models.rbac import Role
from app.models.user import User

logger = logging.getLogger(__name__)

DEFAULT_BRANCH_NAME = "Main Branch"
DEFAULT_BRANCH_CODE = "HQ"
DEFAULT_DEPARTMENT_NAME = "general"


def normalize_code(value: str) -> str:
    code = re.sub(r"[^A-Za-z0-9_-]+", "-", (value or "").strip()).strip("-").upper()
    if not code:
        raise ValueError("Branch code is required")
    return code[:30]


# ─── Defaults (used at signup and as a safety net for legacy orgs) ───────────

def ensure_default_branch(db: Session, organization_id, commit: bool = True) -> Branch:
    """Return the org's default branch, creating 'Main Branch' + 'general' dept if none exists."""
    branch = (
        db.query(Branch)
        .filter(Branch.organization_id == organization_id, Branch.deleted == False)  # noqa: E712
        .order_by(Branch.is_default.desc(), Branch.created_at.asc())
        .first()
    )
    if branch:
        return branch

    branch = Branch(
        organization_id=organization_id,
        name=DEFAULT_BRANCH_NAME,
        code=DEFAULT_BRANCH_CODE,
        is_default=True,
        is_active=True,
    )
    db.add(branch)
    db.flush()
    db.add(Department(
        organization_id=organization_id, branch_id=branch.id, name=DEFAULT_DEPARTMENT_NAME,
    ))
    if commit:
        db.commit()
        db.refresh(branch)
    else:
        db.flush()
    return branch


# ─── Branches ────────────────────────────────────────────────────────────────

def list_branches(db: Session, organization_id, branch_ids: Optional[List] = None,
                  include_inactive: bool = True) -> List[Branch]:
    q = db.query(Branch).filter(Branch.organization_id == organization_id, Branch.deleted == False)  # noqa: E712
    if branch_ids is not None:
        q = q.filter(Branch.id.in_(branch_ids) if branch_ids else False)
    if not include_inactive:
        q = q.filter(Branch.is_active == True)  # noqa: E712
    return q.order_by(Branch.is_default.desc(), Branch.name).all()


def get_branch(db: Session, branch_id, organization_id) -> Optional[Branch]:
    return db.query(Branch).filter(
        Branch.id == branch_id, Branch.organization_id == organization_id, Branch.deleted == False  # noqa: E712
    ).first()


def create_branch(db: Session, organization_id, name: str, code: Optional[str] = None,
                  address: str = None, phone: str = None, description: str = None,
                  departments: Optional[List[str]] = None) -> Branch:
    name = (name or "").strip()
    if not name:
        raise ValueError("Branch name is required")
    code = normalize_code(code or name[:6])

    if db.query(Branch).filter(
        Branch.organization_id == organization_id, Branch.code == code, Branch.deleted == False  # noqa: E712
    ).first():
        raise ValueError(f"A branch with code '{code}' already exists.")
    if db.query(Branch).filter(
        Branch.organization_id == organization_id, Branch.name.ilike(name), Branch.deleted == False  # noqa: E712
    ).first():
        raise ValueError(f"A branch named '{name}' already exists.")

    branch = Branch(
        organization_id=organization_id, name=name, code=code,
        address=address, phone=phone, description=description,
    )
    db.add(branch)
    db.flush()
    names = [d.strip() for d in (departments or []) if d and d.strip()] or [DEFAULT_DEPARTMENT_NAME]
    seen = set()
    for dn in names:
        if dn.lower() in seen:
            continue
        seen.add(dn.lower())
        db.add(Department(organization_id=organization_id, branch_id=branch.id, name=dn))
    db.commit()
    db.refresh(branch)
    return branch


def update_branch(db: Session, branch: Branch, data: dict) -> Branch:
    if "name" in data and data["name"] is not None:
        name = data["name"].strip()
        if not name:
            raise ValueError("Branch name cannot be empty")
        clash = db.query(Branch).filter(
            Branch.organization_id == branch.organization_id, Branch.name.ilike(name),
            Branch.id != branch.id, Branch.deleted == False,  # noqa: E712
        ).first()
        if clash:
            raise ValueError(f"A branch named '{name}' already exists.")
        branch.name = name
    if "code" in data and data["code"] is not None:
        code = normalize_code(data["code"])
        clash = db.query(Branch).filter(
            Branch.organization_id == branch.organization_id, Branch.code == code,
            Branch.id != branch.id, Branch.deleted == False,  # noqa: E712
        ).first()
        if clash:
            raise ValueError(f"A branch with code '{code}' already exists.")
        branch.code = code
    for f in ("address", "phone", "description"):
        if f in data:
            setattr(branch, f, data[f])
    if "is_active" in data and data["is_active"] is not None:
        if data["is_active"] is False and branch.is_default:
            raise ValueError("The default branch cannot be deactivated.")
        branch.is_active = data["is_active"]
    db.commit()
    db.refresh(branch)
    return branch


def branch_has_data(db: Session, branch_id) -> bool:
    for model in (Items, Category, Sales, Expenses, StockHistory):
        if db.query(model.id).filter(model.branch_id == branch_id, model.deleted == False).first():  # noqa: E712
            return True
    return False


def delete_branch(db: Session, branch: Branch) -> None:
    if branch.is_default:
        raise ValueError("The default branch cannot be deleted.")
    if branch_has_data(db, branch.id):
        raise ValueError("This branch has products, sales or expenses. Deactivate it instead of deleting.")
    branch.deleted = True
    branch.is_active = False
    db.query(BranchMembership).filter(BranchMembership.branch_id == branch.id).delete()
    db.commit()


# ─── Departments ─────────────────────────────────────────────────────────────

def list_departments(db: Session, organization_id, branch_id=None, branch_ids: Optional[List] = None) -> List[Department]:
    q = db.query(Department).filter(
        Department.organization_id == organization_id, Department.deleted == False  # noqa: E712
    )
    if branch_id:
        q = q.filter(Department.branch_id == branch_id)
    if branch_ids is not None:
        q = q.filter(Department.branch_id.in_(branch_ids) if branch_ids else False)
    return q.order_by(Department.name).all()


def get_department(db: Session, department_id, organization_id) -> Optional[Department]:
    return db.query(Department).filter(
        Department.id == department_id, Department.organization_id == organization_id,
        Department.deleted == False,  # noqa: E712
    ).first()


def create_department(db: Session, organization_id, branch_id, name: str, description: str = None) -> Department:
    name = (name or "").strip()
    if not name:
        raise ValueError("Department name is required")
    if db.query(Department).filter(
        Department.branch_id == branch_id, Department.name.ilike(name), Department.deleted == False  # noqa: E712
    ).first():
        raise ValueError(f"Department '{name}' already exists in this branch.")
    dept = Department(organization_id=organization_id, branch_id=branch_id, name=name, description=description)
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept


def _sync_dept_label(db: Session, dept: Department) -> None:
    """Keep the legacy free-text `dept` label on child rows in step with the department name."""
    for model in (Items, Category, Sales, Expenses):
        db.query(model).filter(model.department_id == dept.id).update(
            {model.dept: dept.name}, synchronize_session=False
        )


def update_department(db: Session, dept: Department, data: dict) -> Department:
    if "name" in data and data["name"] is not None:
        name = data["name"].strip()
        if not name:
            raise ValueError("Department name cannot be empty")
        clash = db.query(Department).filter(
            Department.branch_id == dept.branch_id, Department.name.ilike(name),
            Department.id != dept.id, Department.deleted == False,  # noqa: E712
        ).first()
        if clash:
            raise ValueError(f"Department '{name}' already exists in this branch.")
        if name != dept.name:
            dept.name = name
            _sync_dept_label(db, dept)
    if "description" in data:
        dept.description = data["description"]
    if "is_active" in data and data["is_active"] is not None:
        dept.is_active = data["is_active"]
    db.commit()
    db.refresh(dept)
    return dept


def delete_department(db: Session, dept: Department) -> None:
    for model in (Items, Category, Sales, Expenses):
        if db.query(model.id).filter(model.department_id == dept.id, model.deleted == False).first():  # noqa: E712
            raise ValueError("This department has records. Deactivate it instead of deleting.")
    dept.deleted = True
    dept.is_active = False
    db.query(BranchMembership).filter(BranchMembership.department_id == dept.id).delete()
    db.commit()


# ─── Memberships ─────────────────────────────────────────────────────────────

def list_members(db: Session, branch_id, organization_id) -> List[BranchMembership]:
    return (
        db.query(BranchMembership)
        .filter(BranchMembership.branch_id == branch_id, BranchMembership.organization_id == organization_id)
        .order_by(BranchMembership.role, BranchMembership.created_at)
        .all()
    )


def user_memberships(db: Session, user_id, organization_id) -> List[BranchMembership]:
    return db.query(BranchMembership).filter(
        BranchMembership.user_id == user_id, BranchMembership.organization_id == organization_id
    ).all()


def assign_member(db: Session, organization_id, user: User, branch: Branch, role: str,
                  department_id=None, assigned_by=None) -> BranchMembership:
    """Create or update a user's membership in a branch (idempotent per user/branch/department)."""
    if role not in BRANCH_ROLES:
        raise ValueError(f"Role must be one of: {', '.join(BRANCH_ROLES)}")
    if user.organization_id != organization_id:
        raise ValueError("User does not belong to this organization.")
    if department_id is not None:
        dept = get_department(db, department_id, organization_id)
        if not dept or dept.branch_id != branch.id:
            raise ValueError("Department does not belong to this branch.")
        if role == "admin":
            raise ValueError("Branch admins manage the whole branch; clear the department.")

    # A manager/admin membership needs the matching global capability so the
    # existing role-gated endpoints let them through (scope then limits them).
    if role in ("admin", "manager") and not user.has_role("admin", "super_admin", "manager"):
        manager_role = db.query(Role).filter(Role.name == "manager").first()
        if not manager_role:
            raise ValueError("The 'manager' role does not exist yet. Create it before assigning managers.")
        user.roles.append(manager_role)

    existing = db.query(BranchMembership).filter(
        BranchMembership.user_id == user.id,
        BranchMembership.branch_id == branch.id,
        BranchMembership.department_id == department_id if department_id else BranchMembership.department_id.is_(None),
    ).first()
    if existing:
        existing.role = role
        existing.assigned_by = assigned_by
        member = existing
    else:
        member = BranchMembership(
            organization_id=organization_id, user_id=user.id, branch_id=branch.id,
            department_id=department_id, role=role, assigned_by=assigned_by,
        )
        db.add(member)
    db.commit()
    db.refresh(member)
    return member


def remove_member(db: Session, membership: BranchMembership) -> None:
    db.delete(membership)
    db.commit()
