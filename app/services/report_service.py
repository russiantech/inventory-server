# # app/services/report_service.py
# from datetime import datetime, timedelta
# from sqlalchemy import desc
# from sqlalchemy.orm import joinedload, Session

# from app.models.items import Items
# from app.models.stock_history import StockHistory
# from app.models.sales import Sales
# from app.models.expenses import Expenses

# def _resolve_date_range(
#     period: str = "daily",
#     year: int = None,
#     month: int = None,
#     start: str = None,
#     end: str = None,
# ):
#     """
#     Resolve report date range.

#     Supports:
#     - daily
#     - weekly
#     - monthly
#     - yearly
#     - custom (via start/end)
#     """

#     now = datetime.utcnow()

#     # Custom range
#     if start and end:
#         start_date = datetime.fromisoformat(start)
#         end_date = datetime.fromisoformat(end)

#         # Include full final day
#         end_date = end_date.replace(
#             hour=23,
#             minute=59,
#             second=59,
#             microsecond=999999,
#         )

#         return start_date, end_date

#     # Daily
#     if period == "daily":
#         start_date = now.replace(
#             hour=0,
#             minute=0,
#             second=0,
#             microsecond=0,
#         )
#         end_date = now

#     # Weekly
#     elif period == "weekly":
#         start_date = now - timedelta(days=7)
#         end_date = now

#     # Monthly
#     elif period == "monthly":
#         y = year or now.year
#         m = month or now.month

#         start_date = datetime(y, m, 1)

#         if m == 12:
#             end_date = datetime(y + 1, 1, 1) - timedelta(microseconds=1)
#         else:
#             end_date = datetime(y, m + 1, 1) - timedelta(microseconds=1)

#     # Yearly
#     elif period == "yearly":
#         y = year or now.year

#         start_date = datetime(y, 1, 1)

#         end_date = datetime(
#             y,
#             12,
#             31,
#             23,
#             59,
#             59,
#             999999,
#         )

#     else:
#         raise ValueError(
#             "Invalid period. Use daily, weekly, monthly, yearly or custom range."
#         )

#     return start_date, end_date


# def get_report(
#     db: Session,
#     period: str = "daily",
#     year: int = None,
#     month: int = None,
#     item_id=None,
#     dept: str = None,
#     start: str = None,
#     end: str = None,
#     include_expenses: bool = True,
# ):
#     """
#     Comprehensive inventory/sales/profit reporting service.
#     """

#     start_date, end_date = _resolve_date_range(
#         period=period,
#         year=year,
#         month=month,
#         start=start,
#         end=end,
#     )

#     # =========================================================
#     # SALES
#     # =========================================================

#     sales_query = (
#         db.query(Sales)
#         .options(
#             joinedload(Sales.item),
#         )
#         .filter(
#             Sales.deleted == False,
#             Sales.sale_date >= start_date,
#             Sales.sale_date <= end_date,
#         )
#     )

#     if item_id:
#         sales_query = sales_query.filter(
#             Sales.item_id == item_id
#         )

#     if dept:
#         sales_query = sales_query.filter(
#             Sales.dept == dept
#         )

#     sales_rows = (
#         sales_query
#         .order_by(desc(Sales.sale_date))
#         .all()
#     )

#     # =========================================================
#     # STOCK HISTORY
#     # =========================================================

#     stock_query = (
#         db.query(StockHistory)
#         .options(
#             joinedload(StockHistory.item),
#         )
#         .filter(
#             StockHistory.deleted == False,
#             StockHistory.date_in >= start_date,
#             StockHistory.date_in <= end_date,
#         )
#     )

#     if item_id:
#         stock_query = stock_query.filter(
#             StockHistory.item_id == item_id
#         )

#     stock_rows = stock_query.all()

#     # =========================================================
#     # INVENTORY ITEMS
#     # =========================================================

#     inventory_query = (
#         db.query(Items)
#         .filter(
#             Items.deleted == False
#         )
#     )

#     if item_id:
#         inventory_query = inventory_query.filter(
#             Items.id == item_id
#         )

#     if dept:
#         inventory_query = inventory_query.filter(
#             Items.dept == dept
#         )

#     inventory_items = inventory_query.all()

#     # =========================================================
#     # EXPENSES
#     # =========================================================

