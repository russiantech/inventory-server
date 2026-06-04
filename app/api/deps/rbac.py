# app/api/deps/rbac.py
from fastapi import Depends, HTTPException, status
from app.api.deps.users import get_current_user


def require_roles(*roles: str):
    async def role_checker(current_user=Depends(get_current_user)):
        if not current_user.has_role(*roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return current_user
    return role_checker
