# app/api/v1/reports.py
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from app.api.deps.users import _get_org_id, get_db, get_current_user
from app.api.deps.rbac import require_roles
from app.models.user import User
from app.services.report_service import get_product_detail_report, get_report
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    period: daily | weekly | monthly | yearly
    month: 1-12 (used with period=monthly)
    year: e.g. 2025
    """
    valid_periods = ("daily", "weekly", "monthly", "yearly")
    if period not in valid_periods:
        return api_response(False, f"Invalid period. Choose one of: {', '.join(valid_periods)}", status_code=400)

    org_id = _get_org_id(current_user)
    data = get_report(db, period=period, year=year, month=month, item_id=item_id, dept=dept, organization_id=org_id)
    return api_response(True, f"{period.capitalize()} report generated.", data=data)


@router.get("/dashboard", summary="Dashboard summary stats")
async def dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Quick-load dashboard: today's stats + current stock counts."""
    org_id = _get_org_id(current_user)
    today = get_report(db, period="daily", organization_id=org_id)
    monthly = get_report(db, period="monthly", organization_id=org_id)

    items = inventory_service.get_items(db, organization_id=org_id)
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
        "top_products_today": sorted(
            today["products"], key=lambda x: x["total_revenue"], reverse=True
        )[:5],
    })


@router.get("/expenses", summary="Expense report")
async def expense_report(
    dept: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "super_admin", "manager")),
):
    org_id = _get_org_id(current_user)
    expenses = inventory_service.get_expenses(db, dept=dept, organization_id=org_id)
    total = sum(float(e.cost) for e in expenses)
    return api_response(True, "Expenses fetched.", data={
        "total_expenses": total,
        "count": len(expenses),
        "expenses": [e.get_summary() for e in expenses],
    })


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
    item = inventory_service.get_item(db, item_id)
    if not item or str(item.organization_id) != org_id:
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
    )
    if not data:
        return api_response(False, "Product not found.", status_code=404)

    return api_response(True, "Product report generated.", data=data)