#     expense_query = (
#         db.query(Expenses)
#         .filter(
#             Expenses.deleted == False,
#             Expenses.created_at >= start_date,
#             Expenses.created_at <= end_date,
#         )
#     )

#     if dept:
#         expense_query = expense_query.filter(
#             Expenses.dept == dept
#         )

#     expenses_rows = (
#         expense_query
#         .order_by(desc(Expenses.created_at))
#         .all()
#     )

#     # =========================================================
#     # PRODUCT BREAKDOWN
#     # =========================================================

#     product_breakdown = {}

#     # ---------------------------------------------------------
#     # Initialize from inventory items
#     # ---------------------------------------------------------

#     for item in inventory_items:

#         pid = str(item.id)

#         product_breakdown[pid] = {
#             "item_id": pid,
#             "item_name": item.name,
#             "category_name": (
#                 getattr(item.category, "name", None)
#                 if getattr(item, "category", None)
#                 else None
#             ),

#             # sales
#             "qty_sold": 0,
#             "transactions": 0,
#             "total_revenue": 0.0,
#             "profit": 0.0,

#             # stock
#             "qty_in_stock": item.in_stock or 0,
#             "total_stock_received": 0,

#             # analytics
#             "revenue_share": 0.0,
#         }

#     # ---------------------------------------------------------
#     # Aggregate stock-in
#     # ---------------------------------------------------------

#     for stock in stock_rows:

#         pid = str(stock.item_id)

#         if pid not in product_breakdown:

#             item = stock.item

#             product_breakdown[pid] = {
#                 "item_id": pid,
#                 "item_name": item.name if item else "Unknown",
#                 "category_name": (
#                     getattr(item.category, "name", None)
#                     if item and getattr(item, "category", None)
#                     else None
#                 ),

#                 "qty_sold": 0,
#                 "transactions": 0,
#                 "total_revenue": 0.0,
#                 "profit": 0.0,

#                 "qty_in_stock": (
#                     getattr(item, "in_stock", 0)
#                     if item else 0
#                 ),

#                 "total_stock_received": 0,
#                 "revenue_share": 0.0,
#             }

#         product_breakdown[pid]["total_stock_received"] += (
#             stock.quantity_in or 0
#         )

#     # ---------------------------------------------------------
#     # Aggregate sales
#     # ---------------------------------------------------------

#     for sale in sales_rows:

#         pid = str(sale.item_id)

#         item = sale.item

#         if pid not in product_breakdown:

#             product_breakdown[pid] = {
#                 "item_id": pid,
#                 "item_name": item.name if item else "Unknown",

#                 "category_name": (
#                     getattr(item.category, "name", None)
#                     if item and getattr(item, "category", None)
#                     else None
#                 ),

#                 "qty_sold": 0,
#                 "transactions": 0,
#                 "total_revenue": 0.0,
#                 "profit": 0.0,

#                 "qty_in_stock": (
#                     getattr(item, "in_stock", 0)
#                     if item else 0
#                 ),

#                 "total_stock_received": 0,
#                 "revenue_share": 0.0,
#             }

#         qty_sold = int(sale.qty_sold or 0)

#         revenue = float(sale.total_price or 0)

#         profit = float(sale.profit or 0)

#         # fallback profit calculation
#         if not profit and item:

#             cost_price = float(
#                 getattr(item, "c_price", 0) or 0
#             )

#             unit_price = float(
#                 getattr(sale, "unit_price", 0) or 0
#             )

#             profit = (
#                 (unit_price - cost_price)
#                 * qty_sold
#             )

#         product_breakdown[pid]["qty_sold"] += qty_sold
#         product_breakdown[pid]["transactions"] += 1
#         product_breakdown[pid]["total_revenue"] += revenue
#         product_breakdown[pid]["profit"] += profit

#     # =========================================================
#     # PRODUCTS LIST
#     # =========================================================

#     products = list(product_breakdown.values())

#     # =========================================================
#     # TOTALS
#     # =========================================================

#     total_revenue = sum(
#         float(p["total_revenue"] or 0)
#         for p in products
#     )

#     total_profit = sum(
#         float(p["profit"] or 0)
#         for p in products
#     )

#     total_units_sold = sum(
#         int(p["qty_sold"] or 0)
#         for p in products
#     )

