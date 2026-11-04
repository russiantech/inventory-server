# app/api/v1/expenses.py
import logging
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, field_validator
from typing import Optional

from app.api.deps.users import _get_org_id, get_db, get_current_user
from app.api.deps.rbac import require_roles
from app.models.user import User
from app.api.deps.scope import get_access_scope, get_scope_filter, scope_error_response
from app.services.scope_service import AccessScope, ScopeFilter, ScopeError
from app.services import inventory_service
from app.utils.responses import api_response, PageSerializer

logger = logging.getLogger(__name__)
router = APIRouter()


class ExpenseCreateSchema(BaseModel):
    cost: float
    dept: str = "general"
    comment: Optional[str] = None
    branch_id: Optional[str] = None
    department_id: Optional[str] = None
    # organization_id intentionally removed — derived server-side from the
    # authenticated user; clients must never supply it.

    @field_validator("cost")
    @classmethod
    def cost_positive(cls, v):
        if v <= 0:
            raise ValueError("Cost must be greater than zero")
        return v


@router.get(
    "/",
    summary="List expenses [manager/admin]",
    dependencies=[Depends(require_roles("admin", "super_admin", "manager"))],
)
async def list_expenses(
    request: Request,
    dept: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    sf: ScopeFilter = Depends(get_scope_filter),
):
    org_id = _get_org_id(current_user)
    expenses = inventory_service.get_expenses(db, dept=dept, organization_id=org_id, scope=sf)
    return PageSerializer(request, obj=expenses, resource_name="expenses").get_response("Expenses fetched.")


@router.post("/", summary="Record an expense [manager/admin]", status_code=201)
async def create_expense(
    data: ExpenseCreateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "super_admin", "manager")),
    scope: AccessScope = Depends(get_access_scope),
):
    org_id = _get_org_id(current_user)
    try:
        branch_id, department_id = scope.resolve_write_target(
            db, data.branch_id, data.department_id, require_department=True
        )
        scope.require_role(branch_id, "manager")
        exp = inventory_service.create_expense(
            db,
            cost=data.cost,
            dept=data.dept,
            comment=data.comment,
            user_id=current_user.id,
            organization_id=org_id,
            branch_id=branch_id,
            department_id=department_id,
        )
    except ScopeError as e:
        return scope_error_response(e)
    except ValueError as e:
        return api_response(False, str(e), status_code=400)
    return api_response(True, "Expense recorded.", data=exp.get_summary(), status_code=201)


@router.delete(
    "/{expense_id}",
    summary="Delete expense [org admin / branch admin]",
    dependencies=[Depends(require_roles("admin", "super_admin", "manager"))],
)
async def delete_expense(
    expense_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "super_admin", "manager")),
    scope: AccessScope = Depends(get_access_scope),
    sf: ScopeFilter = Depends(get_scope_filter),
):
    org_id = _get_org_id(current_user)
    from app.models.expenses import Expenses
    from app.services.scope_service import apply_scope
    exp = apply_scope(db.query(Expenses), Expenses, sf).filter(
        Expenses.id == expense_id,
        Expenses.deleted == False,
        Expenses.organization_id == org_id,
    ).first()
    if not exp:
        return api_response(False, "Expense not found.", status_code=404)
    try:
        scope.require_role(exp.branch_id, "admin")
    except ScopeError as e:
        return scope_error_response(e)
    inventory_service.delete_expense(db, exp, organization_id=org_id)
    return api_response(True, "Expense deleted.")
