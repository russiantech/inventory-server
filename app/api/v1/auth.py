# # Generate all the updated files

# ============================================
# 1. BACKEND: Updated auth.py
# ============================================
# app/api/v1/auth.py
"""
Authentication endpoints — Dunis Inventory (Org/Tenant Model)
=============================================================
- Organization-first: Only admin can create accounts (initially)
- Two-step signup: initiate → verify via 6-digit code (Redis-backed)
- Admin can toggle public signup via org config
- Multi-identifier signin: email | username | phone
- All users belong to an organization; data is tenant-scoped
"""

import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.api.deps.users import get_db, get_current_user, admin_required as require_admin
from app.core.security.auth import (
    create_access_token, create_refresh_token,
    decode_token
)
from app.core.security.password import (
    hash_password, verify_password,
)

from app.models.user import User
from app.models.organization import Organization
from app.schemas.auth import (
    SigninSchema, ChangePasswordSchema,
    SignupSchema, SignupVerifySchema,
    ForgotPasswordSchema, ResetPasswordSchema,
    CreateStaffSchema,
)
from app.services.auth_service import authenticate_user, create_user
from app.services import branch_service
from app.services.scope_service import ScopeError, build_access_scope
from app.services.email_service import send_verification_email, send_welcome_email, send_password_reset_email
from app.services.redis_service import RedisService
from app.api.deps.storage import get_redis_service
from app.utils.responses import api_response
from app.utils.helpers import get_client_ip, generate_code

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Organization & Admin-Only Account Creation
# ---------------------------------------------------------------------------

@router.post("/signup", status_code=status.HTTP_202_ACCEPTED, summary="Step 1: Initiate signup (admin or first org account)")
async def signup(
    data: SignupSchema,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    redis: Optional[RedisService] = Depends(get_redis_service),
):
    """
    Initiate account creation. 
    
    RULES:
    - If NO users exist in the system → this becomes the ORG ADMIN (first account).
    - If users exist → only an existing admin can call this (to create staff accounts).
    - Public signup can be disabled by admin via org config.
    """
    if not redis:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable. Please try again.")

    user_count = db.query(User).filter(User.deleted == False).count()
    is_first_account = user_count == 0

    # ── First account = org admin (no auth needed) ──
    if not is_first_account:
        org = db.query(Organization).first()
        if not org or getattr(org, "allow_public_signup", False) is False:
            raise HTTPException(
                status_code=403,
                detail="Account creation is restricted. Contact your administrator.",
            )
        # Public signup enabled: anyone can sign up, but account stays
        # inactive until an admin approves it.
        is_public_signup = True
        target_org_id = org.id
    else:
        is_public_signup = False
        target_org_id = None

    # Check uniqueness
    existing = db.query(User).filter(
        or_(
            User.email == data.email.lower(),
            User.username == data.username.lower(),
        ),
        User.deleted == False,
    ).first()
    if existing:
        field = "email" if existing.email == data.email.lower() else "username"
        raise HTTPException(status_code=409, detail=f"An account with this {field} already exists.")

    if data.phone:
        phone_exists = db.query(User).filter(
            User.phone == data.phone,
            User.deleted == False,
        ).first()
        if phone_exists:
            raise HTTPException(status_code=409, detail="An account with this phone number already exists.")

    # Generate verification code
    email_code = generate_code(6)
    signup_token = secrets.token_urlsafe(32)

    signup_data = {
        "username": data.username.lower(),
        "email": data.email.lower(),
        "names": data.names or data.username,
        "phone": data.phone or "",
        "password_hash": hash_password(data.password),
        "email_code": email_code,
        "is_org_admin": not is_public_signup,
        "is_public_signup": is_public_signup,
        "organization_id": target_org_id,
        "org_name": data.org_name or f"{data.username}\'s Organization",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ip": get_client_ip(request),
    }

    redis_key = f"dunis:signup_pending:{signup_token}"
    if not redis.set(redis_key, signup_data, expiry=600):
        raise HTTPException(status_code=503, detail="Could not initiate signup. Please try again.")

    if not send_verification_email(data.email.lower(), data.names or data.username, email_code):
        redis.delete(redis_key)
        raise HTTPException(
            status_code=502,
            detail="Failed to send verification email. Please check the address and try again.",
        )

    logger.info(f"Signup initiated for {data.email} (first org admin)")

    return api_response(
        True,
        "Verification code sent! Check your email.",
        data={
            "token": signup_token,
            "email": data.email.lower(),
            "expires_in_seconds": 600,
        },
    )