#     total_stock_in = sum(
#         int(p["total_stock_received"] or 0)
#         for p in products
#     )

#     total_current_stock = sum(
#         int(i.in_stock or 0)
#         for i in inventory_items
#     )

#     inventory_value_cost = sum(
#         (float(i.c_price or 0) * int(i.in_stock or 0))
#         for i in inventory_items
#     )

#     inventory_value_retail = sum(
#         (float(i.s_price or 0) * int(i.in_stock or 0))
#         for i in inventory_items
#     )

#     # =========================================================
#     # EXPENSE TOTALS
#     # =========================================================

#     actual_total_expenses = sum(
#         float(e.cost or 0)
#         for e in expenses_rows
#     )

#     # Important:
#     # frontend still expects expenses rows even if excluded
#     total_expenses = (
#         actual_total_expenses
#         if include_expenses
#         else 0
#     )

#     net_profit = (
#         total_profit - actual_total_expenses
#         if include_expenses
#         else total_profit
#     )

#     # =========================================================
#     # REVENUE SHARE
#     # =========================================================

#     for product in products:

#         revenue = float(
#             product["total_revenue"] or 0
#         )

#         product["revenue_share"] = (
#             round((revenue / total_revenue) * 100, 2)
#             if total_revenue > 0
#             else 0
#         )

#     # =========================================================
#     # SALES DATA
#     # =========================================================

#     sales_data = []

#     for sale in sales_rows:

#         recorded_by = None

#         rb = getattr(sale, "recorded_by", None)

#         if rb:
#             recorded_by = (
#                 getattr(rb, "names", None)
#                 or getattr(rb, "full_name", None)
#                 or getattr(rb, "username", None)
#             )

#         sales_data.append({
#             "id": sale.id,
#             "item_id": sale.item_id,

#             "item_name": (
#                 sale.item.name
#                 if sale.item
#                 else "Unknown"
#             ),

#             "qty_sold": sale.qty_sold,

#             "unit_price": float(
#                 sale.unit_price or 0
#             ),

#             "total_price": float(
#                 sale.total_price or 0
#             ),

#             "profit": float(
#                 sale.profit or 0
#             ),

#             "stock_after": sale.stock_after,

#             "sale_date": sale.sale_date,
#             "created_at": sale.created_at,

#             "recorded_by": recorded_by,

#             "dept": getattr(
#                 sale,
#                 "dept",
#                 None,
#             ),

#             "is_void": getattr(
#                 sale,
#                 "is_void",
#                 False,
#             ),
#         })

#     # =========================================================
#     # SUMMARY
#     # =========================================================

#     summary = {
#         "total_revenue": total_revenue,

#         "total_units_sold": total_units_sold,

#         "total_transactions": len(sales_rows),

#         "gross_profit": total_profit,

#         "total_expenses": total_expenses,

#         "net_profit": net_profit,

#         "total_stock_in": total_stock_in,

#         "total_current_stock": total_current_stock,

#         "inventory_value_cost": inventory_value_cost,

#         "inventory_value_retail": inventory_value_retail,
#     }

#     # =========================================================
#     # RESPONSE
#     # =========================================================

#     return {
#         "period": period,

#         "start": start_date.isoformat(),
#         "end": end_date.isoformat(),

#         "include_expenses": include_expenses,

#         "summary": summary,

#         "products": sorted(
#             products,
#             key=lambda x: x["total_revenue"],
#             reverse=True,
#         ),

#         "sales": sales_data,

#         "sales_count": len(sales_data),

#         "stock_entries": len(stock_rows),

#         # IMPORTANT:
#         # Always return rows for frontend consistency
#         "expenses": [
#             e.get_summary()
#             for e in expenses_rows
#         ] if include_expenses else [],
#     }

# def get_product_detail_report(
#     db,
#     item_id,
#     period="daily",
#     year=None,
#     month=None,
#     start=None,
#     end=None,
#     include_expenses=True,
# ):
#     item = db.query(Items).filter(Items.id == item_id).first()

#     if not item:
#         return None

#     now = datetime.utcnow()

#     if period == "daily":
#         start_date = datetime(now.year, now.month, now.day)

#     elif period == "weekly":
#         start_date = now - timedelta(days=7)

