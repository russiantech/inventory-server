# app/schemas/branch.py
import uuid
from typing import List, Optional, Literal

from pydantic import BaseModel, field_validator


class BranchCreate(BaseModel):
    name: str
    code: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    description: Optional[str] = None
    departments: Optional[List[str]] = None  # initial departments; defaults to ["general"]

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Branch name cannot be empty")
        return v


class BranchUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class DepartmentCreate(BaseModel):
    branch_id: uuid.UUID
    name: str
    description: Optional[str] = None


class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class MemberAssign(BaseModel):
    user_id: uuid.UUID
    role: Literal["admin", "manager", "staff"] = "staff"
    department_id: Optional[uuid.UUID] = None  # None = whole branch
