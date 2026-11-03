"""app/schemas/branches.py — Pydantic schemas for branch & department ops."""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


# ─── Department ─────────────────────────────────────────────────────────────

class DepartmentBase(BaseModel):
    name: str
    code: str
    description: Optional[str] = None
    category: Optional[str] = None


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None


class DepartmentOut(DepartmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    is_deleted: bool
    created_at: datetime
    updated_at: Optional[datetime] = None


# ─── Branch ─────────────────────────────────────────────────────────────────

class BranchBase(BaseModel):
    name: str
    code: str
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = "Nigeria"


class BranchCreate(BranchBase):
    department_ids: Optional[List[int]] = []


class BranchUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    is_active: Optional[bool] = None


class BranchDepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    department_id: int
    department_name: str
    department_code: str
    is_primary: bool
    manager_id: Optional[int] = None
    created_at: datetime


class BranchOut(BranchBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    is_deleted: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    departments: List[BranchDepartmentOut] = []


class BranchListOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    city: Optional[str] = None
    state: Optional[str] = None
    is_active: bool
    created_at: datetime


# ─── Branch-Department Link ─────────────────────────────────────────────────

class BranchDepartmentCreate(BaseModel):
    department_id: int
    is_primary: bool = False