#     elif period == "monthly":
#         year = year or now.year
#         month = month or now.month
#         start_date = datetime(year, month, 1)

#     elif period == "yearly":
#         year = year or now.year
#         start_date = datetime(year, 1, 1)

#     elif period == "custom":
#         start_date = datetime.fromisoformat(start)
#         end_date = datetime.fromisoformat(end)

#     else:
#         start_date = now - timedelta(days=1)

#     if period != "custom":
#         end_date = now

#     sales = (
#         db.query(Sales)
#         .filter(
#             Sales.item_id == item_id,
#             Sales.created_at >= start_date,
#             Sales.created_at <= end_date,
#         )
#         .order_by(Sales.created_at.desc())
#         .all()
#     )

#     stock_history = (
#         db.query(StockHistory)
#         .filter(
#             StockHistory.item_id == item_id,
#             StockHistory.created_at >= start_date,
#             StockHistory.created_at <= end_date,
#         )
#         .order_by(StockHistory.created_at.desc())
#         .all()
#     )

#     qty_sold = sum(s.qty_sold for s in sales)
#     revenue = sum(float(s.total_price or 0) for s in sales)

#     profit = sum(
#         # float((s.unit_price - (s.unit_cost or 0)) * s.qty_sold)
#         float((s.unit_price - (s.cost_price or 0)) * s.qty_sold)
#         for s in sales
#     )

#     total_stock_in = sum(h.quantity_in for h in stock_history)

#     avg_unit_price = (
#         revenue / qty_sold
#         if qty_sold > 0 else 0
#     )

#     return {
#         "summary": {
#             "qty_sold": qty_sold,
#             "current_stock": item.in_stock,
#             "total_stock_in": total_stock_in,
#             "transactions": len(sales),
#             "total_revenue": revenue,
#             "profit": profit,
#             "avg_unit_price": avg_unit_price,
#         },

#         # "sales": [
#         #     {
#         #         "id": s.id,
#         #         "qty_sold": s.qty_sold,
#         #         "unit_price": s.unit_price,
#         #         "total_price": s.total_price,
#         #         "stock_after": s.stock_after,
#         #         "sale_date": s.sale_date,
#         #         "created_at": s.created_at,
#         #         "recorded_by": getattr(s.user, "full_name", None),
#         #         "is_void": getattr(s, "is_void", False),
#         #     }
#         #     for s in sales
#         # ],
        
#         "sales": [
#             {
#                 "id": s.id,
#                 "sale_date": s.sale_date,
#                 "created_at": s.created_at,
#                 "qty_sold": s.qty_sold,
#                 "unit_price": s.unit_price,
#                 "total_price": s.total_price,
#                 "stock_after": s.stock_after,
#                 "recorded_by": getattr(s.recorded_by, "names", None),
#                 "is_void": getattr(s, "is_void", False),
#             }
#             for s in sales
#         ],

#         "stock_history": [
#             {
#                 "id": h.id,
#                 "quantity_in": h.quantity_in,
#                 "stock_after": h.stock_after,
#                 "unit_cost": getattr(h, "unit_cost", 0),
#                 "date_in": h.created_at,
#                 "is_reversal": getattr(h, "is_reversal", False),
#             }
#             for h in stock_history
#         ]
#     }


# v2
# app/services/report_service.py
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.models.items import Items
from app.models.stock_history import StockHistory
from app.models.sales import Sales
from app.models.expenses import Expenses
from app.models.branch import Branch, Department
from app.services.scope_service import ScopeFilter, apply_scope


def _date_range(period: str, year: int = None, month: int = None, start: str = None, end: str = None):
    """Return (start_dt, end_dt) UTC. Custom range takes priority."""
    if period == "custom" and start and end:
        from datetime import date
        s = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
        e = datetime.fromisoformat(end).replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        return s, e

    now = datetime.now(timezone.utc)
    y = year or now.year

    if period == "daily":
        s = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return s, s + timedelta(days=1)
    elif period == "weekly":
        s = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        return s, s + timedelta(days=7)
    elif period == "monthly":
        m = month or now.month
        s = datetime(y, m, 1, tzinfo=timezone.utc)
        e = datetime(y + 1, 1, 1, tzinfo=timezone.utc) if m == 12 else datetime(y, m + 1, 1, tzinfo=timezone.utc)
        return s, e
    elif period == "yearly":
        return datetime(y, 1, 1, tzinfo=timezone.utc), datetime(y + 1, 1, 1, tzinfo=timezone.utc)
    else:  # default daily
        s = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return s, s + timedelta(days=1)


