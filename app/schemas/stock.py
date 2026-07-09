# app/api/v1/stock.py
from pydantic import BaseModel, field_validator
from typing import Optional

class StockInSchema(BaseModel):
    item_id: str
    quantity_in: int
    unit_cost: Optional[float] = None
    desc: Optional[str] = None
    reference: Optional[str] = None
    # organization_id intentionally removed — derived server-side from the
    # authenticated user; clients must never supply it.

    @field_validator("quantity_in")
    @classmethod
    def qty_positive(cls, v):
        if v <= 0:
            raise ValueError("Quantity must be greater than zero")
        return v

# class StockUpdateSchema(BaseModel):
#     quantity_in: int
#     unit_cost: Optional[float] = None
#     desc: Optional[str] = None
#     reference: Optional[str] = None

#     @field_validator("quantity_in")
#     @classmethod
#     def qty_positive(cls, v):
#         if v <= 0:
#             raise ValueError("Quantity must be greater than zero")
#         return v

class StockUpdateSchema(BaseModel):
    quantity_in: int
    edit_reason: str
    unit_cost: Optional[float] = None
    desc: Optional[str] = None
    reference: Optional[str] = None

    @field_validator("quantity_in")
    @classmethod
    def qty_positive(cls, v):
        if v <= 0:
            raise ValueError("Quantity must be greater than zero")
        return v

    @field_validator("edit_reason")
    @classmethod
    def reason_required(cls, v):
        if not v or not v.strip():
            raise ValueError("A reason for this edit is required")
        return v

class StockReverseSchema(BaseModel):
    reason: str

