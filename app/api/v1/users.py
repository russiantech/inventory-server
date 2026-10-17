# # app/api/v1/users.py
# import logging
# from fastapi import APIRouter, Depends, Request
# from sqlalchemy.orm import Session

# from app.api.deps.users import _get_org_id, get_db, get_current_user
# from app.api.deps.rbac import require_roles
# from app.models.user import User
# from app.models.rbac import Role
# from app.schemas.user import UserUpdate, UserAdminUpdate
# from app.utils.responses import api_response, PageSerializer
# from app.core.security.password import hash_password

# logger = logging.getLogger(__name__)
# router = APIRouter()


# @router.get(
#     "",
#     summary="List all users [admin only]",
#     dependencies=[Depends(require_roles("admin", "super_admin"))],
# )
# async def list_users(
#     request: Request,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     org_id = _get_org_id(current_user)
#     users = (
#         db.query(User)
#         .filter(User.deleted == False, User.organization_id == org_id)
#         .order_by(User.created_at.desc())
#         .all()
#     )
#     return PageSerializer(request, obj=users, resource_name="users").get_response("Users fetched.")


# @router.get("/me", summary="Get own profile")
# async def get_profile(current_user: User = Depends(get_current_user)):
#     return api_response(True, "Profile fetched.", data=current_user.get_summary())


# @router.put("/me", summary="Update own profile")
# async def update_profile(
#     data: UserUpdate,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     for field, value in data.model_dump(exclude_unset=True).items():
#         setattr(current_user, field, value)
#     db.commit()
#     db.refresh(current_user)
#     return api_response(True, "Profile updated.", data=current_user.get_summary())


# @router.get(
#     "/{user_id}",
#     summary="Get a specific user [admin only]",
#     dependencies=[Depends(require_roles("admin", "super_admin"))],
# )
# async def get_user(
#     user_id: str,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     org_id = _get_org_id(current_user)
#     user = db.query(User).filter(
#         User.id == user_id,
#         User.deleted == False,
#         User.organization_id == org_id,
#     ).first()
#     if not user:
#         return api_response(False, "User not found.", status_code=404)
#     return api_response(True, "User fetched.", data=user.get_summary())


# @router.put(
#     "/{user_id}",
#     summary="Update user [admin only]",
#     dependencies=[Depends(require_roles("admin", "super_admin"))],
# )
# async def admin_update_user(
#     user_id: str,
#     data: UserAdminUpdate,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     org_id = _get_org_id(current_user)
#     user = db.query(User).filter(
#         User.id == user_id,
#         User.deleted == False,
#         User.organization_id == org_id,
#     ).first()
#     if not user:
#         return api_response(False, "User not found.", status_code=404)

#     for field, value in data.model_dump(exclude_unset=True).items():
#         setattr(user, field, value)
#     db.commit()
#     db.refresh(user)
#     return api_response(True, "User updated.", data=user.get_summary())

# # @router.put(
# #     "/{user_id}/reset-password",
# #     summary="Admin reset user password [admin only]",
# #     dependencies=[Depends(require_roles("admin", "super_admin"))],
# # )

# # async def admin_reset_password(
# #     user_id: str,
# #     data: dict,
# #     db: Session = Depends(get_db),
# #     current_user: User = Depends(get_current_user),
# # ):
# #     """Allow admin to reset a user's password without knowing the old one."""
# #     org_id = _get_org_id(current_user)
# #     user = db.query(User).filter(
# #         User.id == user_id,
# #         User.deleted == False,
# #         User.organization_id == org_id,
# #     ).first()
# #     if not user:
# #         return api_response(False, "User not found.", status_code=404)
    
# #     new_password = data.get("new_password")
# #     if not new_password or len(new_password) < 4:
# #         return api_response(False, "Password must be at least 4 characters.", status_code=400)
    
# #     user.password_hash = hash_password(new_password)
# #     db.commit()
    
# #     logger.info(f"Admin {current_user.username} reset password for user {user.username}")
# #     return api_response(True, f"Password reset for {user.username}.", data={"email": user.email})

# # from app.core.security.password import hash_password