def get_report(
    db: Session,
    period: str = "daily",
    year: int = None,
    month: int = None,
    start: str = None,
    end: str = None,
    item_id=None,
    dept: str = None,
    include_expenses: bool = True,
    organization_id: str = None,
    scope: Optional[ScopeFilter] = None,
    category_id=None,
):
    p = "custom" if (start and end) else period
    category_item_ids = None
    if category_id:
        # the category and all of its sub-categories
        from app.models.category import Category
        ids, frontier = {category_id}, [category_id]
        while frontier:
            kids = [c[0] for c in db.query(Category.id).filter(Category.parent_id.in_(frontier), Category.deleted == False).all()]  # noqa: E712
            frontier = [k for k in kids if k not in ids]
            ids.update(frontier)
        category_item_ids = db.query(Items.id).filter(Items.category_id.in_(ids))
    s_dt, e_dt = _date_range(p, year=year, month=month, start=start, end=end)

    # ── Sales ──────────────────────────────────────────────────────────────────
    sq = db.query(Sales).filter(
        Sales.deleted == False,
        # Sales.is_void == False,
        Sales.sale_date >= s_dt,
        Sales.sale_date < e_dt,
    )
    if item_id:
        sq = sq.filter(Sales.item_id == item_id)
    if category_item_ids is not None:
        sq = sq.filter(Sales.item_id.in_(category_item_ids))
    if dept:
        sq = sq.filter(Sales.dept == dept)
    if organization_id:
        sq = sq.filter(Sales.organization_id == organization_id)
    sq = apply_scope(sq, Sales, scope)
    sales_rows = sq.order_by(desc(Sales.sale_date)).all()

    total_revenue = sum(float(s.total_price) for s in sales_rows)
    total_units_sold = sum(s.qty_sold for s in sales_rows)
    total_profit = sum(float(s.profit) for s in sales_rows if s.profit)

    # Per-product breakdown
    product_breakdown: dict = {}
    for s in sales_rows:
        pid = str(s.item_id)
        if pid not in product_breakdown:
            item = s.item
            product_breakdown[pid] = {
                "item_id": pid,
                "item_name": item.name if item else "Unknown",
                "category_name": (item.category.name if item and item.category else None),
                "qty_sold": 0, "total_revenue": 0.0, "profit": 0.0, "transactions": 0,
                "qty_in_stock": item.in_stock if item else 0,
                "total_stock_received": 0,
            }
        product_breakdown[pid]["qty_sold"] += s.qty_sold
        product_breakdown[pid]["total_revenue"] += float(s.total_price)
        product_breakdown[pid]["profit"] += float(s.profit) if s.profit else 0.0
        product_breakdown[pid]["transactions"] += 1

    # Revenue share
    for p_data in product_breakdown.values():
        p_data["revenue_share"] = round(p_data["total_revenue"] / total_revenue * 100, 1) if total_revenue else 0.0

    # ── Stock-in in period ─────────────────────────────────────────────────────
    stq = db.query(StockHistory).filter(
        StockHistory.deleted == False,
        # StockHistory.is_reversal == False,
        StockHistory.date_in >= s_dt,
        StockHistory.date_in < e_dt,
    )
    if item_id:
        stq = stq.filter(StockHistory.item_id == item_id)
    if category_item_ids is not None:
        stq = stq.filter(StockHistory.item_id.in_(category_item_ids))
    if organization_id:
        stq = stq.filter(StockHistory.organization_id == organization_id) 
    stq = apply_scope(stq, StockHistory, scope)
    stock_rows = stq.all()
    total_stock_in = sum(s.quantity_in for s in stock_rows)

    # Populate stock received into product breakdown
    for sh in stock_rows:
        pid = str(sh.item_id)
        if pid in product_breakdown:
            product_breakdown[pid]["total_stock_received"] += sh.quantity_in

    # ── Current inventory ──────────────────────────────────────────────────────
    iq = db.query(Items).filter(Items.deleted == False)
    if item_id:
        iq = iq.filter(Items.id == item_id)
    if category_item_ids is not None:
        iq = iq.filter(Items.id.in_(category_item_ids))
    if dept:
        iq = iq.filter(Items.dept == dept)
    if organization_id:
        iq = iq.filter(Items.organization_id == organization_id) 
    iq = apply_scope(iq, Items, scope)
    inventory_items = iq.all()
    total_current_stock = sum(i.in_stock for i in inventory_items)
    inventory_value_cost = sum((float(i.c_price) if i.c_price else 0) * i.in_stock for i in inventory_items)
    inventory_value_retail = sum(float(i.s_price) * i.in_stock for i in inventory_items)

    # ── Expenses ───────────────────────────────────────────────────────────────
    expenses_rows = []
    total_expenses = 0.0
    # Expenses are not tied to a category, so a category view reports product figures only.
    if include_expenses and category_item_ids is None:
        eq = db.query(Expenses).filter(
            Expenses.deleted == False,
            Expenses.created_at >= s_dt,
            Expenses.created_at < e_dt,
        )
        if dept:
            eq = eq.filter(Expenses.dept == dept)
        if organization_id:
            eq = eq.filter(Expenses.organization_id == organization_id)
        eq = apply_scope(eq, Expenses, scope)
        expenses_rows = eq.all()
        total_expenses = sum(float(e.cost) for e in expenses_rows)

    net_profit = total_profit - total_expenses

    return {
        "period": p,
        "start": s_dt.isoformat(),
        "end": e_dt.isoformat(),
        "include_expenses": include_expenses and category_item_ids is None,
        "expenses_excluded_by_category": category_item_ids is not None,
        "scope": scope.describe() if scope else {"branch_id": None, "department_id": None, "collective": True},
        "summary": {
            "total_revenue": total_revenue,
            "total_units_sold": total_units_sold,
            "gross_profit": total_profit,
            "total_expenses": total_expenses,
            "net_profit": net_profit,
            "total_stock_in": total_stock_in,
            "total_current_stock": total_current_stock,
            "inventory_value_cost": inventory_value_cost,
            "inventory_value_retail": inventory_value_retail,
            "total_transactions": len(sales_rows),
        },
        "products": list(product_breakdown.values()),
        "sales": [s.get_summary() for s in sales_rows[:100]],
        "sales_count": len(sales_rows),
        "stock_entries": len(stock_rows),
        "expenses": [e.get_summary() for e in expenses_rows],
    }


