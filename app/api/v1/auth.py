# app/api/v1/auth.py
import logging
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.api.deps.users import get_db, get_current_user
from app.core.security.auth import create_access_token, create_refresh_token, decode_token
from app.models.user import User
from app.schemas.auth import SigninSchema, SignupSchema, ChangePasswordSchema
from app.services.auth_service import authenticate_user, create_user
from app.utils.responses import api_response
from app.utils.helpers import get_client_ip

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/signin", summary="Sign in with email/username + password")
async def signin(data: SigninSchema, request: Request, db: Session = Depends(get_db)):
    user = authenticate_user(db, data.email, data.password)
    if not user:
        return api_response(False, "Invalid credentials. Please check your email/username and password.", status_code=401)
    if not user.is_active:
        return api_response(False, "Your account has been deactivated. Contact an administrator.", status_code=403)

    access_token = create_access_token(subject=str(user.id), extra={"roles": user.role_names})
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


@router.post("/signup", summary="Register a new user account", status_code=status.HTTP_201_CREATED)
async def signup(data: SignupSchema, request: Request, db: Session = Depends(get_db)):
    # Check uniqueness
    existing = db.query(User).filter(
        or_(User.email == data.email.lower(), User.username == data.username.lower()),
        User.deleted == False,
    ).first()

    if existing:
        field = "email" if existing.email == data.email.lower() else "username"
        return api_response(False, f"An account with this {field} already exists.", status_code=409)

    if data.phone:
        phone_exists = db.query(User).filter(User.phone == data.phone, User.deleted == False).first()
        if phone_exists:
            return api_response(False, "An account with this phone number already exists.", status_code=409)

    user = create_user(
        db=db,
        username=data.username,
        email=data.email,
        password=data.password,
        names=data.names,
        phone=data.phone,
    )
    user.ip = get_client_ip(request)
    db.commit()

    access_token = create_access_token(subject=str(user.id), extra={"roles": user.role_names})

    return api_response(
        True,
        "Account created successfully.",
        data={
            "access_token": access_token,
            "token_type": "Bearer",
            "user": user.get_summary(),
        },
        status_code=201,
    )


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

    access_token = create_access_token(subject=str(user.id), extra={"roles": user.role_names})
    return api_response(True, "Token refreshed.", data={"access_token": access_token, "token_type": "Bearer"})


@router.get("/me", summary="Get current authenticated user profile")
async def get_me(current_user: User = Depends(get_current_user)):
    return api_response(True, "Profile fetched.", data=current_user.get_summary())


@router.post("/change-password", summary="Change password")
async def change_password(
    data: ChangePasswordSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.check_password(data.current_password):
        return api_response(False, "Current password is incorrect.", status_code=400)

    current_user.set_password(data.new_password)
    db.commit()
    return api_response(True, "Password changed successfully.")


@router.post("/signout", summary="Sign out (client should discard token)")
async def signout(current_user: User = Depends(get_current_user)):
    return api_response(True, f"Signed out successfully. Goodbye, {current_user.names or current_user.username}!")
