# v2 - with user_id and better relationships
# app/models/category.py
from typing import List, Optional
from sqlalchemy import String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import UUIDMixin, TimestampMixin, SoftDeleteMixin


class Category(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    desc: Mapped[Optional[str]] = mapped_column(Text)
    dept: Mapped[str] = mapped_column(String(50), nullable=False, default="general")

    # USER TRACKING
    user_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # org
    # ORGANIZATION SCOPING
    organization_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # organization = relationship("Organization", backr="categories")
    organization = relationship(
        "Organization",
        back_populates="categories",
    )

    # ── BRANCH / DEPARTMENT SCOPING (nullable for rolling deploys; the app layer always sets them) ──
    branch_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    department_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    branch = relationship("Branch", foreign_keys=[branch_id])
    department = relationship("Department", foreign_keys=[department_id])

    # Hierarchical: parent_id NULL = root category
    parent_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    user = relationship("User", backref="categories")

    children: Mapped[List["Category"]] = relationship(
        "Category",
        back_populates="parent",
        foreign_keys=[parent_id],
        cascade="all, delete",
    )

    parent: Mapped[Optional["Category"]] = relationship(
        "Category",
        back_populates="children",
        remote_side="Category.id",
        foreign_keys=[parent_id],
    )

    items: Mapped[List["Items"]] = relationship(
        "Items",
        back_populates="category",
    )

    def get_summary(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "desc": self.desc,
            "dept": self.dept,
            "organization_id": str(self.organization_id),
            "branch_id": str(self.branch_id) if self.branch_id else None,
            "branch_name": self.branch.name if self.branch else None,
            "department_id": str(self.department_id) if self.department_id else None,
            "department_name": self.department.name if self.department else None,
            "parent_id": str(self.parent_id) if self.parent_id else None,
            "parent_name": self.parent.name if self.parent else None,
            "items_count": len(self.items) if self.items else 0,
            "created_by": str(self.user_id) if self.user_id else None,  # added
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<Category(name={self.name}, dept={self.dept})>"

