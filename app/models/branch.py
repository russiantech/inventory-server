# app/models/branch.py
"""
Branch / Department / BranchMembership
--------------------------------------
Hierarchy:  Organization (company) -> Branch (unit / subsidiary) -> Department

* A Branch operates independently (its own categories, products, stock, sales,
  expenses) while remaining under the Organization, which can see everything
  collectively or per branch.
* A BranchMembership assigns a user to a branch (optionally limited to one
  department) with a branch-level role: admin | manager | staff.
"""
from typing import Optional, List

from sqlalchemy import (
    String, Text, Boolean, ForeignKey, UniqueConstraint, Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import UUIDMixin, TimestampMixin, SoftDeleteMixin

BRANCH_ROLES = ("admin", "manager", "staff")
BRANCH_ROLE_RANK = {"staff": 1, "manager": 2, "admin": 3}


class Branch(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "branches"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_branch_org_code"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(30))
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    organization = relationship("Organization")
    departments: Mapped[List["Department"]] = relationship(
        "Department", back_populates="branch", cascade="all, delete-orphan"
    )
    memberships: Mapped[List["BranchMembership"]] = relationship(
        "BranchMembership", back_populates="branch", cascade="all, delete-orphan"
    )

    def get_summary(self, include_counts: bool = False) -> dict:
        data = {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "name": self.name,
            "code": self.code,
            "address": self.address,
            "phone": self.phone,
            "description": self.description,
            "is_active": self.is_active,
            "is_default": self.is_default,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_counts:
            data["departments"] = [d.get_summary() for d in self.departments if not d.deleted]
            data["members_count"] = len(self.memberships)
        return data

    def __repr__(self) -> str:
        return f"<Branch(code={self.code}, name={self.name})>"


class Department(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("branch_id", "name", name="uq_department_branch_name"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    branch: Mapped["Branch"] = relationship("Branch", back_populates="departments")

    def get_summary(self) -> dict:
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "branch_id": str(self.branch_id),
            "name": self.name,
            "description": self.description,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<Department(name={self.name}, branch_id={self.branch_id})>"


class BranchMembership(UUIDMixin, TimestampMixin, Base):
    """Assigns a user to a branch (optionally one department) with a branch role."""
    __tablename__ = "branch_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "branch_id", "department_id", name="uq_membership_user_branch_dept"),
        Index("ix_membership_user_branch", "user_id", "branch_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # NULL = whole branch; set = limited to this department
    department_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="CASCADE"), nullable=True, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="staff", server_default="staff")
    assigned_by: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    user = relationship("User", foreign_keys=[user_id])
    branch: Mapped["Branch"] = relationship("Branch", back_populates="memberships")
    department = relationship("Department")

    def get_summary(self) -> dict:
        u = self.user
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "username": u.username if u else None,
            "names": u.names if u else None,
            "email": u.email if u else None,
            "branch_id": str(self.branch_id),
            "branch_name": self.branch.name if self.branch else None,
            "department_id": str(self.department_id) if self.department_id else None,
            "department_name": self.department.name if self.department else None,
            "role": self.role,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
