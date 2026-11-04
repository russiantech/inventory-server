# app/services/inventory_service.py
import logging
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.models.items import Items
from app.models.stock_history import StockHistory
from app.models.stock_edit_log import StockEditLog
from app.models.sales import Sales
from app.models.expenses import Expenses
from app.models.category import Category
from app.models.branch import Department
from app.services.scope_service import ScopeFilter, apply_scope

logger = logging.getLogger(__name__)


def _get_department(db: Session, department_id, branch_id, organization_id) -> Optional[Department]:
    """Fetch a department and verify it belongs to the given branch/org."""
    if not department_id:
        return None
    dept = db.query(Department).filter(
        Department.id == department_id, Department.deleted == False,  # noqa: E712
    ).first()
    if not dept or str(dept.organization_id) != str(organization_id) or str(dept.branch_id) != str(branch_id):
        raise ValueError("Department does not belong to this branch.")
    return dept


def _validate_category_for_branch(db: Session, category_id, branch_id, organization_id) -> Category:
    cat = get_category(db, str(category_id), organization_id=organization_id)
    if not cat:
        raise ValueError("Category not found.")
    if cat.branch_id is not None and str(cat.branch_id) != str(branch_id):
        raise ValueError("This category belongs to a different branch.")
    return cat


# ─── Categories ──────────────────────────────────────────────────────────────

def get_categories(db: Session, dept: str = None, organization_id: str = None, scope: Optional[ScopeFilter] = None) -> List[Category]:
    q = apply_scope(db.query(Category).filter(Category.deleted == False), Category, scope)
    if dept:
        q = q.filter(Category.dept == dept)
    if organization_id:
        q = q.filter(Category.organization_id == organization_id)
    return q.order_by(Category.name).all()


def get_category(db: Session, category_id: str, organization_id: str = None, scope: Optional[ScopeFilter] = None) -> Optional[Category]:
    q = apply_scope(db.query(Category).filter(Category.id == category_id, Category.deleted == False), Category, scope)
    if organization_id:
        q = q.filter(Category.organization_id == organization_id)
    return q.first()


def create_category(
    db: Session,
    data,
    user_id=None,
    organization_id: str = None,
    branch_id=None,
    department_id=None,
) -> Category:
    name = (data.name or "").strip()

    if not name:
        raise ValueError("Category name is required")

    dept_row = _get_department(db, department_id, branch_id, organization_id)

    if data.parent_id:
        parent = get_category(db, str(data.parent_id), organization_id=organization_id)
        if not parent or (branch_id and parent.branch_id and str(parent.branch_id) != str(branch_id)):
            raise ValueError("Parent category must belong to the same branch.")

    cat = Category(
        name=name,
        dept=dept_row.name if dept_row else (data.dept or "general"),
        branch_id=branch_id,
        department_id=department_id,
        desc=data.desc,
        parent_id=data.parent_id,
        user_id=user_id,
        organization_id=organization_id,
    )

    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


# def update_category(db: Session, cat: Category, data: dict) -> Category:
#     for k, v in data.items():
#         if not hasattr(cat, k):
#             continue
#         # Allow explicit null for parent_id (root-level category)
#         if k == "parent_id":
#             setattr(cat, k, v)
#         elif v is not None:
#             setattr(cat, k, v)

#     db.commit()
#     db.refresh(cat)
#     return cat


def update_category(
    db: Session,
    cat: Category,
    data: dict,
    organization_id=None,
) -> Category:

    # Validate organization ownership
    if (
        organization_id is not None
        and str(cat.organization_id) != str(organization_id)
    ):
        raise ValueError("Category does not belong to this organization.")

    allowed_fields = {"name", "desc", "dept", "parent_id", "department_id"}

    if data.get("department_id"):
        dept_row = _get_department(db, data["department_id"], cat.branch_id, cat.organization_id)
        cat.department_id = dept_row.id
        cat.dept = dept_row.name
        data = {k: v for k, v in data.items() if k not in ("department_id", "dept")}
    if data.get("parent_id"):
        parent = get_category(db, str(data["parent_id"]), organization_id=cat.organization_id)
        if not parent or (cat.branch_id and parent.branch_id and str(parent.branch_id) != str(cat.branch_id)):
            raise ValueError("Parent category must belong to the same branch.")

    for k, v in data.items():
        if k not in allowed_fields or k == "department_id":
            continue

        if k == "parent_id":
            setattr(cat, k, v)
        elif v is not None:
            setattr(cat, k, v)

    db.commit()
    db.refresh(cat)

    return cat


