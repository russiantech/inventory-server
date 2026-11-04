# app/api/v1/categories.py
import logging
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps.users import _get_org_id, get_db, get_current_user
from app.api.deps.rbac import require_roles
from app.models.user import User
from app.api.deps.scope import get_access_scope, get_scope_filter, scope_error_response
from app.services.scope_service import AccessScope, ScopeFilter, ScopeError
from app.schemas.inventory import CategoryCreate, CategoryUpdate
from app.services import inventory_service
from app.utils.responses import api_response, PageSerializer

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", summary="List all categories")
async def list_categories(
    request: Request,
    dept: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    sf: ScopeFilter = Depends(get_scope_filter),
):
    org_id = _get_org_id(current_user)
    cats = inventory_service.get_categories(db, dept=dept, organization_id=org_id, scope=sf)
    return PageSerializer(request, obj=cats, resource_name="categories").get_response("Categories fetched.")


@router.post("", summary="Create a category [admin/manager]", status_code=201)
async def create_category(
    data: CategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "super_admin", "manager")),
    scope: AccessScope = Depends(get_access_scope),
):
    org_id = _get_org_id(current_user)

    try:
        branch_id, department_id = scope.resolve_write_target(
            db, data.branch_id, data.department_id, require_department=True
        )
        scope.require_role(branch_id, "manager")
    except ScopeError as e:
        return scope_error_response(e)

    from app.models.category import Category
    existing = db.query(Category).filter(
        Category.name == data.name,
        Category.branch_id == branch_id,
        Category.dept == data.dept,
        Category.deleted == False,
        Category.organization_id == org_id,
    ).first()
    if existing:
        return api_response(
            False,
            f"Category '{data.name}' already exists in dept '{data.dept}'.",
            status_code=409,
        )

    try:
        cat = inventory_service.create_category(
            db, data, user_id=current_user.id, organization_id=org_id,
            branch_id=branch_id, department_id=department_id,
        )
    except ValueError as e:
        return api_response(False, str(e), status_code=400)
    return api_response(True, "Category created.", data=cat.get_summary(), status_code=201)


@router.get("/{category_id}", summary="Get a specific category")
async def get_category(
    category_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    sf: ScopeFilter = Depends(get_scope_filter),
):
    org_id = _get_org_id(current_user)
    cat = inventory_service.get_category(db, category_id, organization_id=org_id, scope=sf)
    if not cat:
        return api_response(False, "Category not found.", status_code=404)
    return api_response(True, "Category fetched.", data=cat.get_summary())


@router.put("/{category_id}", summary="Update category [admin/manager]")
async def update_category(
    category_id: str,
    data: CategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "super_admin", "manager")),
    scope: AccessScope = Depends(get_access_scope),
    sf: ScopeFilter = Depends(get_scope_filter),
):
    org_id = _get_org_id(current_user)
    cat = inventory_service.get_category(db, category_id, organization_id=org_id, scope=sf)
    if not cat:
        return api_response(False, "Category not found.", status_code=404)

    try:
        scope.require_role(cat.branch_id, "manager")
        cat = inventory_service.update_category(
            db,
            cat,
            data.model_dump(exclude_unset=True),
            organization_id=org_id,
        )
    except ScopeError as e:
        return scope_error_response(e)
    except ValueError as e:
        return api_response(False, str(e), status_code=400)
    return api_response(True, "Category updated.", data=cat.get_summary())


@router.delete("/{category_id}", summary="Delete category [admin only]")
async def delete_category(
    category_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "super_admin", "manager")),
    scope: AccessScope = Depends(get_access_scope),
    sf: ScopeFilter = Depends(get_scope_filter),
):
    org_id = _get_org_id(current_user)
    cat = inventory_service.get_category(db, category_id, organization_id=org_id, scope=sf)
    if not cat:
        return api_response(False, "Category not found.", status_code=404)
    try:
        # Org admins pass; managers must be an admin of this category's branch.
        scope.require_role(cat.branch_id, "admin")
    except ScopeError as e:
        return scope_error_response(e)
    if cat.items:
        return api_response(
            False,
            "Cannot delete category that has items. Reassign items first.",
            status_code=400,
        )

    inventory_service.delete_category(db, cat, organization_id=org_id)
    return api_response(True, "Category deleted.")
