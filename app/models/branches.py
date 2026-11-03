"""app/models/branches.py — Branch & Department entities."""
from datetime import datetime, timezone
from app.db.base_class import Base
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import relationship

# from app.db.database import Base
from app.db.mixins import BaseMixin

class Branch(BaseMixin, Base):
    __tablename__ = "branches"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String(150), nullable=False)
    code        = Column(String(50), unique=True, nullable=False, index=True)
    address     = Column(Text, nullable=True)
    phone       = Column(String(30), nullable=True)
    email       = Column(String(150), nullable=True)
    city        = Column(String(100), nullable=True)
    state       = Column(String(100), nullable=True)
    country     = Column(String(100), nullable=True, default="Nigeria")
    is_active   = Column(Boolean, default=True, nullable=False)
    # is_deleted  = Column(Boolean, default=False, nullable=False)
    # created_at  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    # updated_at  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    #                      onupdate=lambda: datetime.now(timezone.utc))

    departments      = relationship("BranchDepartment", back_populates="branch",
                                    cascade="all, delete-orphan")
    staff            = relationship("User", back_populates="branch",
                                    foreign_keys="User.branch_id")
    inventory_items  = relationship("InventoryItem", back_populates="branch")
    orders           = relationship("Order", back_populates="branch")


class Department(Base):
    __tablename__ = "departments"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String(150), nullable=False)
    code        = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    category    = Column(String(50), nullable=True)
    is_active   = Column(Boolean, default=True, nullable=False)
    is_deleted  = Column(Boolean, default=False, nullable=False)
    created_at  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                         onupdate=lambda: datetime.now(timezone.utc))

    branches = relationship("BranchDepartment", back_populates="department",
                            cascade="all, delete-orphan")


class BranchDepartment(Base):
    __tablename__ = "branch_departments"
    __table_args__ = (UniqueConstraint("branch_id", "department_id",
                                       name="uq_branch_department"),)

    id             = Column(Integer, primary_key=True, index=True)
    branch_id      = Column(Integer, ForeignKey("branches.id", ondelete="CASCADE"),
                            nullable=False)
    department_id  = Column(Integer, ForeignKey("departments.id", ondelete="CASCADE"),
                            nullable=False)
    is_primary     = Column(Boolean, default=False, nullable=False)
    manager_id     = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                            nullable=True)
    created_at     = Column(DateTime(timezone=True),
                            default=lambda: datetime.now(timezone.utc))

    branch     = relationship("Branch", back_populates="departments")
    department = relationship("Department", back_populates="branches")
    manager    = relationship("User", foreign_keys=[manager_id])

