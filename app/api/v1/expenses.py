# app/api/v1/expenses.py
import logging
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, field_validator
from typing import Optional

from app.api.deps.users import _get_org_id, get_db, get_current_user
from app.api.deps.rbac import require_roles
from app.models.user import User
from app.services import inventory_service
from app.utils.responses import api_response, PageSerializer

logger = logging.getLogger(__name__)
router = APIRouter()


class ExpenseCreateSchema(BaseModel):
    cost: float
    dept: str = "general"
    comment: Optional[str] = None
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
):
    org_id = _get_org_id(current_user)
    expenses = inventory_service.get_expenses(db, dept=dept, organization_id=org_id)
    return PageSerializer(request, obj=expenses, resource_name="expenses").get_response("Expenses fetched.")


@router.post("/", summary="Record an expense [manager/admin]", status_code=201)
async def create_expense(
    data: ExpenseCreateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "super_admin", "manager")),
):
    org_id = _get_org_id(current_user)
    exp = inventory_service.create_expense(
        db,
        cost=data.cost,
        dept=data.dept,
        comment=data.comment,
        user_id=current_user.id,
        organization_id=org_id,
    )
    return api_response(True, "Expense recorded.", data=exp.get_summary(), status_code=201)


@router.delete(
    "/{expense_id}",
    summary="Delete expense [admin]",
    dependencies=[Depends(require_roles("admin", "super_admin"))],
)
async def delete_expense(
    expense_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "super_admin")),
):
    org_id = _get_org_id(current_user)
    from app.models.expenses import Expenses
    exp = db.query(Expenses).filter(
        Expenses.id == expense_id,
        Expenses.deleted == False,
        Expenses.organization_id == org_id,
    ).first()
    if not exp:
        return api_response(False, "Expense not found.", status_code=404)
    inventory_service.delete_expense(db, exp, organization_id=org_id)
    return api_response(True, "Expense deleted.")