def delete_category(db: Session, cat: Category, organization_id: str = None) -> None:
    if organization_id and str(cat.organization_id) != str(organization_id):
        raise ValueError("Category does not belong to the organization")
    cat.deleted = True
    db.commit()


# ─── Items ───────────────────────────────────────────────────────────────────

def get_items(db: Session, dept: str = None, category_id=None, search: str = None, organization_id: str = None, scope: Optional[ScopeFilter] = None) -> List[Items]:
    q = apply_scope(db.query(Items).filter(Items.deleted == False), Items, scope)
    if dept:
        q = q.filter(Items.dept == dept)
    if category_id:
        q = q.filter(Items.category_id == category_id)
    if organization_id:
        q = q.filter(Items.organization_id == organization_id)
    if search:
        q = q.filter(Items.name.ilike(f"%{search}%"))
    return q.order_by(Items.name).all()


def get_item(db: Session, item_id: str, organization_id: str = None, scope: Optional[ScopeFilter] = None) -> Optional[Items]:
    q = apply_scope(db.query(Items).filter(Items.id == item_id, Items.deleted == False), Items, scope)
    if organization_id:
        q = q.filter(Items.organization_id == organization_id)
    return q.first()


def create_item(db: Session, data: dict, user_id=None, organization_id: str = None, branch_id=None, department_id=None) -> Items:
    initial = data.pop("initial_stock", data.pop("in_stock", 0)) or 0

    # Allowed fields only (STRICT) — prevents unexpected/unknown keys from
    # reaching the Items() constructor
    allowed_fields = {
        "name", "sku", "desc", "dept", "category_id",
        "c_price", "s_price", "disc", "attributes", "photos", "status",
    }
    clean_data = {k: v for k, v in data.items() if k in allowed_fields}

    # ── Branch / department integrity ──
    if clean_data.get("category_id"):
        cat = _validate_category_for_branch(db, clean_data["category_id"], branch_id, organization_id)
        # inherit the category's department when none was chosen
        if department_id is None and cat.department_id:
            department_id = cat.department_id
    if department_id is None:
        active = db.query(Department).filter(
            Department.branch_id == branch_id, Department.deleted == False,  # noqa: E712
            Department.is_active == True,  # noqa: E712
        ).all()
        if len(active) == 1:
            department_id = active[0].id
        elif len(active) > 1:
            raise ValueError("Please choose a department.")
    dept_row = _get_department(db, department_id, branch_id, organization_id)
    if dept_row:
        clean_data["dept"] = dept_row.name

    item = Items(
        **clean_data,
        initial_stock=initial,
        in_stock=initial,
        user_id=user_id,
        organization_id=organization_id,
        branch_id=branch_id,
        department_id=department_id,
    )
    db.add(item)
    db.flush()

    if initial > 0:
        entry = StockHistory(
            item_id=item.id,
            user_id=user_id,
            quantity_in=initial,
            stock_before=0,
            stock_after=initial,
            desc="Initial stock entry",
            organization_id=organization_id,
            branch_id=branch_id,
            department_id=department_id,
        )
        db.add(entry)

    db.commit()
    db.refresh(item)
    return item

