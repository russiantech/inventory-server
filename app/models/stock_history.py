# app/models/stock_history.py
from typing import Optional
from datetime import datetime
from sqlalchemy import String, Text, Integer, Boolean, Numeric, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import UUIDMixin, TimestampMixin, SoftDeleteMixin


class StockHistory(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """
    Records every stock movement (in/adjustment) for an item.
    stock_balance = initial_stock + SUM(quantity_in) 
    """
    __tablename__ = "stock_history"

    item_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    quantity_in: Mapped[int] = mapped_column(Integer, nullable=False)   # new stock added
    stock_before: Mapped[int] = mapped_column(Integer, nullable=False)  # stock before this entry
    stock_after: Mapped[int] = mapped_column(Integer, nullable=False)   # stock after this entry

    unit_cost: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))  # cost per unit at time of entry
    date_in: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    desc: Mapped[Optional[str]] = mapped_column(Text)
    reference: Mapped[Optional[str]] = mapped_column(String(100))       # e.g. PO number

    # Relationships
    item: Mapped["Items"] = relationship("Items", back_populates="s_history")
    recorded_by: Mapped[Optional["User"]] = relationship(
        "User", back_populates="stock_entries", foreign_keys=[user_id]
    )
    
    # ORGANIZATION SCOPING
    organization_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization = relationship("Organization", backref="stock_history")

    def get_summary(self) -> dict:
        return {
            "id": str(self.id),
            "item_id": str(self.item_id),
            "item_name": self.item.name if self.item else None,
            "user_id": str(self.user_id) if self.user_id else None,
            "recorded_by": self.recorded_by.names or self.recorded_by.username if self.recorded_by else None,
            "quantity_in": self.quantity_in,
            "stock_before": self.stock_before,
            "stock_after": self.stock_after,
            "unit_cost": float(self.unit_cost) if self.unit_cost else None,
            "date_in": self.date_in.isoformat() if self.date_in else None,
            "desc": self.desc,
            "reference": self.reference,
            "organization_id": str(self.organization_id),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<StockHistory(item_id={self.item_id}, qty_in={self.quantity_in})>"
