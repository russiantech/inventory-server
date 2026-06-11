# app/schemas/inventory.py
from pydantic import BaseModel, field_validator
from typing import Optional, Any
import uuid


class CategoryCreate(BaseModel):
    name: str
    desc: Optional[str] = None
    dept: str = "general"
    parent_id: Optional[uuid.UUID] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Category name cannot be empty")
        return v


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    desc: Optional[str] = None
    dept: Optional[str] = None
    parent_id: Optional[uuid.UUID] = None
    


class ItemCreate(BaseModel):
    name: str
    sku: Optional[str] = None
    desc: Optional[str] = None
    dept: str = "general"
    c_price: Optional[float] = None
    s_price: float
    disc: int = 0
    in_stock: int = 0   # alias — service prefers initial_stock
    category_id: Optional[uuid.UUID] = None
    photos: Optional[Any] = None
    attributes: Optional[Any] = None
    color: Optional[Any] = None
    size: Optional[Any] = None
    status: Optional[bool] = True  # active by default
    initial_stock: Optional[int] = 0

    @field_validator("s_price")
    @classmethod
    def price_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Selling price cannot be negative")
        return v


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    sku: Optional[str] = None
    desc: Optional[str] = None
    dept: Optional[str] = None
    c_price: Optional[float] = None
    s_price: Optional[float] = None
    disc: Optional[int] = None
    status: Optional[bool] = None
    category_id: Optional[uuid.UUID] = None
    photos: Optional[Any] = None
    attributes: Optional[Any] = None
