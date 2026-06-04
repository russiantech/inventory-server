# app/models/sales.py
from typing import Optional
from datetime import datetime
from sqlalchemy import String, Text, Integer, Boolean, Numeric, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import UUIDMixin, TimestampMixin, SoftDeleteMixin


class Sales(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """
    Records a sale transaction.
    stock_balance (post-sale) = item.in_stock - qty_sold
    profit per line = (unit_price - item.c_price) * qty_sold
    """
    __tablename__ = "sales"

    item_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    qty_sold: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)   # selling price used
    total_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)  # qty_sold * unit_price
    cost_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))         # c_price snapshot at sale time
    profit: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))             # total_price - (cost_price * qty)

    stock_before: Mapped[int] = mapped_column(Integer, nullable=False)          # stock before sale
    stock_after: Mapped[int] = mapped_column(Integer, nullable=False)           # stock after sale

    dept: Mapped[str] = mapped_column(String(80), nullable=False, default="general")
    comment: Mapped[Optional[str]] = mapped_column(String(255))
    sale_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    item: Mapped["Items"] = relationship("Items", back_populates="sales")
    recorded_by: Mapped[Optional["User"]] = relationship(
        "User", back_populates="sales", foreign_keys=[user_id]
    )

    def get_summary(self) -> dict:
        return {
            "id": str(self.id),
            "item_id": str(self.item_id),
            "item_name": self.item.name if self.item else None,
            "item_sku": self.item.sku if self.item else None,
            "category": self.item.category.name if self.item and self.item.category else None,
            "user_id": str(self.user_id) if self.user_id else None,
            "recorded_by": self.recorded_by.names or self.recorded_by.username if self.recorded_by else None,
            "qty_sold": self.qty_sold,
            "unit_price": float(self.unit_price),
            "total_price": float(self.total_price),
            "cost_price": float(self.cost_price) if self.cost_price else None,
            "profit": float(self.profit) if self.profit else None,
            "stock_before": self.stock_before,
            "stock_after": self.stock_after,
            "dept": self.dept,
            "comment": self.comment,
            "sale_date": self.sale_date.isoformat() if self.sale_date else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<Sales(item_id={self.item_id}, qty_sold={self.qty_sold})>"
