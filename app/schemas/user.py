# app/schemas/user.py
from pydantic import BaseModel, EmailStr
from typing import Optional, List
import uuid


class UserUpdate(BaseModel):
    names: Optional[str] = None
    phone: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None


class UserRead(BaseModel):
    id: uuid.UUID
    username: str
    email: str
    names: Optional[str]
    phone: Optional[str]
    avatar_url: Optional[str]
    bio: Optional[str]
    is_active: bool
    is_verified: bool
    roles: List[str] = []

    model_config = {"from_attributes": True}


class UserAdminUpdate(BaseModel):
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None
    names: Optional[str] = None
    phone: Optional[str] = None
