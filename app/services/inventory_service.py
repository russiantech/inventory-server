# app/services/inventory_service.py
import logging
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.items import Items
from app.models.stock_history import StockHistory
from app.models.sales import Sales
from app.models.expenses import Expenses
from app.models.category import Category

logger = logging.getLogger(__name__)


# ─── Categories ──────────────────────────────────────────────────────────────

def get_categories(db: Session, dept: str = None, organization_id: str = None) -> List[Category]:
    q = db.query(Category).filter(Category.deleted == False)
    if dept:
        q = q.filter(Category.dept == dept)
    if organization_id:
        q = q.filter(Category.organization_id == organization_id)
    return q.order_by(Category.name).all()


def get_category(db: Session, category_id: str, organization_id: str = None) -> Optional[Category]:
    q = db.query(Category).filter(Category.id == category_id, Category.deleted == False)
    if organization_id:
        q = q.filter(Category.organization_id == organization_id)
    return q.first()


# def create_category(db: Session, name: str, dept: str = "general", desc: str = None, parent_id=None, user_id=None) -> Category:
#     cat = Category(name=name.strip(), dept=dept, desc=desc, parent_id=parent_id, user_id=user_id)
#     db.add(cat)
#     db.commit()
#     db.refresh(cat)
#     return cat

def create_category(
    db: Session,
    data,
    user_id=None,
    organization_id: str = None,
) -> Category:
    name = (data.name or "").strip()

    if not name:
        raise ValueError("Category name is required")

    cat = Category(
        name=name,
        dept=data.dept or "general",
        desc=data.desc,
        parent_id=data.parent_id,
        user_id=user_id,
        organization_id=organization_id,
    )

    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat

# def create_category(
#     db: Session,
#     data: dict,
#     user_id=None,
# ) -> Category:
#     cat = Category(
#         name=data.get("name").strip(),
#         dept=data.get("dept", "general"),
#         desc=data.get("desc"),
#         parent_id=data.get("parent_id"),
#         user_id=user_id,  # now supported
#     )
#     db.add(cat)
#     db.commit()
#     db.refresh(cat)
#     return cat

# def update_category(db: Session, cat: Category, **kwargs) -> Category:
#     for k, v in kwargs.items():
#         if hasattr(cat, k) and v is not None:
#             setattr(cat, k, v)
#     db.commit()
#     db.refresh(cat)
#     return cat

# v2
# def update_category(
#     db: Session,
#     cat: Category,
#     data,
# ) -> Category:
#     if data.name is not None:
#         name = data.name.strip()
#         if not name:
#             raise ValueError("Category name cannot be empty")
#         cat.name = name

#     if data.dept is not None:
#         cat.dept = data.dept

#     if data.desc is not None:
#         cat.desc = data.desc

#     if data.parent_id is not None:
#         cat.parent_id = data.parent_id

#     db.commit()
#     db.refresh(cat)
#     return cat

# # v3
# def update_category(
#     db: Session,
#     cat: Category,
#     data,
# ) -> Category:
#     update_data = data.model_dump(exclude_unset=True)

#     if "name" in update_data:
#         name = (update_data["name"] or "").strip()
#         if not name:
#             raise ValueError("Category name cannot be empty")
#         cat.name = name

#     if "dept" in update_data:
#         cat.dept = update_data["dept"]

#     if "desc" in update_data:
#         cat.desc = update_data["desc"]

#     # THIS FIXES YOUR ISSUE
#     if "parent_id" in update_data:
#         cat.parent_id = update_data["parent_id"]  # can be None

#     print(f"Updating category {cat.id} with data: {update_data}")  # Debug log
    
#     db.commit()
#     db.refresh(cat)
#     return cat

# v4
def update_category(db: Session, cat: Category, data: dict) -> Category:
    for k, v in data.items():
        if not hasattr(cat, k):
            continue

        # KEY FIX: allow explicit null for parent_id
        if k == "parent_id":
            setattr(cat, k, v)  # allow None
        elif v is not None:
            setattr(cat, k, v)

    print(f"Updating category {cat.id} with data: {data}")  # Debug log
    
    db.commit()
    db.refresh(cat)
    return cat


def delete_category(db: Session, cat: Category, organization_id: str = None) -> None:
    if organization_id and cat.organization_id != organization_id:
        raise ValueError("Category does not belong to the organization")
    cat.deleted = True
    db.commit()


