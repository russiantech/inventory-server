# app/models/items.py
from typing import List, Optional
from sqlalchemy import (
    String, Text, Integer, Boolean, Numeric, 
    ForeignKey, JSON, DateTime
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime

from app.db.base_class import Base
from app.db.mixins import UUIDMixin, TimestampMixin, SoftDeleteMixin


class Items(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "items"

    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    sku: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    desc: Mapped[Optional[str]] = mapped_column(Text)
    dept: Mapped[str] = mapped_column(String(80), nullable=False, default="general")

    # Pricing
    c_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))   # cost price
    s_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)  # selling price

    # Stock
    initial_stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    in_stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # running balance

    disc: Mapped[int] = mapped_column(Integer, default=0)   # discount %
    status: Mapped[bool] = mapped_column(Boolean, default=True)

    # Extra attributes stored as JSON
    attributes: Mapped[Optional[dict]] = mapped_column(JSON)
    photos: Mapped[Optional[list]] = mapped_column(JSON)

    # ── NEW: deletion audit trail ───────────────────────────────────────
    deleted_by: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    delete_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # ─────────────────────────────────────────────────────────────────────
    
    # FK
    # organization_id: Mapped[Optional[UUID]] = mapped_column(
    #     UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True
    # )
    organization_id: Mapped[UUID] = mapped_column(
    UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization = relationship("Organization", back_populates="items")

    category_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    category: Mapped["Category"] = relationship("Category", back_populates="items")
    s_history: Mapped[List["StockHistory"]] = relationship(
        "StockHistory", back_populates="item", cascade="all, delete-orphan"
    )
    stock_edit_logs: Mapped[List["StockEditLog"]] = relationship(
        "StockEditLog", back_populates="item", cascade="all, delete-orphan"
    )
    sales: Mapped[List["Sales"]] = relationship(
        "Sales", back_populates="item", cascade="all, delete-orphan"
    )

    @property
    def stock_balance(self) -> int:
        """Running stock balance = in_stock (maintained by triggers/service)"""
        return self.in_stock

    def get_summary(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "sku": self.sku,
            "desc": self.desc,
            "dept": self.dept,
            "organization_id": str(self.organization_id),
            "c_price": float(self.c_price) if self.c_price else None,
            "s_price": float(self.s_price),
            "initial_stock": self.initial_stock,
            "in_stock": self.in_stock,
            "disc": self.disc,
            "status": self.status,
            "attributes": self.attributes,
            "photos": self.photos,
            "category_id": str(self.category_id),
            "category_name": self.category.name if self.category else None,
            "deleted_by": str(self.deleted_by) if self.deleted_by else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "delete_reason": self.delete_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<Items(name={self.name}, in_stock={self.in_stock})>"

