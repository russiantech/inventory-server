# app/api/v1/stock.py
import logging
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps.users import _get_org_id, get_db, get_current_user
from app.api.deps.rbac import require_roles
from app.models.user import User
from app.services import inventory_service
from app.schemas.stock import (
    StockInSchema, StockReverseSchema, 
    StockUpdateSchema
)
from app.utils.responses import api_response, PageSerializer

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/in", summary="Record new stock receipt [manager/admin]", status_code=201)
async def record_stock_in(
    data: StockInSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "super_admin", "manager", "staff")),
):
    org_id = _get_org_id(current_user)

    # Verify the item exists and belongs to this organisation
    item = inventory_service.get_item(db, data.item_id)
    if not item or str(item.organization_id) != org_id:
        return api_response(False, "Item not found.", status_code=404)

    try:
        entry = inventory_service.stock_in(
            db,
            item_id=data.item_id,
            quantity_in=data.quantity_in,
            user_id=current_user.id,
            desc=data.desc,
            unit_cost=data.unit_cost,
            reference=data.reference,
            organization_id=org_id,
        )
        return api_response(
            True,
            f"Stock received: +{data.quantity_in} units. New balance: {entry.stock_after}",
            data=entry.get_summary(),
            status_code=201,
        )
    except ValueError as e:
        return api_response(False, str(e), status_code=400)


# @router.put("/{stock_id}", summary="Edit a stock entry [staff/manager/admin]")
# async def update_stock_entry(
#     stock_id: str,
#     data: StockUpdateSchema,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(require_roles("admin", "super_admin", "manager", "staff")),
# ):
#     org_id = _get_org_id(current_user)
#     try:
#         entry = inventory_service.update_stock_entry(
#             db,
#             stock_id=stock_id,
#             organization_id=org_id,
#             quantity_in=data.quantity_in,
#             unit_cost=data.unit_cost,
#             desc=data.desc,
#             reference=data.reference,
#         )
#         if not entry:
#             return api_response(False, "Stock entry not found.", status_code=404)
#         return api_response(True, "Stock entry updated.", data=entry.get_summary())
#     except ValueError as e:
#         return api_response(False, str(e), status_code=400)

# v2
@router.put("/{stock_id}", summary="Edit a stock entry [manager/admin]")
async def update_stock_entry(
    stock_id: str,
    data: StockUpdateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "super_admin", "manager", "staff")),
):
    org_id = _get_org_id(current_user)
    try:
        entry = inventory_service.update_stock_entry(
            db,
            stock_id=stock_id,
            organization_id=org_id,
            quantity_in=data.quantity_in,
            unit_cost=data.unit_cost,
            desc=data.desc,
            reference=data.reference,
            user_id=current_user.id,  # ← NEW: pass editor
        )
        if not entry:
            return api_response(False, "Stock entry not found.", status_code=404)
        return api_response(True, "Stock entry updated.", data=entry.get_summary())
    except ValueError as e:
        return api_response(False, str(e), status_code=400)


@router.post("/{stock_id}/reverse", summary="Reverse a stock entry [manager/admin]")
async def reverse_stock_entry(
    stock_id: str,
    data: StockReverseSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "super_admin", "manager", "staff")),
):
    org_id = _get_org_id(current_user)
    try:
        reversal = inventory_service.reverse_stock_entry(
            db,
            stock_id=stock_id,
            organization_id=org_id,
            reason=data.reason,
            user_id=current_user.id,
        )
        if not reversal:
            return api_response(False, "Stock entry not found.", status_code=404)
        return api_response(True, "Stock entry reversed.", data=reversal.get_summary())
    except ValueError as e:
        return api_response(False, str(e), status_code=400)

@router.get("/history", summary="All stock-in entries")
async def list_stock_history(
    request: Request,
    item_id: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = _get_org_id(current_user)
    history = inventory_service.get_stock_history(db, item_id=item_id, organization_id=org_id)
    return PageSerializer(request, obj=history, resource_name="stock_history").get_response("Stock history fetched.")


@router.get("/history/{item_id}", summary="Stock history for a specific item")
async def item_stock_history(
    item_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = _get_org_id(current_user)
    item = inventory_service.get_item(db, item_id, organization_id=org_id)
    if not item:
        return api_response(False, "Item not found.", status_code=404)

    history = inventory_service.get_stock_history(db, item_id=item_id, organization_id=org_id)
    return api_response(
        True, f"Stock history for '{item.name}'.",
        data={
            "item": item.get_summary(),
            "history": [h.get_summary() for h in history],
            "total_received": sum(h.quantity_in for h in history),
        }
    )


@router.get("/snapshot", summary="Current stock levels for all items")
async def stock_snapshot(
    request: Request,
    dept: str = None,
    low_stock_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = _get_org_id(current_user)
    items = inventory_service.get_items(db, dept=dept, organization_id=org_id)
    if low_stock_only:
        items = [i for i in items if i.in_stock < 5]

    snapshots = []
    for item in items:
        s = item.get_summary()
        s["total_sold"] = sum(sale.qty_sold for sale in item.sales if not sale.deleted)
        snapshots.append(s)

    return api_response(True, "Stock snapshot.", data={"count": len(snapshots), "items": snapshots})


@router.get("/{stock_id}/edit-history", summary="Get edit audit trail for a stock entry")
async def stock_entry_edit_history(
    stock_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = _get_org_id(current_user)
    history = inventory_service.get_stock_entry_edit_history(db, stock_id, organization_id=org_id)
    return api_response(
        True,
        f"Edit history for stock entry {stock_id}.",
        data=[h.get_summary() for h in history],
    )