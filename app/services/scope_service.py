# app/services/scope_service.py
"""
Branch / department access scoping.

Two small building blocks used everywhere data is read or written:

* ``AccessScope``  – WHO the caller is within the org hierarchy
                      (org-wide admin vs. branch/department member).
* ``ScopeFilter``  – WHAT rows a given request may touch (the result of
                      combining the caller's access with the optional
                      ?branch_id= / ?department_id= the client asked for).

Rules
-----
* Org-wide users (is_org_admin, role admin / super_admin) may see every branch.
  With no branch requested they get the *collective* view (no filter);
  with ``branch_id`` they get that branch only.
* Everyone else is limited to the branches/departments they are a member of.
  With no branch requested they see the collective view of *their* branches.
* Asking for a branch you cannot access raises ``ScopeError`` (-> HTTP 403).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Tuple

from sqlalchemy import and_, or_, false
from sqlalchemy.orm import Session

from app.models.branch import Branch, Department, BranchMembership, BRANCH_ROLE_RANK


class ScopeError(Exception):
    """Raised when the caller asks for data outside their branch scope."""

    def __init__(self, message: str, status_code: int = 403):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _uuid(value) -> Optional[uuid.UUID]:
    if value in (None, "", "all"):
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise ScopeError("Invalid branch or department id.", 400)


Grant = Tuple[uuid.UUID, Optional[uuid.UUID]]  # (branch_id, department_id | None)


@dataclass
class ScopeFilter:
    """Row filter. ``grants=None`` means 'no branch restriction'."""
    grants: Optional[List[Grant]] = None
    department_id: Optional[uuid.UUID] = None
    branch_id: Optional[uuid.UUID] = None  # explicit single-branch selection (informational)

    def describe(self) -> dict:
        return {
            "branch_id": str(self.branch_id) if self.branch_id else None,
            "department_id": str(self.department_id) if self.department_id else None,
            "collective": self.branch_id is None,
        }


def apply_scope(query, model, scope: Optional[ScopeFilter]):
    """Constrain ``query`` on ``model.branch_id`` / ``model.department_id``."""
    if scope is None:
        return query
    if scope.grants is not None:
        if not scope.grants:
            return query.filter(false())
        conds = []
        for b, d in scope.grants:
            if d is not None:
                conds.append(and_(model.branch_id == b, model.department_id == d))
            else:
                conds.append(model.branch_id == b)
        query = query.filter(or_(*conds))
    if scope.department_id is not None:
        query = query.filter(model.department_id == scope.department_id)
    return query


@dataclass
class AccessScope:
    organization_id: uuid.UUID
    org_wide: bool
    memberships: List[BranchMembership] = field(default_factory=list)

    # ── introspection ───────────────────────────────────────────────────────
    def accessible_branch_ids(self, db: Session) -> List[uuid.UUID]:
        if self.org_wide:
            rows = db.query(Branch.id).filter(
                Branch.organization_id == self.organization_id, Branch.deleted == False  # noqa: E712
            ).all()
            return [r[0] for r in rows]
        return list({m.branch_id for m in self.memberships})

    def _memberships_for(self, branch_id) -> List[BranchMembership]:
        return [m for m in self.memberships if m.branch_id == branch_id]

    def branch_role(self, branch_id) -> Optional[str]:
        """Highest branch-wide role the caller holds in ``branch_id`` (None = no access)."""
        if self.org_wide:
            return "admin"
        ms = self._memberships_for(branch_id)
        if not ms:
            return None
        whole = [m for m in ms if m.department_id is None]
        pool = whole or ms
        return max((m.role for m in pool), key=lambda r: BRANCH_ROLE_RANK.get(r, 0))

    def has_branch_wide_access(self, branch_id) -> bool:
        return self.org_wide or any(m.department_id is None for m in self._memberships_for(branch_id))

    def can_access(self, branch_id, department_id=None) -> bool:
        if branch_id is None:
            return self.org_wide  # legacy rows with no branch: org-wide users only
        if self.org_wide:
            return True
        ms = self._memberships_for(branch_id)
        if not ms:
            return False
        if any(m.department_id is None for m in ms):
            return True
        return department_id is not None and any(m.department_id == department_id for m in ms)

    # ── enforcement ─────────────────────────────────────────────────────────
    def require_access(self, branch_id, department_id=None) -> None:
        if not self.can_access(branch_id, department_id):
            raise ScopeError("You do not have access to this branch or department.")

    def require_role(self, branch_id, minimum: str) -> None:
        """Require at least ``minimum`` ('staff'|'manager'|'admin') in the branch."""
        if self.org_wide:
            return
        role = self.branch_role(branch_id)
        if role is None or BRANCH_ROLE_RANK[role] < BRANCH_ROLE_RANK[minimum]:
            raise ScopeError(f"Branch {minimum} privileges required for this action.")

    def require_org_wide(self, message: str = "Organization admin privileges required.") -> None:
        if not self.org_wide:
            raise ScopeError(message)

    # ── read filter ─────────────────────────────────────────────────────────
    def read_filter(self, db: Session, branch_id=None, department_id=None) -> ScopeFilter:
        b = _uuid(branch_id)
        d = _uuid(department_id)

        if d is not None and b is None:
            dep = db.query(Department).filter(
                Department.id == d, Department.organization_id == self.organization_id
            ).first()
            if not dep:
                raise ScopeError("Department not found.", 404)
            b = dep.branch_id

        if b is not None:
            self._assert_branch_in_org(db, b)
            if d is not None:
                self._assert_department_in_branch(db, d, b)
            if not self.can_access(b, d):
                raise ScopeError("You do not have access to this branch or department.")
            if self.org_wide or self.has_branch_wide_access(b):
                return ScopeFilter(grants=[(b, None)], department_id=d, branch_id=b)
            # department-limited member: restrict to granted departments
            grants = [(b, m.department_id) for m in self._memberships_for(b)]
            return ScopeFilter(grants=grants, department_id=d, branch_id=b)

        # No explicit selection → collective view
        if self.org_wide:
            return ScopeFilter(grants=None)
        grants: List[Grant] = []
        for m in self.memberships:
            g = (m.branch_id, m.department_id)
            if g not in grants:
                grants.append(g)
        return ScopeFilter(grants=grants)

    # ── write target ────────────────────────────────────────────────────────
    def resolve_write_target(
        self, db: Session, branch_id=None, department_id=None, *, require_department: bool = False
    ) -> Tuple[uuid.UUID, Optional[uuid.UUID]]:
        """Validate and return (branch_id, department_id) for a new record."""
        b = _uuid(branch_id)
        d = _uuid(department_id)

        if d is not None and b is None:
            dep = db.query(Department).filter(
                Department.id == d, Department.organization_id == self.organization_id,
                Department.deleted == False,  # noqa: E712
            ).first()
            if not dep:
                raise ScopeError("Department not found.", 404)
            b = dep.branch_id

        if b is None:
            allowed = self.accessible_branch_ids(db)
            if len(allowed) == 1:
                b = allowed[0]
            else:
                raise ScopeError("Please choose which branch this record belongs to.", 400)

        self._assert_branch_in_org(db, b, must_be_active=True)
        if d is not None:
            self._assert_department_in_branch(db, d, b, must_be_active=True)
        elif require_department:
            raise ScopeError("Please choose a department.", 400)

        if not self.can_access(b, d):
            raise ScopeError("You do not have access to this branch or department.")
        # department-limited members must pick one of their own departments
        if not self.org_wide and not self.has_branch_wide_access(b) and d is None:
            own = [m.department_id for m in self._memberships_for(b)]
            if len(own) == 1:
                d = own[0]
            else:
                raise ScopeError("Please choose a department.", 400)
        return b, d

    # ── helpers ─────────────────────────────────────────────────────────────
    def _assert_branch_in_org(self, db: Session, branch_id, must_be_active: bool = False) -> Branch:
        q = db.query(Branch).filter(
            Branch.id == branch_id,
            Branch.organization_id == self.organization_id,
            Branch.deleted == False,  # noqa: E712
        )
        branch = q.first()
        if not branch:
            raise ScopeError("Branch not found.", 404)
        if must_be_active and not branch.is_active:
            raise ScopeError("This branch is deactivated.", 400)
        return branch

    def _assert_department_in_branch(self, db: Session, department_id, branch_id, must_be_active: bool = False) -> Department:
        dep = db.query(Department).filter(
            Department.id == department_id,
            Department.branch_id == branch_id,
            Department.organization_id == self.organization_id,
            Department.deleted == False,  # noqa: E712
        ).first()
        if not dep:
            raise ScopeError("Department not found in this branch.", 404)
        if must_be_active and not dep.is_active:
            raise ScopeError("This department is deactivated.", 400)
        return dep


# ─── Construction ────────────────────────────────────────────────────────────

def is_org_wide_user(user) -> bool:
    return bool(getattr(user, "is_org_admin", False)) or user.has_role("admin", "super_admin")


def build_access_scope(db: Session, user) -> AccessScope:
    org_id = user.organization_id
    if not org_id:
        raise ScopeError("User not associated with any organization", 403)
    memberships: List[BranchMembership] = []
    if not is_org_wide_user(user):
        memberships = (
            db.query(BranchMembership)
            .join(Branch, Branch.id == BranchMembership.branch_id)
            .filter(
                BranchMembership.user_id == user.id,
                BranchMembership.organization_id == org_id,
                Branch.deleted == False,  # noqa: E712
                Branch.is_active == True,  # noqa: E712
            )
            .all()
        )
    return AccessScope(organization_id=org_id, org_wide=is_org_wide_user(user), memberships=memberships)


def entity_scope_check(scope: AccessScope, entity) -> bool:
    """True if the caller may touch ``entity`` (anything with branch_id/department_id)."""
    return scope.can_access(getattr(entity, "branch_id", None), getattr(entity, "department_id", None))
