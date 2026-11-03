# app/api/v1/departments.py
"""Departments live inside a branch. Managed by org admins and that branch's admins."""
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps.users import get_db
from app.api.deps.scope import get_access_scope, scope_error_response
from app.schemas.branch import DepartmentCreate, DepartmentUpdate
from app.services import branch_service
from app.services.scope_service import AccessScope, ScopeError
from app.utils.responses import api_response

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", summary="List departments the caller can see")
async def list_departments(
    branch_id: Optional[uuid.UUID] = None,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_access_scope),
):
    if branch_id and not scope.can_access(branch_id):
        return api_response(False, "Branch not found.", status_code=404)
    ids = None if scope.org_wide else scope.accessible_branch_ids(db)
    depts = branch_service.list_departments(db, scope.organization_id, branch_id=branch_id, branch_ids=ids)
    depts = [d for d in depts if scope.can_access(d.branch_id, d.id)]
    return api_response(True, "Departments fetched.", data={"departments": [d.get_summary() for d in depts]})


@router.post("", summary="Create a department [org admin / branch admin]", status_code=201)
async def create_department(
    data: DepartmentCreate,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_access_scope),
):
    branch = branch_service.get_branch(db, data.branch_id, scope.organization_id)
    if not branch or not scope.can_access(branch.id):
        return api_response(False, "Branch not found.", status_code=404)
    try:
        scope.require_role(branch.id, "admin")
        dept = branch_service.create_department(db, scope.organization_id, branch.id, data.name, data.description)
    except ScopeError as e:
        return scope_error_response(e)
    except ValueError as e:
        return api_response(False, str(e), status_code=400)
    return api_response(True, f"Department '{dept.name}' created.", data=dept.get_summary(), status_code=201)


def _load(db: Session, scope: AccessScope, department_id):
    dept = branch_service.get_department(db, department_id, scope.organization_id)
    if not dept or not scope.can_access(dept.branch_id):
        return None
    return dept


@router.put("/{department_id}", summary="Update a department [org admin / branch admin]")
async def update_department(
    department_id: uuid.UUID,
    data: DepartmentUpdate,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_access_scope),
):
    dept = _load(db, scope, department_id)
    if not dept:
        return api_response(False, "Department not found.", status_code=404)
    try:
        scope.require_role(dept.branch_id, "admin")
        dept = branch_service.update_department(db, dept, data.model_dump(exclude_unset=True))
    except ScopeError as e:
        return scope_error_response(e)
    except ValueError as e:
        return api_response(False, str(e), status_code=400)
    return api_response(True, "Department updated.", data=dept.get_summary())


@router.delete("/{department_id}", summary="Delete a department [org admin / branch admin]")
async def delete_department(
    department_id: uuid.UUID,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_access_scope),
):
    dept = _load(db, scope, department_id)
    if not dept:
        return api_response(False, "Department not found.", status_code=404)
    try:
        scope.require_role(dept.branch_id, "admin")
        branch_service.delete_department(db, dept)
    except ScopeError as e:
        return scope_error_response(e)
    except ValueError as e:
        return api_response(False, str(e), status_code=400)
    return api_response(True, "Department deleted.")