def update_item(
    db: Session,
    item: Items,
    data: dict,
    organization_id: str = None,
) -> Items:
    """Update an item while enforcing organization ownership."""

    if (
        organization_id is not None
        and str(item.organization_id) != str(organization_id)
    ):
        raise ValueError("Item does not belong to this organization.")

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
    }

    # branch_id is deliberately NOT updatable: an item's stock ledger lives in its branch.
    if data.get("category_id"):
        _validate_category_for_branch(db, data["category_id"], item.branch_id, item.organization_id)
    if data.get("department_id"):
        dept_row = _get_department(db, data["department_id"], item.branch_id, item.organization_id)
        item.department_id = dept_row.id
        item.dept = dept_row.name
        # keep the item's ledgers on the same department
        db.query(Sales).filter(Sales.item_id == item.id).update({Sales.department_id: dept_row.id, Sales.dept: dept_row.name}, synchronize_session=False)
        db.query(StockHistory).filter(StockHistory.item_id == item.id).update({StockHistory.department_id: dept_row.id}, synchronize_session=False)
        data = {k: v for k, v in data.items() if k != "dept"}

    for key, value in data.items():
        if key not in allowed_fields:
            continue

        # Avoid overwriting existing values with None.
        # If your schema allows intentionally clearing fields,
        # handle those fields separately.
        if value is not None:
            setattr(item, key, value)

    db.commit()
    db.refresh(item)

    return item

def delete_item(
    db: Session,
    item: Items,
    organization_id: str,
    user_id,
    user_roles: List[str],
    reason: str,
) -> Items:
    if str(item.organization_id) != str(organization_id):
        raise ValueError("Item does not belong to the organization")
    if not reason or not reason.strip():
        raise ValueError("A reason is required to delete a product")

    is_privileged = any(r in ("admin", "super_admin") for r in user_roles)

    if not is_privileged:
        if item.in_stock != 0:
            raise ValueError(
                "This product still has stock on hand. Reduce stock to zero "
                "(via a manager-approved adjustment) before deleting, or ask "
                "a manager/admin to delete it."
            )
        has_sales = (
            db.query(Sales)
            .filter(Sales.item_id == item.id, Sales.deleted == False)
            .first()
        )
        if has_sales:
            raise ValueError(
                "This product has recorded sales and cannot be deleted by staff. "
                "Ask a manager or admin if it needs to be removed."
            )

    item.deleted = True
    item.deleted_by = user_id
    item.deleted_at = func.now()
    item.delete_reason = reason.strip()
    db.commit()
    db.refresh(item)
    return item


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
        branch_id=item.branch_id,
        department_id=item.department_id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    db.refresh(item)
    return entry


def get_stock_history(db: Session, item_id=None, organization_id: str = None, scope: Optional[ScopeFilter] = None) -> List[StockHistory]:
    """Full (unbounded) history list. Used by item_stock_history for the
    'total_received' sum, and by /history via PageSerializer."""
    q = apply_scope(db.query(StockHistory).filter(StockHistory.deleted == False), StockHistory, scope)
    if item_id:
        q = q.filter(StockHistory.item_id == item_id)
    if organization_id:
        q = q.filter(StockHistory.organization_id == organization_id)
    return q.order_by(desc(StockHistory.date_in)).all()


