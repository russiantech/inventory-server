# app/api/v1/branches.py
"""
Branch management + membership (staff / branch-admin assignment).

Permissions
-----------
* Org-wide admins (org owner, role admin / super_admin): everything.
* Branch admins: manage their own branch's details, departments and
  manager/staff memberships. They cannot create branches or grant branch-admin.
* Everyone else: read-only view of the branches they belong to (``/me``).
"""
import logging
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps.users import get_db, get_current_user
from app.api.deps.scope import get_access_scope, scope_error_response
from app.models.branch import BranchMembership
from app.models.user import User
from app.schemas.branch import BranchCreate, BranchUpdate, MemberAssign
from app.services import branch_service
from app.services.scope_service import AccessScope, ScopeError
from app.utils.responses import api_response

logger = logging.getLogger(__name__)
router = APIRouter()


def _branch_payload(db: Session, scope: AccessScope, branch) -> dict:
    data = branch.get_summary(include_counts=True)
    data["my_role"] = scope.branch_role(branch.id)
    data["branch_wide_access"] = scope.has_branch_wide_access(branch.id)
    if not scope.org_wide and not scope.has_branch_wide_access(branch.id):
        allowed = {m.department_id for m in scope._memberships_for(branch.id)}
        data["departments"] = [d for d in data["departments"] if uuid.UUID(d["id"]) in allowed]
    return data


@router.get("/me", summary="Branches/departments the current user can work in")
async def my_scope(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    scope: AccessScope = Depends(get_access_scope),
):
    # Safety net for organizations created before branches existed.
    branch_service.ensure_default_branch(db, scope.organization_id)
    ids = None if scope.org_wide else scope.accessible_branch_ids(db)
    branches = branch_service.list_branches(db, scope.organization_id, branch_ids=ids)
    payload = [_branch_payload(db, scope, b) for b in branches]
    default = next((b for b in payload if b["is_default"]), payload[0] if payload else None)
    return api_response(True, "Scope fetched.", data={
        "is_org_wide": scope.org_wide,
        "branches": payload,
        "default_branch_id": default["id"] if default else None,
        "can_create_branch": scope.org_wide,
    })


@router.get("", summary="List branches visible to the caller")
async def list_branches(
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_access_scope),
):
    ids = None if scope.org_wide else scope.accessible_branch_ids(db)
    branches = branch_service.list_branches(db, scope.organization_id, branch_ids=ids)
    return api_response(True, "Branches fetched.", data={"branches": [_branch_payload(db, scope, b) for b in branches]})


@router.post("", summary="Create a branch [org admin]", status_code=201)
async def create_branch(
    data: BranchCreate,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_access_scope),
):
    try:
        scope.require_org_wide("Only organization admins can create branches.")
        branch = branch_service.create_branch(
            db, scope.organization_id, data.name, code=data.code, address=data.address,
            phone=data.phone, description=data.description, departments=data.departments,
        )
    except ScopeError as e:
        return scope_error_response(e)
    except ValueError as e:
        return api_response(False, str(e), status_code=400)
    return api_response(True, f"Branch '{branch.name}' created.", data=_branch_payload(db, scope, branch), status_code=201)


@router.get("/{branch_id}", summary="Get a branch")
async def get_branch(
    branch_id: uuid.UUID,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_access_scope),
):
    branch = branch_service.get_branch(db, branch_id, scope.organization_id)
    if not branch or not scope.can_access(branch.id):
        return api_response(False, "Branch not found.", status_code=404)
    return api_response(True, "Branch fetched.", data=_branch_payload(db, scope, branch))


@router.put("/{branch_id}", summary="Update a branch [org admin / branch admin]")
async def update_branch(
    branch_id: uuid.UUID,
    data: BranchUpdate,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_access_scope),
):
    branch = branch_service.get_branch(db, branch_id, scope.organization_id)
    if not branch or not scope.can_access(branch.id):
        return api_response(False, "Branch not found.", status_code=404)
    payload = data.model_dump(exclude_unset=True)
    try:
        scope.require_role(branch.id, "admin")
        if not scope.org_wide:
            # branch admins may only edit descriptive details
            payload = {k: v for k, v in payload.items() if k in ("address", "phone", "description")}
        branch = branch_service.update_branch(db, branch, payload)
    except ScopeError as e:
        return scope_error_response(e)
    except ValueError as e:
        return api_response(False, str(e), status_code=400)
    return api_response(True, "Branch updated.", data=_branch_payload(db, scope, branch))


