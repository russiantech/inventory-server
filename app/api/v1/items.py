# app/api/v1/items.py
import logging
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps.users import _get_org_id, get_db, get_current_user
from app.api.deps.rbac import require_roles
from app.models.user import User
from app.schemas.inventory import ItemCreate, ItemDeleteSchema, ItemUpdate
from app.services import inventory_service
from app.utils.responses import api_response, PageSerializer

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", summary="List all inventory items")
async def list_items(
    request: Request,
    dept: str = None,
    category_id: str = None,
    search: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = _get_org_id(current_user)
    items = inventory_service.get_items(
        db, dept=dept, category_id=category_id, search=search, organization_id=org_id
    )
    return PageSerializer(request, obj=items, resource_name="items").get_response("Items fetched.")


@router.post("", summary="Create a new product [manager/admin]", status_code=201)
async def create_item(
    data: ItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "super_admin", "manager", "staff")),
):
    org_id = _get_org_id(current_user)
    payload = data.model_dump()
    item = inventory_service.create_item(db, data=payload, user_id=current_user.id, organization_id=org_id)
    return api_response(True, f"Item '{item.name}' created.", data=item.get_summary(), status_code=201)


@router.get("/{item_id}", summary="Get item details")
async def get_item(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = _get_org_id(current_user)
    item = inventory_service.get_item(db, item_id, organization_id=org_id)
    if not item:
        return api_response(False, "Item not found.", status_code=404)

    summary = item.get_summary()
    summary["stock_history"] = [
        h.get_summary() for h in inventory_service.get_stock_history(db, item_id=item.id)
    ]
    summary["sales_history"] = [
        s.get_summary() for s in inventory_service.get_sales(db, item_id=item.id)
    ]
    return api_response(True, "Item fetched.", data=summary)


@router.put("/{item_id}", summary="Update item [manager/admin]")
async def update_item(
    item_id: str,
    data: ItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "super_admin", "manager", "staff")),
):
    org_id = _get_org_id(current_user)
    item = inventory_service.get_item(db, item_id, organization_id=org_id)
    if not item:
        return api_response(False, "Item not found.", status_code=404)

    item = inventory_service.update_item(db, item, data.model_dump(exclude_unset=True), organization_id=org_id)
    return api_response(True, "Item updated.", data=item.get_summary())


# @router.delete("/{item_id}", summary="Delete item [admin only]")
# async def delete_item(
#     item_id: str,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(require_roles("admin", "super_admin")),
# ):
#     org_id = _get_org_id(current_user)
#     item = inventory_service.get_item(db, item_id, organization_id=org_id)
#     if not item:
#         return api_response(False, "Item not found.", status_code=404)

#     inventory_service.delete_item(db, item, organization_id=org_id)
#     return api_response(True, f"Item '{item.name}' deleted.")

# v2
@router.delete("/{item_id}", summary="Delete a product")
async def remove_item(
    item_id: str,
    data: ItemDeleteSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "super_admin", "manager", "staff")),
):
    org_id = _get_org_id(current_user)
    item = inventory_service.get_item(db, item_id, organization_id=org_id)
    if not item:
        return api_response(False, "Item not found.", status_code=404)

    try:
        inventory_service.delete_item(
            db,
            item=item,
            organization_id=org_id,
            user_id=current_user.id,
            user_roles=[r.name for r in current_user.roles],  # adjust to however roles are stored on User
            reason=data.reason,
        )
        return api_response(True, f'"{item.name}" deleted.')
    except ValueError as e:
        return api_response(False, str(e), status_code=400)