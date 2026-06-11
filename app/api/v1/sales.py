# app/api/v1/sales.py
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


class SaleCreateSchema(BaseModel):
    item_id: str
    qty_sold: int
    unit_price: float
    dept: str = "general"
    comment: Optional[str] = None
    # organization_id intentionally removed — derived server-side from the
    # authenticated user; clients must never supply it.

    @field_validator("qty_sold")
    @classmethod
    def qty_positive(cls, v):
        if v <= 0:
            raise ValueError("Quantity sold must be greater than zero")
        return v

    @field_validator("unit_price")
    @classmethod
    def price_valid(cls, v):
        if v < 0:
            raise ValueError("Unit price cannot be negative")
        return v


class SaleUpdateSchema(BaseModel):
    comment: Optional[str] = None
    # organization_id intentionally removed — derived server-side


@router.get("/", summary="List all sales")
async def list_sales(
    request: Request,
    item_id: str = None,
    dept: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = _get_org_id(current_user)
    # Staff only see their own sales; managers/admins see all
    uid = None if current_user.has_role("admin", "super_admin", "manager") else current_user.id
    sales = inventory_service.get_sales(db, item_id=item_id, dept=dept, user_id=uid, organization_id=org_id)
    return PageSerializer(request, obj=sales, resource_name="sales").get_response("Sales fetched.")


@router.post("/", summary="Record a sale", status_code=201)
async def create_sale(
    data: SaleCreateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = _get_org_id(current_user)

    # Verify the item exists and belongs to this organisation
    item = inventory_service.get_item(db, data.item_id)
    if not item or str(item.organization_id) != org_id:
        return api_response(False, "Item not found.", status_code=404)

    try:
        sale = inventory_service.create_sale(
            db,
            item_id=data.item_id,
            qty_sold=data.qty_sold,
            unit_price=data.unit_price,
            user_id=str(current_user.id),
            dept=data.dept,
            comment=data.comment,
            organization_id=org_id,
        )
        return api_response(
            True,
            f"Sale recorded. {data.qty_sold} units sold. Stock balance: {sale.stock_after}",
            data=sale.get_summary(),
            status_code=201,
        )
    except ValueError as e:
        return api_response(False, str(e), status_code=400)


@router.get("/{sale_id}", summary="Get sale details")
async def get_sale(
    sale_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = _get_org_id(current_user)
    sale = inventory_service.get_sale(db, sale_id, organization_id=org_id)
    if not sale:
        return api_response(False, "Sale not found.", status_code=404)
    return api_response(True, "Sale fetched.", data=sale.get_summary())


@router.put("/{sale_id}", summary="Update sale comment [manager/admin]")
async def update_sale(
    sale_id: str,
    data: SaleUpdateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "super_admin", "manager")),
):
    org_id = _get_org_id(current_user)
    sale = inventory_service.get_sale(db, sale_id, organization_id=org_id)
    if not sale:
        return api_response(False, "Sale not found.", status_code=404)
    if data.comment is not None:
        sale.comment = data.comment
        db.commit()
        db.refresh(sale)
    return api_response(True, "Sale updated.", data=sale.get_summary())


@router.delete("/{sale_id}", summary="Void a sale (restores stock) [admin only]")
async def void_sale(
    sale_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "super_admin")),
):
    org_id = _get_org_id(current_user)
    sale = inventory_service.get_sale(db, sale_id, organization_id=org_id)
    if not sale:
        return api_response(False, "Sale not found.", status_code=404)

    item_name = sale.item.name if sale.item else "Unknown"
    inventory_service.void_sale(db, sale, organization_id=org_id)
    return api_response(True, f"Sale voided. Stock restored for '{item_name}'.")