def update_stock_entry(
    db: Session,
    stock_id,
    organization_id: str,
    quantity_in: int,
    edit_reason: str,
    unit_cost: float = None,
    desc: str = None,
    reference: str = None,
    user_id=None,
    scope: Optional[ScopeFilter] = None,
) -> Optional[StockHistory]:
    entry = (
        apply_scope(db.query(StockHistory), StockHistory, scope)
        .filter(
            StockHistory.id == stock_id,
            StockHistory.organization_id == organization_id,
            StockHistory.deleted == False,
        )
        .first()
    )
    if not entry:
        return None
    if entry.is_reversal:
        raise ValueError("Cannot edit a reversal record")
    if entry.is_reversed:
        raise ValueError("Cannot edit an entry that has already been reversed")
    if quantity_in <= 0:
        raise ValueError("Quantity must be greater than zero")
    if not edit_reason or not edit_reason.strip():
        raise ValueError("A reason is required to edit a stock entry")

    item = get_item(db, entry.item_id, organization_id=organization_id)
    if not item:
        raise ValueError("Associated item not found")

    old_values = {
        "quantity_in": entry.quantity_in,
        "unit_cost": float(entry.unit_cost) if entry.unit_cost else None,
        "desc": entry.desc,
        "reference": entry.reference,
        "stock_after": entry.stock_after,
    }
    delta = quantity_in - entry.quantity_in

    if delta != 0:
        if item.in_stock + delta < 0:
            raise ValueError("Edit would drop stock below zero")

        # Cascade-adjust every later entry for this item so the ledger
        # stays consistent with item.in_stock
        later_entries = (
            db.query(StockHistory)
            .filter(
                StockHistory.item_id == entry.item_id,
                StockHistory.deleted == False,
                StockHistory.date_in > entry.date_in,
            )
            .order_by(StockHistory.date_in.asc())
            .all()
        )
        for later in later_entries:
            later.stock_before += delta
            later.stock_after += delta

        item.in_stock += delta

    entry.quantity_in = quantity_in
    entry.stock_after = entry.stock_before + quantity_in
    if unit_cost is not None:
        entry.unit_cost = unit_cost
    if desc is not None:
        entry.desc = desc
    if reference is not None:
        entry.reference = reference
    entry.edit_count += 1

    audit = StockEditLog(
        stock_entry_id=entry.id,
        item_id=entry.item_id,
        user_id=user_id,
        organization_id=organization_id,
        old_quantity_in=old_values["quantity_in"],
        new_quantity_in=quantity_in,
        quantity_delta=delta,
        old_unit_cost=old_values["unit_cost"],
        new_unit_cost=unit_cost if unit_cost is not None else old_values["unit_cost"],
        old_desc=old_values["desc"],
        new_desc=desc if desc is not None else old_values["desc"],
        old_reference=old_values["reference"],
        new_reference=reference if reference is not None else old_values["reference"],
        old_stock_after=old_values["stock_after"],
        new_stock_after=entry.stock_after,
        edit_reason=edit_reason.strip(),
    )
    db.add(audit)

    db.commit()
    db.refresh(entry)
    db.refresh(item)
    return entry


