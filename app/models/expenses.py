# app/models/expenses.py
from typing import Optional
from datetime import datetime
from sqlalchemy import String, Text, Numeric, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import UUIDMixin, TimestampMixin, SoftDeleteMixin


class Expenses(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "expenses"

    cost: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    dept: Mapped[str] = mapped_column(String(80), nullable=False, default="general")
    comment: Mapped[Optional[str]] = mapped_column(String(255))
    expense_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    user_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    def get_summary(self) -> dict:
        return {
            "id": str(self.id),
            "cost": float(self.cost),
            "dept": self.dept,
            "comment": self.comment,
            "expense_date": self.expense_date.isoformat() if self.expense_date else None,
            "user_id": str(self.user_id) if self.user_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
