# app/models/stock_edit_log.py
from typing import Optional
from datetime import datetime
from sqlalchemy import String, Text, Integer, Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.base_class import Base
from app.db.mixins import UUIDMixin, TimestampMixin


class StockEditLog(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "stock_edit_logs"

    # Link to the original stock entry
    stock_entry_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stock_history.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Context
    item_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id"), nullable=False, index=True
    )
    user_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    organization_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )

    # Old vs New values
    old_quantity_in: Mapped[int] = mapped_column(Integer, nullable=False)
    new_quantity_in: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_delta: Mapped[int] = mapped_column(Integer, nullable=False)

    old_unit_cost: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    new_unit_cost: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))

    old_desc: Mapped[Optional[str]] = mapped_column(Text)
    new_desc: Mapped[Optional[str]] = mapped_column(Text)

    old_reference: Mapped[Optional[str]] = mapped_column(String(100))
    new_reference: Mapped[Optional[str]] = mapped_column(String(100))

    old_stock_after: Mapped[int] = mapped_column(Integer, nullable=False)
    new_stock_after: Mapped[int] = mapped_column(Integer, nullable=False)

    edit_reason: Mapped[str] = mapped_column(Text, nullable=False, default="Stock entry edited")

    # Relationships
    stock_entry: Mapped["StockHistory"] = relationship("StockHistory", back_populates="edit_logs")
    item: Mapped["Items"] = relationship("Items", back_populates="stock_edit_logs")
    user: Mapped[Optional["User"]] = relationship("User", back_populates="stock_edits")

    def get_summary(self) -> dict:
        return {
            "id": str(self.id),
            "stock_entry_id": str(self.stock_entry_id),
            "item_id": str(self.item_id),
            "item_name": self.item.name if self.item else None,
            "user_id": str(self.user_id) if self.user_id else None,
            "edited_by": self.user.names or self.user.username if self.user else None,
            "old_quantity_in": self.old_quantity_in,
            "new_quantity_in": self.new_quantity_in,
            "quantity_delta": self.quantity_delta,
            "old_unit_cost": float(self.old_unit_cost) if self.old_unit_cost else None,
            "new_unit_cost": float(self.new_unit_cost) if self.new_unit_cost else None,
            "old_desc": self.old_desc,
            "new_desc": self.new_desc,
            "old_reference": self.old_reference,
            "new_reference": self.new_reference,
            "old_stock_after": self.old_stock_after,
            "new_stock_after": self.new_stock_after,
            "edit_reason": self.edit_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