@router.post("/signup/verify", status_code=status.HTTP_201_CREATED, summary="Step 2: Verify code and create account")
async def signup_verify(
    data: SignupVerifySchema,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    redis: Optional[RedisService] = Depends(get_redis_service),
):
    """Verify 6-digit code and finalize account creation."""
    if not redis:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable.")

    if not data.token or not data.email_code:
        raise HTTPException(status_code=400, detail="Token and verification code are required.")

    redis_key = f"dunis:signup_pending:{data.token}"
    signup_data = redis.get(redis_key, as_json=True)

    if not signup_data:
        raise HTTPException(status_code=400, detail="Session expired or invalid. Please start again.")

    if signup_data.get("email_code") != data.email_code.strip().upper():
        raise HTTPException(status_code=400, detail="Invalid verification code.")

    # Double-check uniqueness
    if db.query(User).filter(User.email == signup_data["email"], User.deleted == False).first():
        redis.delete(redis_key)
        raise HTTPException(status_code=409, detail="Email already registered.")
    if db.query(User).filter(User.username == signup_data["username"], User.deleted == False).first():
        redis.delete(redis_key)
        raise HTTPException(status_code=409, detail="Username already taken.")

    if signup_data.get("is_public_signup"):
        # ── Public signup: attach to existing org, inactive until admin approval ──
        org = db.query(Organization).filter(Organization.id == signup_data["organization_id"]).first()
        if not org:
            redis.delete(redis_key)
            raise HTTPException(status_code=400, detail="Organization no longer exists.")

        current_user_count = db.query(User).filter(
            User.organization_id == org.id, User.deleted == False
        ).count()
        max_users = org.max_users if org.max_users is not None else 5
        if current_user_count >= max_users:
            redis.delete(redis_key)
            raise HTTPException(status_code=403, detail="User limit reached for this organization.")

        user = create_user(
            db=db,
            username=signup_data["username"],
            email=signup_data["email"],
            password_hash=signup_data["password_hash"],
            names=signup_data["names"],
            phone=signup_data["phone"] or None,
            organization_id=org.id,
            is_org_admin=False,
            email_verified=True,
        )
        # Pending admin approval — admin activates via PUT /users/{id}.
        user.is_active = False
        user.ip = signup_data.get("ip")
        db.commit()
        db.refresh(user)

        # Place the new member in the org's default branch; admins can move them later.
        default_branch = branch_service.ensure_default_branch(db, org.id)
        branch_service.assign_member(db, org.id, user, default_branch, "staff")

        redis.delete(redis_key)

        background_tasks.add_task(
            send_welcome_email,
            user.email,
            user.names or user.username,
        )

        logger.info(f"Public signup: account '{user.username}' created in org '{org.name}', pending activation")

        return api_response(
            True,
            "Account created! An administrator must activate your account before you can sign in.",
            data={"user": user.get_summary(), "organization": {"id": org.id, "name": org.name}},
            status_code=201,
        )

    # ── Create Organization ──
    org = Organization(
        name=signup_data.get("org_name", "Default Organization"),
        slug=signup_data["username"],
        plan="free",  # Default plan; admin upgrades later
        allow_public_signup=False,  # Default: admin-only creation
        max_users=5,  # Free tier limit
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    db.flush()  # Get org.id

    # ── Create Admin User ──
    user = create_user(
        db=db,
        username=signup_data["username"],
        email=signup_data["email"],
        password_hash=signup_data["password_hash"],  # Already hashed
        names=signup_data["names"],
        phone=signup_data["phone"] or None,
        organization_id=org.id,
        is_org_admin=True,
        email_verified=True,
    )
    # Root cause of "403 Forbidden" on signin: User.is_active defaults to False
    # at the DB level and was never being set. The very first account is the
    # org admin and must be able to log in right away — set it active here.
    user.is_active = True
    user.ip = signup_data.get("ip")
    db.commit()
    db.refresh(user)

    # Update org owner
    org.owner_id = user.id
    db.commit()

    # Every organization starts with a default branch + 'general' department.
    branch_service.ensure_default_branch(db, org.id)

    redis.delete(redis_key)

    # access_token = create_access_token(subject=str(user.id), extra={"roles": user.role_names, "org_id": org.id})
    access_token = create_access_token(
        subject=str(user.id),
        extra={"roles": user.role_names, "org_id": str(org.id)},
        )
    
    refresh_token = create_refresh_token(subject=str(user.id))

    background_tasks.add_task(
        send_welcome_email,
        user.email,
        user.names or user.username,
    )

    logger.info(f"Organization '{org.name}' created by {user.username}")

    return api_response(
        True,
        "Account created successfully! Welcome to Dunis Inventory.",
        data={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "user": user.get_summary(),
            "organization": {"id": org.id, "name": org.name, "plan": org.plan},
        },
        status_code=201,
    )


@router.post("/signup/resend", summary="Resend verification code")
async def resend_signup_code(
    data: dict,
    background_tasks: BackgroundTasks,
    redis: Optional[RedisService] = Depends(get_redis_service),
):
    """Resend verification code for pending signup."""
    if not redis:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable.")

    token = data.get("token", "")
    if not token:
        raise HTTPException(status_code=400, detail="Token is required.")

    redis_key = f"dunis:signup_pending:{token}"
    signup_data = redis.get(redis_key, as_json=True)

    if not signup_data:
        raise HTTPException(status_code=400, detail="Session expired. Please start again.")

    new_code = generate_code(6)
    signup_data["email_code"] = new_code
    redis.set(redis_key, signup_data, expiry=600)

    if not send_verification_email(
        signup_data["email"],
        signup_data["names"] or signup_data["username"],
        new_code,
    ):
        raise HTTPException(status_code=502, detail="Failed to send verification email. Please try again.")

    return api_response(True, "New verification code sent.")


# ---------------------------------------------------------------------------
# Admin: Create Staff/Users Within Organization
# ---------------------------------------------------------------------------

# @router.post("/users/create", summary="Admin creates staff/user account (org-scoped)")
# async def create_staff_user(
#     data: CreateStaffSchema,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(require_admin),
#     redis: Optional[RedisService] = Depends(get_redis_service),
# ):
#     """
#     Admin-only endpoint to create staff accounts within the same organization.
#     Enforces organization user limits based on subscription plan.
#     """
#     if not current_user.is_org_admin:
#         raise HTTPException(status_code=403, detail="Organization admin privileges required.")

#     org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
#     if not org:
#         raise HTTPException(status_code=404, detail="Organization not found.")

#     # Check plan limits
#     current_user_count = db.query(User).filter(
#         User.organization_id == org.id,
#         User.deleted == False,
#     ).count()
#     if current_user_count >= org.max_users:
#         raise HTTPException(
#             status_code=403,
#             detail=f"User limit reached ({org.max_users}). Upgrade your plan to add more users.",
#         )

#     # Check uniqueness
#     existing = db.query(User).filter(
#         or_(
#             User.email == data.email.lower(),
#             User.username == data.username.lower(),
#         ),
#         User.deleted == False,
#     ).first()
#     if existing:
#         field = "email" if existing.email == data.email.lower() else "username"
#         raise HTTPException(status_code=409, detail=f"An account with this {field} already exists.")

#     # Generate temp password if not provided
#     temp_password = data.password or secrets.token_urlsafe(12)

#     user = create_user(
#         db=db,
#         username=data.username.lower(),
#         email=data.email.lower(),
#         password_hash=hash_password(temp_password),
#         names=data.names,
#         phone=data.phone,
#         organization_id=org.id,
#         is_org_admin=False,
#         role=data.role or "staff",  # staff, manager, cashier, etc.
#         email_verified=True,  # Admin-created accounts are pre-verified
#     )
#     db.commit()
#     db.refresh(user)

#     logger.info(f"Admin {current_user.username} created user {user.username} in org {org.name}")

#     return api_response(
#         True,
#         f"User '{user.username}' created successfully.",
#         data={
#             "user": user.get_summary(),
#             "temp_password": temp_password if not data.password else None,
#             "organization_users": current_user_count + 1,
#             "max_users": org.max_users,
#         },
#     )

# v2
@router.post("/users/create", summary="Admin creates staff/user account (org-scoped)")
async def create_staff_user(
    data: CreateStaffSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
    redis: Optional[RedisService] = Depends(get_redis_service),
):
    """
    Admin-only endpoint to create staff accounts within the same organization.
    Enforces organization user limits based on subscription plan.
    """
    # REMOVED: is_org_admin check — any admin role can create users
    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")

    # Check plan limits
    current_user_count = db.query(User).filter(
        User.organization_id == org.id,
        User.deleted == False,
    ).count()
    
    max_users = org.max_users if org.max_users is not None else 5
    if current_user_count >= max_users:
        raise HTTPException(
            status_code=403,
            detail=f"User limit reached ({max_users}). Upgrade your plan to add more users.",
        )

    # Check uniqueness
    existing = db.query(User).filter(
        or_(
            User.email == data.email.lower(),
            User.username == data.username.lower(),
        ),
        User.deleted == False,
    ).first()
    if existing:
        field = "email" if existing.email == data.email.lower() else "username"
        raise HTTPException(status_code=409, detail=f"An account with this {field} already exists.")

    # Resolve the branch the new user will work in (before creating anything)
    try:
        creator_scope = build_access_scope(db, current_user)
        target_branch_id, target_department_id = creator_scope.resolve_write_target(
            db, data.branch_id, data.department_id
        )
        creator_scope.require_role(target_branch_id, "manager")
        branch_role = data.branch_role or ("manager" if data.role == "manager" else "staff")
        if branch_role == "admin" and not creator_scope.org_wide:
            raise ScopeError("Only organization admins can appoint a branch admin.")
        if branch_role == "manager":
            # granting manager rights is an admin-level action within the branch
            creator_scope.require_role(target_branch_id, "admin")
    except ScopeError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    # Generate temp password if not provided
    temp_password = data.password or secrets.token_urlsafe(12)

    user = create_user(
        db=db,
        username=data.username.lower(),
        email=data.email.lower(),
        password_hash=hash_password(temp_password),
        names=data.names,
        phone=data.phone,
        organization_id=org.id,
        is_org_admin=False,
        role=data.role or "staff",
        email_verified=True,
    )
    # Pending admin activation per policy — admin can flip is_active via
    # PUT /users/{id} (UserAdminUpdate) once ready.
    user.is_active = False
    db.commit()
    db.refresh(user)

    try:
        branch = branch_service.get_branch(db, target_branch_id, org.id)
        branch_service.assign_member(
            db, org.id, user, branch, branch_role,
            department_id=target_department_id, assigned_by=current_user.id,
        )
    except ValueError as e:
        # user exists but could not be placed: report clearly instead of failing silently
        raise HTTPException(status_code=400, detail=f"User created, but branch assignment failed: {e}")

    logger.info(f"Admin {current_user.username} created user {user.username} in org {org.name}")

    return api_response(
        True,
        f"User '{user.username}' created successfully.",
        data={
            "user": user.get_summary(),
            "temp_password": temp_password if not data.password else None,
            "organization_users": current_user_count + 1,
            "max_users": max_users,  # <-- was org.max_users
        },
    )


# ---------------------------------------------------------------------------
# Admin: Toggle Public Signup
# ---------------------------------------------------------------------------

# @router.post("/config/signup-toggle", summary="Admin toggle public signup availability")
# async def toggle_public_signup(
#     data: dict,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(require_admin),
# ):
#     """Enable or disable public account creation."""
#     if not current_user.is_org_admin:
#         raise HTTPException(status_code=403, detail="Organization admin required.")

#     org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
#     if not org:
#         raise HTTPException(status_code=404, detail="Organization not found.")

#     allow = data.get("allow_public_signup", False)
#     org.allow_public_signup = bool(allow)
#     db.commit()

#     status_msg = "enabled" if allow else "disabled"
#     logger.info(f"Admin {current_user.username} {status_msg} public signup for org {org.name}")

#     return api_response(True, f"Public signup {status_msg}.", data={"allow_public_signup": org.allow_public_signup})

# v2
@router.post("/config/signup-toggle", summary="Admin toggle public signup availability")
async def toggle_public_signup(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Enable or disable public account creation."""
    # REMOVED: is_org_admin check — any admin role can toggle signup
    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")

    allow = data.get("allow_public_signup", False)
    org.allow_public_signup = bool(allow)
    db.commit()

    status_msg = "enabled" if allow else "disabled"
    logger.info(f"Admin {current_user.username} {status_msg} public signup for org {org.name}")

    return api_response(True, f"Public signup {status_msg}.", data={"allow_public_signup": org.allow_public_signup})



# ---------------------------------------------------------------------------
# Sign In — Multi-identifier
# ---------------------------------------------------------------------------

@router.post("/signin", summary="Sign in with email/username/phone + password")
async def signin(
    data: SigninSchema,
    request: Request,
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, data.identifier, data.password)
    if not user:
        return api_response(False, "Invalid credentials. Please check your identifier and password.", status_code=401)
    if not user.is_active:
        return api_response(False, "Your account has been deactivated. Contact an administrator.", status_code=403)
    if not user.email_verified:
        return api_response(False, "Please verify your email before signing in.", status_code=403)

    # Update online status
    user.is_online = True
    user.last_seen = datetime.now(timezone.utc)
    db.commit()

    # access_token = create_access_token(
    #     subject=str(user.id),
    #     extra={"roles": user.role_names, "org_id": str(user.organization_id)},
    # )
    access_token = create_access_token(
    subject=str(user.id),
    extra={"roles": user.role_names, "org_id": str(user.organization_id) if user.organization_id else None},
    )
    refresh_token = create_refresh_token(subject=str(user.id))

    return api_response(
        True,
        "Sign in successful. Welcome back!",
        data={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "user": user.get_summary(),
        },
    )


# ---------------------------------------------------------------------------
# Refresh / Me / Signout
# ---------------------------------------------------------------------------

@router.post("/refresh", summary="Exchange refresh token for new access token")
async def refresh_token(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    token = body.get("refresh_token")
    if not token:
        return api_response(False, "Refresh token required.", status_code=400)

    payload = decode_token(token)
    if not payload or payload.get("type") != "refresh":
        return api_response(False, "Invalid or expired refresh token.", status_code=401)

    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id, User.deleted == False).first()
    if not user or not user.is_active:
        return api_response(False, "User not found or inactive.", status_code=401)

    # access_token = create_access_token(
    #     subject=str(user.id),
    #     extra={"roles": user.role_names, "org_id": user.organization_id},
    # )
    # v2
    access_token = create_access_token(
        subject=str(user.id),
        extra={"roles": user.role_names, "org_id": str(user.organization_id) if user.organization_id else None},
    )
    return api_response(True, "Token refreshed.", data={"access_token": access_token, "token_type": "Bearer"})


@router.get("/me", summary="Get current authenticated user profile")
async def get_me(current_user: User = Depends(get_current_user)):
    org = None
    if current_user.organization_id:
        # Import here to avoid circular dependency
        from app.models.organization import Organization
        org = current_user.organization
    return api_response(
        True,
        "Profile fetched.",
        data={
            **current_user.get_summary(),
            "organization": org.get_summary() if org else None,
        },
    )


@router.post("/signout", summary="Sign out")
async def signout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.is_online = False
    current_user.last_seen = datetime.now(timezone.utc)
    db.commit()
    return api_response(True, f"Signed out successfully. Goodbye, {current_user.names or current_user.username}!")


# ---------------------------------------------------------------------------
# Password Management
# ---------------------------------------------------------------------------

@router.post("/forgot-password", summary="Request password reset code")
async def forgot_password(
    data: ForgotPasswordSchema,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    redis: Optional[RedisService] = Depends(get_redis_service),
):
    if not redis:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable.")

    user = db.query(User).filter(
        User.email == data.email.lower(),
        User.deleted == False,
        User.is_active == True,
    ).first()

    reset_token = secrets.token_urlsafe(32)
    reset_code = generate_code(6)

    if user:
        redis_key = f"dunis:pwd_reset:{reset_token}"
        redis.set(
            redis_key,
            {"user_id": str(user.id), "email": user.email, "reset_code": reset_code},
            expiry=900,
        )
        if not send_password_reset_email(user.email, user.names or user.username, reset_code):
            redis.delete(redis_key)
            raise HTTPException(status_code=502, detail="Failed to send reset email. Please try again.")
        logger.info(f"Password reset initiated for {user.email}")

    return api_response(
        True,
        "If that email is registered, a reset code has been sent.",
        data={"token": reset_token, "email": data.email.lower(), "expires_in_seconds": 900},
    )

@router.post("/forgot-password/verify-code", summary="Verify reset code without consuming it")
async def verify_reset_code(
    data: dict,
    redis: RedisService = Depends(get_redis_service),
):
    """
    Lightweight endpoint to verify a reset code is valid before showing password form.
    Does NOT consume the code — the code is only consumed on successful /reset-password.
    """
    token = data.get("token", "")
    email_code = data.get("email_code", "").strip().upper()
    
    if not token or not email_code or len(email_code) != 6:
        raise HTTPException(status_code=400, detail="Token and 6-digit code are required.")
    
    redis_key = f"dunis:pwd_reset:{token}"
    reset_data = redis.get(redis_key, as_json=True)
    
    if not reset_data:
        raise HTTPException(status_code=400, detail="Session expired. Please start again.")
    
    if reset_data.get("noop"):
        raise HTTPException(status_code=400, detail="Invalid or expired reset code.")
    
    if reset_data.get("reset_code") != email_code:
        raise HTTPException(status_code=400, detail="Invalid verification code.")
    
    return api_response(True, "Code verified.", data={"valid": True})


@router.post("/reset-password", summary="Reset password with code")
async def reset_password(
    data: ResetPasswordSchema,
    db: Session = Depends(get_db),
    redis: Optional[RedisService] = Depends(get_redis_service),
):
    if not redis:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable.")

    if not data.token or not data.email_code or not data.new_password:
        raise HTTPException(status_code=400, detail="Token, code, and new password are required.")
    if len(data.new_password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters.")

    redis_key = f"dunis:pwd_reset:{data.token}"
    reset_data = redis.get(redis_key, as_json=True)

    if not reset_data or reset_data.get("reset_code") != data.email_code.strip().upper():
        raise HTTPException(status_code=400, detail="Invalid or expired reset code.")

    user = db.query(User).filter(User.id == reset_data["user_id"], User.deleted == False).first()
    if not user or not user.is_active:
        redis.delete(redis_key)
        raise HTTPException(status_code=400, detail="Account unavailable.")

    # user.password = hash_password(data.new_password)
    user.set_password(data.new_password)
    
    db.commit()
    redis.delete(redis_key)

    return api_response(True, "Password reset successfully. You can now sign in.", data={"email": user.email})


@router.post("/forgot-password/resend", summary="Resend password reset code")
async def resend_reset_code(
    data: dict,
    background_tasks: BackgroundTasks,
    redis: Optional[RedisService] = Depends(get_redis_service),
):
    if not redis:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable.")

    token = data.get("token", "")
    redis_key = f"dunis:pwd_reset:{token}"
    reset_data = redis.get(redis_key, as_json=True)

    if not reset_data:
        raise HTTPException(status_code=400, detail="Session expired. Please start again.")

    new_code = generate_code(6)
    reset_data["reset_code"] = new_code
    redis.set(redis_key, reset_data, expiry=900)

    background_tasks.add_task(
        send_password_reset_email,
        reset_data["email"],
        reset_data.get("name") or reset_data["email"],
        new_code,
    )

    return api_response(True, "New reset code sent.")


@router.post("/change-password", summary="Change password")
async def change_password(
    data: ChangePasswordSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(data.current_password, current_user.password_hash):
        return api_response(False, "Current password is incorrect.", status_code=400)

    current_user.password_hash = hash_password(data.new_password)
    db.commit()
    return api_response(True, "Password changed successfully.")

