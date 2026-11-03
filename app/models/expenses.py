# app/models/expenses.py
from typing import Optional
from datetime import datetime
from app.models.user import User
from sqlalchemy import String, Text, Numeric, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import UUIDMixin, TimestampMixin, SoftDeleteMixin


class Expenses(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "expenses"
    
    organization_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    cost: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    dept: Mapped[str] = mapped_column(String(80), nullable=False, default="general")
    comment: Mapped[Optional[str]] = mapped_column(String(255))
    expense_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    user_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    
    organization = relationship("Organization", back_populates="expenses")

    # ── BRANCH / DEPARTMENT SCOPING (nullable for rolling deploys; the app layer always sets them) ──
    branch_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    department_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    branch = relationship("Branch", foreign_keys=[branch_id])
    department = relationship("Department", foreign_keys=[department_id])
    recorded_by: Mapped[Optional["User"]] = relationship(
        "User", back_populates="expenses", foreign_keys=[user_id]
    )

    def get_summary(self) -> dict:
        return {
            "id": str(self.id),
            "cost": float(self.cost),
            "dept": self.dept,
            "branch_id": str(self.branch_id) if self.branch_id else None,
            "branch_name": self.branch.name if self.branch else None,
            "department_id": str(self.department_id) if self.department_id else None,
            "department_name": self.department.name if self.department else None,
            "comment": self.comment,
            "expense_date": self.expense_date.isoformat() if self.expense_date else None,
            "user_id": str(self.user_id) if self.user_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