# ─── Items ───────────────────────────────────────────────────────────────────

def get_items(db: Session, dept: str = None, category_id=None, search: str = None, organization_id: str = None) -> List[Items]:
    q = db.query(Items).filter(Items.deleted == False)
    if dept:
        q = q.filter(Items.dept == dept)
    if category_id:
        q = q.filter(Items.category_id == category_id)
    if organization_id:
        q = q.filter(Items.organization_id == organization_id)
    if search:
        q = q.filter(Items.name.ilike(f"%{search}%"))
    return q.order_by(Items.name).all()


def get_item(db: Session, item_id: str, organization_id: str = None) -> Optional[Items]:
    q = db.query(Items).filter(Items.id == item_id, Items.deleted == False)
    if organization_id:
        q = q.filter(Items.organization_id == organization_id)
    return q.first()


# def create_item(db: Session, data: dict, user_id=None) -> Items:
#     initial = data.pop("initial_stock", 0) or data.pop("in_stock", 0)
#     item = Items(**data, initial_stock=initial, in_stock=initial, user_id=user_id)
#     db.add(item)
#     db.flush()

#     # Record initial stock if > 0
#     if initial > 0:
#         entry = StockHistory(
#             item_id=item.id,
#             user_id=user_id,
#             quantity_in=initial,
#             stock_before=0,
#             stock_after=initial,
#             desc="Initial stock entry",
#         )
#         db.add(entry)

#     db.commit()
#     db.refresh(item)
#     return item

# v2
def create_item(db: Session, data: dict, user_id=None, organization_id: str = None) -> Items:
    # Extract stock safely
    initial = data.pop("initial_stock", data.pop("in_stock", 0)) or 0

    # print(f"Creating item with data: {data}, initial_stock: {initial}, organization_id: {organization_id}")  # Debug log
    print(f"Initial: {initial}")
    print(f"Organization ID: {organization_id}")
    print(f"Data: {data}")
    
    # ✅ Allowed fields only (STRICT)
    allowed_fields = {
        "name",
        "sku",              
        "desc",
        "dept",
        "category_id",
        "c_price",
        "s_price",
        "disc",
        "attributes",
        "photos",
        "status", 
        # "organization_id",  # ensure this is included
    }
    
    

    clean_data = {k: v for k, v in data.items() if k in allowed_fields}

    item = Items(
        **clean_data,
        initial_stock=initial,
        in_stock=initial,
        user_id=user_id,
        organization_id=organization_id,
    )

    db.add(item)
    db.flush()

    # Stock history
    if initial > 0:
        entry = StockHistory(
            item_id=item.id,
            user_id=user_id,
            quantity_in=initial,
            stock_before=0,
            stock_after=initial,
            desc="Initial stock entry",
            organization_id=organization_id # ensure this is set for stock history as well,
        )
        db.add(entry)

    db.commit()
    db.refresh(item)
    return item


# def update_item(db: Session, item: Items, data: dict, organization_id: str = None) -> Items:
#     if organization_id and item.organization_id != organization_id:
#         raise ValueError("Item does not belong to the organization")
#     for k, v in data.items():
#         if hasattr(item, k):
#             setattr(item, k, v)
#     db.commit()
#     db.refresh(item)
#     return item

# app/services/inventory_service.py

def update_item(db: Session, item: Items, data: dict, organization_id: str = None) -> Items:
    # FIX: compare as strings to handle UUID object vs string mismatch
    if organization_id and str(item.organization_id) != str(organization_id):
        raise ValueError("Item does not belong to the organization")
    for k, v in data.items():
        if hasattr(item, k):
            setattr(item, k, v)
    db.commit()
    db.refresh(item)
    return item

# def delete_item(db: Session, item: Items) -> None:
#     item.deleted = True
#     db.commit()
# app/services/inventory_service.py  (same fix)

def delete_category(db: Session, cat: Category, organization_id: str = None) -> None:
    if organization_id and str(cat.organization_id) != str(organization_id):
        raise ValueError("Category does not belong to the organization")
    cat.deleted = True
    db.commit()

# ─── Stock-In ────────────────────────────────────────────────────────────────

