# app/api/v1/reports.py
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Optional

from app.api.deps.users import get_db, get_current_user
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

    data = get_report(db, period=period, year=year, month=month, item_id=item_id, dept=dept)
    return api_response(True, f"{period.capitalize()} report generated.", data=data)


@router.get("/dashboard", summary="Dashboard summary stats")
async def dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Quick-load dashboard: today's stats + current stock counts."""
    today = get_report(db, period="daily")
    monthly = get_report(db, period="monthly")

    items = inventory_service.get_items(db)
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
    expenses = inventory_service.get_expenses(db, dept=dept)
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
    include_expenses: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    valid_periods = ("daily", "weekly", "monthly", "yearly", "custom")

    if period not in valid_periods:
        return api_response(
            False,
            f"Invalid period. Choose one of: {', '.join(valid_periods)}",
            status_code=400
        )

    data = get_product_detail_report(
        db=db,
        item_id=item_id,
        period=period,
        year=year,
        month=month,
        start=start,
        end=end,
        # include_expenses=include_expenses,
    )

    if not data:
        return api_response(False, "Product not found.", status_code=404)

    return api_response(
        True,
        "Product report generated.",
        data=data
    )
    
