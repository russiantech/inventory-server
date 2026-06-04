# app/api/v1/items.py
import logging
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps.users import get_db, get_current_user
from app.api.deps.rbac import require_roles
from app.models.user import User
from app.schemas.inventory import ItemCreate, ItemUpdate
from app.services import inventory_service
from app.utils.responses import api_response, PageSerializer

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", summary="List all inventory items")
async def list_items(
    request: Request,
    dept: str = None,
    category_id: str = None,
    search: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = inventory_service.get_items(db, dept=dept, category_id=category_id, search=search)
    return PageSerializer(request, obj=items, resource_name="items").get_response("Items fetched.")


@router.post("/", summary="Create a new product [manager/admin]", status_code=201)
async def create_item(
    data: ItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "super_admin", "manager")),
):
    payload = data.model_dump()
    item = inventory_service.create_item(db, data=payload, user_id=current_user.id)
    return api_response(True, f"Item '{item.name}' created.", data=item.get_summary(), status_code=201)


@router.get("/{item_id}", summary="Get item details")
async def get_item(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = inventory_service.get_item(db, item_id)
    if not item:
        return api_response(False, "Item not found.", status_code=404)

    summary = item.get_summary()
    # Attach stock history
    history = inventory_service.get_stock_history(db, item_id=item.id)
    summary["stock_history"] = [h.get_summary() for h in history]
    summary["sales_history"] = [s.get_summary() for s in inventory_service.get_sales(db, item_id=item.id)]
    return api_response(True, "Item fetched.", data=summary)


@router.put("/{item_id}", summary="Update item [manager/admin]")
async def update_item(
    item_id: str,
    data: ItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "super_admin", "manager")),
):
    item = inventory_service.get_item(db, item_id)
    if not item:
        return api_response(False, "Item not found.", status_code=404)

    item = inventory_service.update_item(db, item, data.model_dump(exclude_unset=True))
    return api_response(True, "Item updated.", data=item.get_summary())


@router.delete("/{item_id}", summary="Delete item [admin only]")
async def delete_item(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "super_admin")),
):
    item = inventory_service.get_item(db, item_id)
    if not item:
        return api_response(False, "Item not found.", status_code=404)

    inventory_service.delete_item(db, item)
    return api_response(True, f"Item '{item.name}' deleted.")
