# app/api/v1/users.py
import logging
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps.users import _get_org_id, get_db, get_current_user
from app.api.deps.rbac import require_roles
from app.models.user import User
from app.models.rbac import Role
from app.schemas.user import UserUpdate, UserAdminUpdate
from app.utils.responses import api_response, PageSerializer

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/",
    summary="List all users [admin only]",
    dependencies=[Depends(require_roles("admin", "super_admin"))],
)
async def list_users(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = _get_org_id(current_user)
    users = (
        db.query(User)
        .filter(User.deleted == False, User.organization_id == org_id)
        .order_by(User.created_at.desc())
        .all()
    )
    return PageSerializer(request, obj=users, resource_name="users").get_response("Users fetched.")


@router.get("/me", summary="Get own profile")
async def get_profile(current_user: User = Depends(get_current_user)):
    return api_response(True, "Profile fetched.", data=current_user.get_summary())


@router.put("/me", summary="Update own profile")
async def update_profile(
    data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(current_user, field, value)
    db.commit()
    db.refresh(current_user)
    return api_response(True, "Profile updated.", data=current_user.get_summary())


@router.get(
    "/{user_id}",
    summary="Get a specific user [admin only]",
    dependencies=[Depends(require_roles("admin", "super_admin"))],
)
async def get_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = _get_org_id(current_user)
    user = db.query(User).filter(
        User.id == user_id,
        User.deleted == False,
        User.organization_id == org_id,
    ).first()
    if not user:
        return api_response(False, "User not found.", status_code=404)
    return api_response(True, "User fetched.", data=user.get_summary())


@router.put(
    "/{user_id}",
    summary="Update user [admin only]",
    dependencies=[Depends(require_roles("admin", "super_admin"))],
)
async def admin_update_user(
    user_id: str,
    data: UserAdminUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = _get_org_id(current_user)
    user = db.query(User).filter(
        User.id == user_id,
        User.deleted == False,
        User.organization_id == org_id,
    ).first()
    if not user:
        return api_response(False, "User not found.", status_code=404)

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return api_response(True, "User updated.", data=user.get_summary())


@router.delete(
    "/{user_id}",
    summary="Soft-delete a user [admin only]",
    dependencies=[Depends(require_roles("admin", "super_admin"))],
)
async def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = _get_org_id(current_user)
    user = db.query(User).filter(
        User.id == user_id,
        User.deleted == False,
        User.organization_id == org_id,
    ).first()
    if not user:
        return api_response(False, "User not found.", status_code=404)
    user.deleted = True
    db.commit()
    return api_response(True, "User removed.")


@router.post(
    "/{user_id}/roles/{role_name}",
    summary="Assign role to user [admin only]",
    dependencies=[Depends(require_roles("admin", "super_admin"))],
)
async def assign_role(
    user_id: str,
    role_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = _get_org_id(current_user)
    user = db.query(User).filter(
        User.id == user_id,
        User.deleted == False,
        User.organization_id == org_id,
    ).first()
    if not user:
        return api_response(False, "User not found.", status_code=404)

    role = db.query(Role).filter(Role.name == role_name).first()
    if not role:
        return api_response(False, f"Role '{role_name}' not found.", status_code=404)

    if role not in user.roles:
        user.roles.append(role)
        db.commit()

    return api_response(True, f"Role '{role_name}' assigned to {user.username}.", data=user.get_summary())


@router.delete(
    "/{user_id}/roles/{role_name}",
    summary="Remove role from user [admin only]",
    dependencies=[Depends(require_roles("admin", "super_admin"))],
)
async def remove_role(
    user_id: str,
    role_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = _get_org_id(current_user)
    user = db.query(User).filter(
        User.id == user_id,
        User.deleted == False,
        User.organization_id == org_id,
    ).first()
    if not user:
        return api_response(False, "User not found.", status_code=404)

    role = db.query(Role).filter(Role.name == role_name).first()
    if role and role in user.roles:
        user.roles.remove(role)
        db.commit()

    return api_response(True, f"Role '{role_name}' removed from {user.username}.", data=user.get_summary())