def get_product_detail_report_0(
    db: Session, item_id,
    period: str = "monthly",
    year: int = None, month: int = None,
    start: str = None, end: str = None,
    organization_id: str = None,
):
    """Detailed report for a single product within a date range."""
    from app.services.inventory_service import get_item
    item = get_item(db, item_id)
    if not item:
        return None

    p = "custom" if (start and end) else period
    s_dt, e_dt = _date_range(p, year=year, month=month, start=start, end=end)

    # Sales for this item in period (including void for audit)
    sales = db.query(Sales).filter(
        Sales.item_id == item_id,
        Sales.deleted == False,
        Sales.sale_date >= s_dt,
        Sales.sale_date < e_dt,
        Sales.organization_id == organization_id if organization_id else True,
    ).order_by(desc(Sales.sale_date)).all()

    non_void_sales = [s for s in sales if not s.is_void]
    qty_sold = sum(s.qty_sold for s in non_void_sales)
    total_revenue = sum(float(s.total_price) for s in non_void_sales)
    total_profit = sum(float(s.profit) for s in non_void_sales if s.profit)
    avg_price = total_revenue / qty_sold if qty_sold else 0.0

    # Stock history for this item in period
    stock_history = db.query(StockHistory).filter(
        StockHistory.item_id == item_id,
        StockHistory.deleted == False,
        StockHistory.date_in >= s_dt,
        StockHistory.date_in < e_dt,
    ).order_by(desc(StockHistory.date_in)).all()
    total_stock_in = sum(h.quantity_in for h in stock_history if not h.is_reversal)

    return {
        "item": item.get_summary(),
        "period": p,
        "start": s_dt.isoformat(),
        "end": e_dt.isoformat(),
        "summary": {
            "qty_sold": qty_sold,
            "total_revenue": total_revenue,
            "profit": total_profit,
            "total_stock_in": total_stock_in,
            "current_stock": item.in_stock,
            "transactions": len(non_void_sales),
            "avg_unit_price": avg_price,
        },
        "sales": [s.get_summary() for s in sales],
        "stock_history": [h.get_summary() for h in stock_history],
    }


