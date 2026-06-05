# app/api/v1/roles.py
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.api.deps.users import get_db, get_current_user
from app.api.deps.rbac import require_roles
from app.models.rbac import Role
from app.utils.responses import api_response

logger = logging.getLogger(__name__)
router = APIRouter()


class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    is_default: bool = False


@router.get("", summary="List all roles [admin]", dependencies=[Depends(require_roles("admin", "super_admin"))])
async def list_roles(db: Session = Depends(get_db)):
    roles = db.query(Role).order_by(Role.name).all()
    return api_response(True, "Roles fetched.", data=[r.get_summary() for r in roles])


@router.post("", summary="Create role [admin]", dependencies=[Depends(require_roles("admin", "super_admin"))], status_code=201)
async def create_role(data: RoleCreate, db: Session = Depends(get_db)):
    existing = db.query(Role).filter(Role.name == data.name).first()
    if existing:
        return api_response(False, f"Role '{data.name}' already exists.", status_code=409)
    role = Role(**data.model_dump())
    db.add(role)
    db.commit()
    db.refresh(role)
    return api_response(True, f"Role '{role.name}' created.", data=role.get_summary(), status_code=201)


@router.delete("/{role_id}", summary="Delete role [admin]", dependencies=[Depends(require_roles("admin", "super_admin"))])
async def delete_role(role_id: str, db: Session = Depends(get_db)):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        return api_response(False, "Role not found.", status_code=404)
    if role.name in ("admin", "super_admin", "staff"):
        return api_response(False, "Cannot delete system roles.", status_code=400)
    db.delete(role)
    db.commit()
    return api_response(True, f"Role '{role.name}' deleted.")