# @router.post(
#     "/{user_id}/reset-password",
#     summary="Admin reset user password [admin only]",
#     dependencies=[Depends(require_roles("admin", "super_admin"))],
# )
# async def admin_reset_password(
#     user_id: str,
#     data: dict,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     """Allow admin to reset a user's password without knowing the old one."""
#     org_id = _get_org_id(current_user)
#     user = db.query(User).filter(
#         User.id == user_id,
#         User.deleted == False,
#         User.organization_id == org_id,
#     ).first()
#     if not user:
#         return api_response(False, "User not found.", status_code=404)
    
#     new_password = data.get("new_password")
#     if not new_password or len(new_password) < 4:
#         return api_response(False, "Password must be at least 4 characters.", status_code=400)
    
#     user.password_hash = hash_password(new_password)
#     db.commit()
    
#     logger.info(f"Admin {current_user.username} reset password for user {user.username}")
#     return api_response(True, f"Password reset for {user.username}.", data={"email": user.email})

# @router.delete(
#     "/{user_id}",
#     summary="Soft-delete a user [admin only]",
#     dependencies=[Depends(require_roles("admin", "super_admin"))],
# )
# async def delete_user(
#     user_id: str,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     org_id = _get_org_id(current_user)
#     user = db.query(User).filter(
#         User.id == user_id,
#         User.deleted == False,
#         User.organization_id == org_id,
#     ).first()
#     if not user:
#         return api_response(False, "User not found.", status_code=404)
#     user.deleted = True
#     db.commit()
#     return api_response(True, "User removed.")


# @router.post(
#     "/{user_id}/roles/{role_name}",
#     summary="Assign role to user [admin only]",
#     dependencies=[Depends(require_roles("admin", "super_admin"))],
# )
# async def assign_role(
#     user_id: str,
#     role_name: str,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     org_id = _get_org_id(current_user)
#     user = db.query(User).filter(
#         User.id == user_id,
#         User.deleted == False,
#         User.organization_id == org_id,
#     ).first()
#     if not user:
#         return api_response(False, "User not found.", status_code=404)

#     role = db.query(Role).filter(Role.name == role_name).first()
#     if not role:
#         return api_response(False, f"Role '{role_name}' not found.", status_code=404)

#     if role not in user.roles:
#         user.roles.append(role)
#         db.commit()

#     return api_response(True, f"Role '{role_name}' assigned to {user.username}.", data=user.get_summary())


# @router.delete(
#     "/{user_id}/roles/{role_name}",
#     summary="Remove role from user [admin only]",
#     dependencies=[Depends(require_roles("admin", "super_admin"))],
# )
# async def remove_role(
#     user_id: str,
#     role_name: str,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     org_id = _get_org_id(current_user)
#     user = db.query(User).filter(
#         User.id == user_id,
#         User.deleted == False,
#         User.organization_id == org_id,
#     ).first()
#     if not user:
#         return api_response(False, "User not found.", status_code=404)

#     role = db.query(Role).filter(Role.name == role_name).first()
#     if role and role in user.roles:
#         user.roles.remove(role)
#         db.commit()

#     return api_response(True, f"Role '{role_name}' removed from {user.username}.", data=user.get_summary())




# v2
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
from app.core.security.password import hash_password

logger = logging.getLogger(__name__)
router = APIRouter()


def _is_super_admin(user: User) -> bool:
    return any(r.name == "super_admin" for r in user.roles)


def _scoped_user_query(db: Session, current_user: User):
    """Super admins see every user across every organization.
    Regular admins/managers only see users within their own organization."""
    q = db.query(User).filter(User.deleted == False)
    if not _is_super_admin(current_user):
        q = q.filter(User.organization_id == _get_org_id(current_user))
    return q


@router.get(
    "",
    summary="List users — super_admin sees all organizations, admin sees own org",
    dependencies=[Depends(require_roles("admin", "super_admin"))],
)
async def list_users(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    users = _scoped_user_query(db, current_user).order_by(User.created_at.desc()).all()
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
    summary="Get a specific user — super_admin: any org, admin: own org only",
    dependencies=[Depends(require_roles("admin", "super_admin"))],
)
async def get_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = _scoped_user_query(db, current_user).filter(User.id == user_id).first()
    if not user:
        return api_response(False, "User not found.", status_code=404)
    return api_response(True, "User fetched.", data=user.get_summary())