# v2
def get_product_detail_report(
    db: Session, item_id,
    period: str = "monthly",
    year: int = None, month: int = None,
    start: str = None, end: str = None,
    organization_id: str = None,
    scope: Optional[ScopeFilter] = None,
):
    from app.services.inventory_service import get_item
    item = get_item(db, item_id, organization_id=organization_id, scope=scope)
    if not item:
        return None

    p = "custom" if (start and end) else period
    s_dt, e_dt = _date_range(p, year=year, month=month, start=start, end=end)

    sales = db.query(Sales).filter(
        Sales.item_id == item_id,
        Sales.deleted == False,
        Sales.sale_date >= s_dt,
        Sales.sale_date < e_dt,
        Sales.organization_id == organization_id if organization_id else True,
    ).order_by(desc(Sales.sale_date)).all()

    # Defensive: Sales model may not have is_void
    non_void_sales = [s for s in sales if not getattr(s, 'is_void', False)]
    qty_sold = sum(s.qty_sold for s in non_void_sales)
    total_revenue = sum(float(s.total_price or 0) for s in non_void_sales)
    total_profit = sum(float(s.profit or 0) for s in non_void_sales if s.profit)
    avg_price = total_revenue / qty_sold if qty_sold else 0.0

    stock_history = db.query(StockHistory).filter(
        StockHistory.item_id == item_id,
        StockHistory.deleted == False,
        StockHistory.date_in >= s_dt,
        StockHistory.date_in < e_dt,
        StockHistory.organization_id == organization_id if organization_id else True,
    ).order_by(desc(StockHistory.date_in)).all()
    total_stock_in = sum(h.quantity_in for h in stock_history if not getattr(h, 'is_reversal', False))

    return {
        "item": item.get_summary(),
        "period": p,
        "start": s_dt.isoformat(),
        "end": e_dt.isoformat(),
        "summary": {
            "qty_sold": qty_sold,
            "total_revenue": total_revenue,
            "profit": total_profit,
            "total_stock_in": total_stock_in,
            "current_stock": item.in_stock,
            "transactions": len(non_void_sales),
            "avg_unit_price": avg_price,
            "organization_id": organization_id,
        },
        "sales": [s.get_summary() for s in sales],
        "stock_history": [h.get_summary() for h in stock_history],
    }



# ─── Branch / department comparison ──────────────────────────────────────────