def stock_in(db: Session, item_id, quantity_in: int, user_id=None, desc: str = None, unit_cost: float = None, reference: str = None, organization_id: str = None) -> StockHistory:
    item = get_item(db, item_id, organization_id=organization_id)
    if not item:
        raise ValueError(f"Item not found: {item_id}")
    if quantity_in <= 0:
        raise ValueError("Quantity must be greater than zero")

    stock_before = item.in_stock
    stock_after = stock_before + quantity_in

    item.in_stock = stock_after

    entry = StockHistory(
        item_id=item.id,
        user_id=user_id,
        quantity_in=quantity_in,
        stock_before=stock_before,
        stock_after=stock_after,
        unit_cost=unit_cost,
        desc=desc or f"+{quantity_in} units added",
        reference=reference,
        organization_id=organization_id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    db.refresh(item)
    return entry


def get_stock_history(db: Session, item_id=None, organization_id: str = None) -> List[StockHistory]:
    q = db.query(StockHistory).filter(StockHistory.deleted == False)
    if item_id:
        q = q.filter(StockHistory.item_id == item_id)
    if organization_id:
        q = q.filter(StockHistory.organization_id == organization_id)
    return q.order_by(desc(StockHistory.date_in)).all()


# ─── Sales ───────────────────────────────────────────────────────────────────

def get_sales(db: Session, item_id=None, dept: str = None, user_id=None, organization_id: str = None) -> List[Sales]:
    q = db.query(Sales).filter(Sales.deleted == False)
    if item_id:
        q = q.filter(Sales.item_id == item_id)
    if dept:
        q = q.filter(Sales.dept == dept)
    if user_id:
        q = q.filter(Sales.user_id == user_id)
    if organization_id:
        q = q.filter(Sales.organization_id == organization_id)
    return q.order_by(desc(Sales.sale_date)).all()


def get_sale(db: Session, sale_id) -> Optional[Sales]:
    return db.query(Sales).filter(Sales.id == sale_id, Sales.deleted == False).first()


def create_sale(db: Session, item_id, qty_sold: int, unit_price: float, user_id=None, dept: str = "general", comment: str = None, organization_id: str = None) -> Sales:
    item = get_item(db, item_id, organization_id=organization_id)
    if not item:
        raise ValueError(f"Item not found: {item_id}")
    if item.in_stock < qty_sold:
        raise ValueError(f"Insufficient stock. Available: {item.in_stock}, Requested: {qty_sold}")

    stock_before = item.in_stock
    stock_after = stock_before - qty_sold
    total_price = qty_sold * unit_price
    cost_price = float(item.c_price) if item.c_price else None
    profit = (unit_price - cost_price) * qty_sold if cost_price else None

    item.in_stock = stock_after

    sale = Sales(
        item_id=item.id,
        user_id=user_id,
        qty_sold=qty_sold,
        unit_price=unit_price,
        total_price=total_price,
        cost_price=cost_price,
        profit=profit,
        stock_before=stock_before,
        stock_after=stock_after,
        dept=dept or item.dept,
        comment=comment,
        organization_id=organization_id,
    )
    db.add(sale)
    db.commit()
    db.refresh(sale)
    db.refresh(item)
    return sale


def void_sale(db: Session, sale: Sales) -> None:
    """Soft-delete a sale and restore the stock."""
    item = get_item(db, sale.item_id, organization_id=sale.organization_id)
    if item:
        item.in_stock += sale.qty_sold
    sale.deleted = True
    db.commit()


# ─── Expenses ────────────────────────────────────────────────────────────────

def get_expenses(db: Session, dept: str = None, organization_id: str = None) -> List[Expenses]:
    q = db.query(Expenses).filter(Expenses.deleted == False)
    if dept:
        q = q.filter(Expenses.dept == dept)
    if organization_id:
        q = q.filter(Expenses.organization_id == organization_id)
    return q.order_by(desc(Expenses.created_at)).all()


def create_expense(db: Session, cost: float, dept: str = "general", comment: str = None, user_id=None, organization_id: str = None) -> Expenses:
    exp = Expenses(cost=cost, dept=dept, comment=comment, user_id=user_id, organization_id=organization_id)
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return exp


def delete_expense(db: Session, exp: Expenses, organization_id: str = None) -> None:
    if organization_id:
        exp = db.query(Expenses).filter(Expenses.id == exp.id, Expenses.organization_id == organization_id).first()
        if not exp:
            raise ValueError("Expense not found or does not belong to the organization")
    exp.deleted = True
    db.commit()