@router.put(
    "/{user_id}",
    summary="Update user — activation of org-admin accounts is super_admin only",
    dependencies=[Depends(require_roles("admin", "super_admin"))],
)
async def admin_update_user(
    user_id: str,
    data: UserAdminUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = _scoped_user_query(db, current_user).filter(User.id == user_id).first()
    if not user:
        return api_response(False, "User not found.", status_code=404)

    payload = data.model_dump(exclude_unset=True)

    # ── Activation gate ──────────────────────────────────────────────
    # When a new organization signs up, its first/owning admin account is
    # created with is_active=False pending review. Only a super_admin may
    # flip activation for an org-admin account (i.e. approve a new org).
    # A regular org admin may still activate/deactivate their own staff
    # (non org-admin users) within their organization.
    if "is_active" in payload and not _is_super_admin(current_user):
        if user.is_org_admin or _is_super_admin(user):
            return api_response(
                False,
                "Only a super admin can activate or suspend an organization's admin account.",
                status_code=403,
            )

    # Org admins must not be able to escalate users into super_admin via this endpoint.
    if "is_org_admin" in payload and not _is_super_admin(current_user):
        payload.pop("is_org_admin")

    for field, value in payload.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)

    action_logged = "activated" if payload.get("is_active") is True else (
        "deactivated" if payload.get("is_active") is False else "updated"
    )
    logger.info(f"{current_user.username} {action_logged} user {user.username} (org={user.organization_id})")

    return api_response(True, "User updated.", data=user.get_summary())


@router.put(
    "/{user_id}/reset-password",
    summary="Admin reset user password — super_admin: any org, admin: own org only",
    dependencies=[Depends(require_roles("admin", "dev", "super_admin"))],
)
async def admin_reset_password(
    user_id: str,
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Allow admin to reset a user's password without knowing the old one."""
    user = _scoped_user_query(db, current_user).filter(User.id == user_id).first()
    if not user:
        return api_response(False, "User not found.", status_code=404)

    # Org admins cannot reset passwords for other org-admin / super_admin accounts.
    if not _is_super_admin(current_user) and (user.is_org_admin or _is_super_admin(user)):
        return api_response(False, "Not permitted to reset this account's password.", status_code=403)

    new_password = data.get("new_password")
    if not new_password or len(new_password) < 4:
        return api_response(False, "Password must be at least 4 characters.", status_code=400)

    user.password_hash = hash_password(new_password)
    db.commit()

    logger.info(f"{current_user.username} reset password for user {user.username}")
    return api_response(True, f"Password reset for {user.username}.", data={"email": user.email})


@router.delete(
    "/{user_id}",
    summary="Soft-delete a user — super_admin: any org, admin: own org only",
    dependencies=[Depends(require_roles("admin", "dev", "super_admin"))],
)
async def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = _scoped_user_query(db, current_user).filter(User.id == user_id).first()
    if not user:
        return api_response(False, "User not found.", status_code=404)

    if not _is_super_admin(current_user) and (user.is_org_admin or _is_super_admin(user)):
        return api_response(False, "Not permitted to remove this account.", status_code=403)

    user.deleted = True
    db.commit()
    return api_response(True, "User removed.")


@router.post(
    "/{user_id}/roles/{role_name}",
    summary="Assign role to user — super_admin role assignable by super_admin only",
    dependencies=[Depends(require_roles("admin", "dev", "super_admin"))],
)
async def assign_role(
    user_id: str,
    role_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if role_name == "super_admin" and not _is_super_admin(current_user):
        return api_response(False, "Only a super admin can grant the super_admin role.", status_code=403)

    user = _scoped_user_query(db, current_user).filter(User.id == user_id).first()
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
    summary="Remove role from user [admin/super_admin]",
    dependencies=[Depends(require_roles("admin", "dev", "super_admin"))],
)
async def remove_role(
    user_id: str,
    role_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if role_name == "super_admin" and not _is_super_admin(current_user):
        return api_response(False, "Only a super admin can revoke the super_admin role.", status_code=403)

    user = _scoped_user_query(db, current_user).filter(User.id == user_id).first()
    if not user:
        return api_response(False, "User not found.", status_code=404)

    role = db.query(Role).filter(Role.name == role_name).first()
    if role and role in user.roles:
        user.roles.remove(role)
        db.commit()

    return api_response(True, f"Role '{role_name}' removed from {user.username}.", data=user.get_summary())