@router.delete("/{branch_id}", summary="Delete a branch [org admin] — only if it holds no data")
async def delete_branch(
    branch_id: uuid.UUID,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_access_scope),
):
    branch = branch_service.get_branch(db, branch_id, scope.organization_id)
    if not branch:
        return api_response(False, "Branch not found.", status_code=404)
    try:
        scope.require_org_wide("Only organization admins can delete branches.")
        branch_service.delete_branch(db, branch)
    except ScopeError as e:
        return scope_error_response(e)
    except ValueError as e:
        return api_response(False, str(e), status_code=400)
    return api_response(True, "Branch deleted.")


# ─── Members ─────────────────────────────────────────────────────────────────

@router.get("/{branch_id}/members", summary="List branch members [org admin / branch admin]")
async def list_members(
    branch_id: uuid.UUID,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_access_scope),
):
    branch = branch_service.get_branch(db, branch_id, scope.organization_id)
    if not branch or not scope.can_access(branch.id):
        return api_response(False, "Branch not found.", status_code=404)
    try:
        scope.require_role(branch.id, "admin")
    except ScopeError as e:
        return scope_error_response(e)
    members = branch_service.list_members(db, branch.id, scope.organization_id)
    return api_response(True, "Members fetched.", data={"members": [m.get_summary() for m in members]})


@router.get("/{branch_id}/assignable-users", summary="Org users that can be assigned to this branch [org admin / branch admin]")
async def assignable_users(
    branch_id: uuid.UUID,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_access_scope),
):
    branch = branch_service.get_branch(db, branch_id, scope.organization_id)
    if not branch or not scope.can_access(branch.id):
        return api_response(False, "Branch not found.", status_code=404)
    try:
        scope.require_role(branch.id, "admin")
    except ScopeError as e:
        return scope_error_response(e)
    users = db.query(User).filter(
        User.organization_id == scope.organization_id, User.deleted == False,  # noqa: E712
        User.is_org_admin == False,  # noqa: E712
    ).order_by(User.names, User.username).all()
    users = [u for u in users if not u.has_role("admin", "super_admin")]
    return api_response(True, "Users fetched.", data={"users": [
        {"id": str(u.id), "username": u.username, "names": u.names, "email": u.email,
         "roles": u.role_names, "is_active": u.is_active} for u in users
    ]})


@router.post("/{branch_id}/members", summary="Assign a user to a branch [org admin / branch admin]", status_code=201)
async def assign_member(
    branch_id: uuid.UUID,
    data: MemberAssign,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    scope: AccessScope = Depends(get_access_scope),
):
    branch = branch_service.get_branch(db, branch_id, scope.organization_id)
    if not branch or not scope.can_access(branch.id):
        return api_response(False, "Branch not found.", status_code=404)
    try:
        scope.require_role(branch.id, "admin")
        if data.role == "admin" and not scope.org_wide:
            raise ScopeError("Only organization admins can appoint a branch admin.")
    except ScopeError as e:
        return scope_error_response(e)

    user = db.query(User).filter(
        User.id == data.user_id, User.organization_id == scope.organization_id, User.deleted == False  # noqa: E712
    ).first()
    if not user:
        return api_response(False, "User not found in your organization.", status_code=404)
    if user.is_org_admin or user.has_role("admin", "super_admin"):
        return api_response(False, "Organization admins already have access to every branch.", status_code=400)
    try:
        member = branch_service.assign_member(
            db, scope.organization_id, user, branch, data.role,
            department_id=data.department_id, assigned_by=current_user.id,
        )
    except ValueError as e:
        return api_response(False, str(e), status_code=400)
    return api_response(True, f"{user.names or user.username} assigned to {branch.name}.", data=member.get_summary(), status_code=201)


@router.delete("/{branch_id}/members/{membership_id}", summary="Remove a branch assignment [org admin / branch admin]")
async def remove_member(
    branch_id: uuid.UUID,
    membership_id: uuid.UUID,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_access_scope),
):
    branch = branch_service.get_branch(db, branch_id, scope.organization_id)
    if not branch or not scope.can_access(branch.id):
        return api_response(False, "Branch not found.", status_code=404)
    member = db.query(BranchMembership).filter(
        BranchMembership.id == membership_id, BranchMembership.branch_id == branch.id,
        BranchMembership.organization_id == scope.organization_id,
    ).first()
    if not member:
        return api_response(False, "Assignment not found.", status_code=404)
    try:
        scope.require_role(branch.id, "admin")
        if member.role == "admin" and not scope.org_wide:
            raise ScopeError("Only organization admins can remove a branch admin.")
    except ScopeError as e:
        return scope_error_response(e)
    branch_service.remove_member(db, member)
    return api_response(True, "Assignment removed.")
