# app/api/deps/scope.py
"""
FastAPI dependencies that resolve branch/department scope for a request.

    scope: AccessScope  = Depends(get_access_scope)   # who is the caller
    sf:    ScopeFilter  = Depends(get_scope_filter)   # which rows (reads)

Reads accept optional ``?branch_id=`` and ``?department_id=`` query params.
Writes call ``scope.resolve_write_target(...)`` with ids from the request body.
"""
from typing import Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps.users import get_db, get_current_user
from app.models.user import User
from app.services.scope_service import (
    AccessScope, ScopeFilter, ScopeError, build_access_scope,
)
from app.utils.responses import api_response


def scope_error_response(exc: ScopeError):
    """Uniform JSON error (same envelope as the rest of the API)."""
    return api_response(False, exc.message, status_code=exc.status_code)


async def get_access_scope(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AccessScope:
    try:
        return build_access_scope(db, current_user)
    except ScopeError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


async def get_scope_filter(
    branch_id: Optional[str] = None,
    department_id: Optional[str] = None,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_access_scope),
) -> ScopeFilter:
    try:
        return scope.read_filter(db, branch_id=branch_id, department_id=department_id)
    except ScopeError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
