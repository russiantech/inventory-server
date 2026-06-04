# app/api/v1/categories.py
import logging
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps.users import get_db, get_current_user
from app.api.deps.rbac import require_roles
from app.models.user import User
from app.schemas.inventory import CategoryCreate, CategoryUpdate
from app.services import inventory_service
from app.utils.responses import api_response, PageSerializer

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", summary="List all categories")
async def list_categories(
    request: Request,
    dept: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cats = inventory_service.get_categories(db, dept=dept)
    return PageSerializer(request, obj=cats, resource_name="categories").get_response("Categories fetched.")


@router.post("/", summary="Create a category [admin/manager]", status_code=201)
async def create_category(
    data: CategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "super_admin", "manager")),
):
    # Check duplicate name in same dept
    from app.models.category import Category
    existing = db.query(Category).filter(
        Category.name == data.name,
        Category.dept == data.dept,
        Category.deleted == False,
    ).first()
    if existing:
        return api_response(False, f"Category '{data.name}' already exists in dept '{data.dept}'.", status_code=409)

    cat = inventory_service.create_category(db, data, user_id=current_user.id)
    return api_response(True, "Category created.", data=cat.get_summary(), status_code=201)


@router.get("/{category_id}", summary="Get a specific category")
async def get_category(
    category_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cat = inventory_service.get_category(db, category_id)
    if not cat:
        return api_response(False, "Category not found.", status_code=404)
    return api_response(True, "Category fetched.", data=cat.get_summary())


@router.put("/{category_id}", summary="Update category [admin/manager]")
async def update_category(
    category_id: str,
    data: CategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "super_admin", "manager")),
):
    cat = inventory_service.get_category(db, category_id)
    
    if not cat:
        return api_response(False, "Category not found.", status_code=404)

    # cat = inventory_service.update_category(db, cat, data)
    
    cat = inventory_service.update_category(
    db,
    cat,
    data.dict(exclude_unset=True)  # critical
    )
    return api_response(True, "Category updated.", data=cat.get_summary())


@router.delete("/{category_id}", summary="Delete category [admin only]")
async def delete_category(
    category_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "super_admin")),
):
    cat = inventory_service.get_category(db, category_id)
    if not cat:
        return api_response(False, "Category not found.", status_code=404)
    if cat.items:
        return api_response(False, "Cannot delete category that has items. Reassign items first.", status_code=400)

    inventory_service.delete_category(db, cat)
    return api_response(True, "Category deleted.")