def get_stock_edit_logs(
    db: Session,
    stock_id,
    organization_id: str,
    page: int = 1,
    page_size: int = 20,
    scope: Optional[ScopeFilter] = None,
):
    """DB-level paginated, most-recent-first edit history for one stock entry."""
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)

    base_q = db.query(StockEditLog).filter(
        StockEditLog.stock_entry_id == stock_id,
        StockEditLog.organization_id == organization_id,
    )
    if scope is not None:
        # edit logs inherit the branch of their stock entry
        visible = apply_scope(db.query(StockHistory.id), StockHistory, scope).subquery()
        base_q = base_q.filter(StockEditLog.stock_entry_id.in_(visible))
    total = base_q.count()
    logs = (
        base_q
        .order_by(desc(StockEditLog.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return logs, total, page, page_size


def reverse_stock_entry(
    db: Session,
    stock_id,
    organization_id: str,
    reason: str,
    user_id=None,
    scope: Optional[ScopeFilter] = None,
) -> Optional[StockHistory]:
    entry = (
        apply_scope(db.query(StockHistory), StockHistory, scope)
        .filter(
            StockHistory.id == stock_id,
            StockHistory.organization_id == organization_id,
            StockHistory.deleted == False,
        )
        .first()
    )
    if not entry:
        return None
    if entry.is_reversal:
        raise ValueError("Cannot reverse a reversal record")
    if entry.is_reversed:
        raise ValueError("This entry has already been reversed")
    if not reason or not reason.strip():
        raise ValueError("A reason is required to reverse a stock entry")

    item = get_item(db, entry.item_id, organization_id=organization_id)
    if not item:
        raise ValueError("Associated item not found")
    if item.in_stock < entry.quantity_in:
        raise ValueError(
            f"Cannot reverse: current stock ({item.in_stock}) is lower than the "
            f"quantity being reversed ({entry.quantity_in}). Some of it may already be sold."
        )

    stock_before = item.in_stock
    stock_after = stock_before - entry.quantity_in
    item.in_stock = stock_after

    reversal = StockHistory(
        item_id=entry.item_id,
        user_id=user_id,
        quantity_in=entry.quantity_in,
        stock_before=stock_before,
        stock_after=stock_after,
        unit_cost=entry.unit_cost,
        desc=reason.strip(),
        reference=entry.reference,
        is_reversal=True,
        reversed_entry_id=entry.id,
        organization_id=organization_id,
        branch_id=entry.branch_id,
        department_id=entry.department_id,
    )
    entry.is_reversed = True

    db.add(reversal)
    db.commit()
    db.refresh(reversal)
    db.refresh(item)
    return reversal


# ─── Sales ───────────────────────────────────────────────────────────────────

def get_sales(db: Session, item_id=None, dept: str = None, user_id=None, organization_id: str = None, scope: Optional[ScopeFilter] = None) -> List[Sales]:
    q = apply_scope(db.query(Sales).filter(Sales.deleted == False), Sales, scope)
    if item_id:
        q = q.filter(Sales.item_id == item_id)
    if dept:
        q = q.filter(Sales.dept == dept)
    if user_id:
        q = q.filter(Sales.user_id == user_id)
    if organization_id:
        q = q.filter(Sales.organization_id == organization_id)
    return q.order_by(desc(Sales.sale_date)).all()


# def get_sale(db: Session, sale_id) -> Optional[Sales]:
#     return db.query(Sales).filter(Sales.id == sale_id, Sales.deleted == False).first()

def get_sale(
    db: Session,
    sale_id,
    organization_id: str = None,
    scope: Optional[ScopeFilter] = None,
) -> Optional[Sales]:
    q = apply_scope(db.query(Sales), Sales, scope).filter(
        Sales.id == sale_id,
        Sales.deleted == False,
    )

    if organization_id is not None:
        q = q.filter(Sales.organization_id == organization_id)

    return q.first()

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
        # Branch/department always come from the item (never from the client)
        dept=item.dept if item.department_id else (dept or item.dept),
        comment=comment,
        organization_id=organization_id,
        branch_id=item.branch_id,
        department_id=item.department_id,
    )
    db.add(sale)
    db.commit()
    db.refresh(sale)
    db.refresh(item)
    return sale


# def void_sale(db: Session, sale: Sales) -> None:
#     """Soft-delete a sale and restore the stock."""
#     item = get_item(db, sale.item_id, organization_id=sale.organization_id)
#     if item:
#         item.in_stock += sale.qty_sold
#     sale.deleted = True
#     db.commit()

# update void_sale to enforce organization ownership and raise ValueError if the sale does not belong to the organization.
def void_sale(
    db: Session,
    sale: Sales,
    organization_id: str = None,
) -> None:
    if (
        organization_id is not None
        and str(sale.organization_id) != str(organization_id)
    ):
        raise ValueError("Sale does not belong to this organization.")

    item = get_item(
        db,
        sale.item_id,
        organization_id=organization_id or sale.organization_id,
    )

    if item:
        item.in_stock += sale.qty_sold

    sale.deleted = True
    db.commit()


# ─── Expenses ────────────────────────────────────────────────────────────────

def get_expenses(db: Session, dept: str = None, organization_id: str = None, scope: Optional[ScopeFilter] = None) -> List[Expenses]:
    q = apply_scope(db.query(Expenses).filter(Expenses.deleted == False), Expenses, scope)
    if dept:
        q = q.filter(Expenses.dept == dept)
    if organization_id:
        q = q.filter(Expenses.organization_id == organization_id)
    return q.order_by(desc(Expenses.created_at)).all()


def create_expense(db: Session, cost: float, dept: str = "general", comment: str = None, user_id=None, organization_id: str = None, branch_id=None, department_id=None) -> Expenses:
    dept_row = _get_department(db, department_id, branch_id, organization_id)
    exp = Expenses(
        cost=cost, dept=dept_row.name if dept_row else dept, comment=comment, user_id=user_id,
        organization_id=organization_id, branch_id=branch_id, department_id=department_id,
    )
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

