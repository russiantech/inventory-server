# app/api/v1/reports.py
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from app.api.deps.users import _get_org_id, get_db, get_current_user
from app.api.deps.rbac import require_roles
from app.models.user import User
from app.api.deps.scope import get_access_scope, get_scope_filter
from app.services.scope_service import AccessScope, ScopeFilter
from app.services.report_service import get_product_detail_report, get_report, get_breakdown_report
from app.services import inventory_service
from app.utils.responses import api_response

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", summary="Get inventory/sales/profit report")
async def report(
    period: str = "daily",
    year: int = None,
    month: int = None,
    item_id: str = None,
    dept: str = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    category_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    sf: ScopeFilter = Depends(get_scope_filter),
):
    """
    period: daily | weekly | monthly | yearly
    month: 1-12 (used with period=monthly)
    year: e.g. 2025
    branch_id / department_id: optional. Omit for the collective view across
    every branch you may access; pass a branch for that branch alone.
    """
    valid_periods = ("daily", "weekly", "monthly", "yearly")
    if period not in valid_periods:
        return api_response(False, f"Invalid period. Choose one of: {', '.join(valid_periods)}", status_code=400)

    org_id = _get_org_id(current_user)
    if category_id:
        if not inventory_service.get_category(db, category_id, organization_id=org_id, scope=sf):
            return api_response(False, "Category not found.", status_code=404)
    data = get_report(db, period=period, year=year, month=month, start=start, end=end, item_id=item_id, dept=dept, organization_id=org_id, scope=sf, category_id=category_id)
    return api_response(True, f"{period.capitalize()} report generated.", data=data)


@router.get("/dashboard", summary="Dashboard summary stats")
async def dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    sf: ScopeFilter = Depends(get_scope_filter),
):
    """Quick-load dashboard: today's stats + current stock counts."""
    org_id = _get_org_id(current_user)
    today = get_report(db, period="daily", organization_id=org_id, scope=sf)
    monthly = get_report(db, period="monthly", organization_id=org_id, scope=sf)

    items = inventory_service.get_items(db, organization_id=org_id, scope=sf)
    low_stock = [i.get_summary() for i in items if i.in_stock < 5]
    out_of_stock = [i.get_summary() for i in items if i.in_stock == 0]

    return api_response(True, "Dashboard data.", data={
        "today": today["summary"],
        "this_month": monthly["summary"],
        "inventory": {
            "total_products": len(items),
            "total_current_stock": today["summary"]["total_current_stock"],
            "low_stock_count": len(low_stock),
            "out_of_stock_count": len(out_of_stock),
            "low_stock_items": low_stock[:10],
        },
        "scope": sf.describe(),
        "top_products_today": sorted(
            today["products"], key=lambda x: x["total_revenue"], reverse=True
        )[:5],
    })


@router.get("/expenses", summary="Expense report")
async def expense_report(
    dept: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "super_admin", "manager")),
    sf: ScopeFilter = Depends(get_scope_filter),
):
    org_id = _get_org_id(current_user)
    expenses = inventory_service.get_expenses(db, dept=dept, organization_id=org_id, scope=sf)
    total = sum(float(e.cost) for e in expenses)
    return api_response(True, "Expenses fetched.", data={
        "total_expenses": total,
        "count": len(expenses),
        "expenses": [e.get_summary() for e in expenses],
    })


@router.get("/breakdown", summary="Compare branches (or departments) side by side")
async def breakdown_report(
    group_by: str = "branch",
    period: str = "monthly",
    year: int = None,
    month: int = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    sf: ScopeFilter = Depends(get_scope_filter),
):
    """
    group_by: branch | department.
    Org admins get every branch; branch members only their own. Pass
    ``branch_id`` with ``group_by=department`` to compare one branch's departments.
    """
    if group_by not in ("branch", "department"):
        return api_response(False, "group_by must be 'branch' or 'department'.", status_code=400)
    if period not in ("daily", "weekly", "monthly", "yearly", "custom"):
        return api_response(False, "Invalid period.", status_code=400)
    org_id = _get_org_id(current_user)
    data = get_breakdown_report(
        db, org_id, scope=sf, group_by=group_by, period=period,
        year=year, month=month, start=start, end=end,
    )
    return api_response(True, f"{group_by.capitalize()} comparison generated.", data=data)


@router.get("/product/{item_id}", summary="Detailed product report")
async def product_detail_report(
    item_id: str,
    period: str = "daily",
    year: int = None,
    month: int = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    sf: ScopeFilter = Depends(get_scope_filter),
):
    valid_periods = ("daily", "weekly", "monthly", "yearly", "custom")
    if period not in valid_periods:
        return api_response(
            False,
            f"Invalid period. Choose one of: {', '.join(valid_periods)}",
            status_code=400,
        )

    org_id = _get_org_id(current_user)

    # Verify item belongs to this organisation before reporting
    item = inventory_service.get_item(db, item_id, organization_id=org_id, scope=sf)
    if not item:
        return api_response(False, "Product not found.", status_code=404)

    data = get_product_detail_report(
        db=db,
        item_id=item_id,
        period=period,
        year=year,
        month=month,
        start=start,
        end=end,
        organization_id=org_id,
        scope=sf,
    )
    if not data:
        return api_response(False, "Product not found.", status_code=404)

    return api_response(True, "Product report generated.", data=data)