def get_breakdown_report(
    db: Session,
    organization_id,
    scope: Optional[ScopeFilter] = None,
    group_by: str = "branch",
    period: str = "monthly",
    year: int = None,
    month: int = None,
    start: str = None,
    end: str = None,
    branch_ids: Optional[list] = None,
):
    """
    Side-by-side figures per branch (``group_by='branch'``) or per department
    (``group_by='department'``), plus a collective total row.

    Sales / expenses / stock-in are limited to the period; inventory value is a
    point-in-time snapshot. Every figure respects ``scope`` so branch members
    only ever see their own units.
    """
    p = "custom" if (start and end) else period
    s_dt, e_dt = _date_range(p, year=year, month=month, start=start, end=end)

    if group_by == "department":
        key = lambda M: M.department_id  # noqa: E731
        label_rows = db.query(Department.id, Department.name, Branch.name, Department.branch_id).join(
            Branch, Branch.id == Department.branch_id
        ).filter(Department.organization_id == organization_id, Department.deleted == False)  # noqa: E712
        if scope and scope.branch_id:
            label_rows = label_rows.filter(Department.branch_id == scope.branch_id)
        labels = {r[0]: {"name": r[1], "branch_name": r[2], "branch_id": str(r[3])} for r in label_rows.all()}
        dept_branch = {r[0]: r[3] for r in label_rows.all()}
    else:
        group_by = "branch"
        key = lambda M: M.branch_id  # noqa: E731
        label_rows = db.query(Branch.id, Branch.name, Branch.code, Branch.is_active).filter(
            Branch.organization_id == organization_id, Branch.deleted == False  # noqa: E712
        )
        labels = {r[0]: {"name": r[1], "code": r[2], "is_active": r[3]} for r in label_rows.all()}

    def _q(model, *cols):
        q = db.query(key(model), *cols).filter(model.organization_id == organization_id, model.deleted == False)  # noqa: E712
        q = apply_scope(q, model, scope)
        return q

    sales = {
        r[0]: r for r in _q(
            Sales, func.coalesce(func.sum(Sales.total_price), 0), func.coalesce(func.sum(Sales.profit), 0),
            func.coalesce(func.sum(Sales.qty_sold), 0), func.count(Sales.id),
        ).filter(Sales.sale_date >= s_dt, Sales.sale_date < e_dt).group_by(key(Sales)).all()
    }
    expenses = {
        r[0]: r for r in _q(Expenses, func.coalesce(func.sum(Expenses.cost), 0))
        .filter(Expenses.created_at >= s_dt, Expenses.created_at < e_dt).group_by(key(Expenses)).all()
    }
    stock_in = {
        r[0]: r for r in _q(StockHistory, func.coalesce(func.sum(StockHistory.quantity_in), 0))
        .filter(StockHistory.date_in >= s_dt, StockHistory.date_in < e_dt,
                StockHistory.is_reversal == False).group_by(key(StockHistory)).all()  # noqa: E712
    }
    inventory = {
        r[0]: r for r in _q(
            Items, func.count(Items.id), func.coalesce(func.sum(Items.in_stock), 0),
            func.coalesce(func.sum(func.coalesce(Items.c_price, 0) * Items.in_stock), 0),
            func.coalesce(func.sum(Items.s_price * Items.in_stock), 0),
        ).group_by(key(Items)).all()
    }

    ids = set(sales) | set(expenses) | set(stock_in) | set(inventory)
    # include every visible branch/department even if it had no activity
    if scope is None or scope.grants is None:
        ids |= set(labels)
    else:
        allowed_b = {g[0] for g in scope.grants}
        if group_by == "branch":
            ids |= {lid for lid in labels if lid in allowed_b}
        else:
            for lid in labels:
                for gb, gd in scope.grants:
                    if dept_branch.get(lid) == gb and gd in (None, lid):
                        ids.add(lid)
    if scope is not None and scope.branch_id and group_by == "branch":
        ids = {i for i in ids if i == scope.branch_id}

    rows, tot = [], {
        "total_revenue": 0.0, "gross_profit": 0.0, "total_expenses": 0.0, "net_profit": 0.0,
        "units_sold": 0, "transactions": 0, "stock_in": 0, "products": 0, "current_stock": 0,
        "inventory_value_cost": 0.0, "inventory_value_retail": 0.0,
    }
    for gid in ids:
        sr, er, tr, ir = sales.get(gid), expenses.get(gid), stock_in.get(gid), inventory.get(gid)
        revenue = float(sr[1]) if sr else 0.0
        profit = float(sr[2]) if sr else 0.0
        exp = float(er[1]) if er else 0.0
        meta = labels.get(gid, {"name": "No department" if group_by == "department" else "Unassigned"})
        row = {
            "id": str(gid) if gid else None,
            **meta,
            "total_revenue": revenue,
            "gross_profit": profit,
            "total_expenses": exp,
            "net_profit": profit - exp,
            "units_sold": int(sr[3]) if sr else 0,
            "transactions": int(sr[4]) if sr else 0,
            "stock_in": int(tr[1]) if tr else 0,
            "products": int(ir[1]) if ir else 0,
            "current_stock": int(ir[2]) if ir else 0,
            "inventory_value_cost": float(ir[3]) if ir else 0.0,
            "inventory_value_retail": float(ir[4]) if ir else 0.0,
        }
        rows.append(row)
        for k in tot:
            tot[k] += row[k]
    rows.sort(key=lambda r: r["total_revenue"], reverse=True)
    for r in rows:
        r["revenue_share"] = round(r["total_revenue"] / tot["total_revenue"] * 100, 1) if tot["total_revenue"] else 0.0

    return {
        "group_by": group_by,
        "period": p,
        "start": s_dt.isoformat(),
        "end": e_dt.isoformat(),
        "rows": rows,
        "totals": tot,
    }
