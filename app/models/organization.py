# # app/models/organization.py
# from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
# from sqlalchemy.orm import relationship
# from datetime import datetime, timezone
# from sqlalchemy.dialects.postgresql import UUID
# # from app.db.database import Base
# from app.db.base_class import Base
# from app.db.mixins import UUIDMixin, TimestampMixin, SoftDeleteMixin


# # class Organization(Base):
# class Organization(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):

#     __tablename__ = "organizations"

#     # id = Column(Integer, primary_key=True, index=True)
#     name = Column(String(120), nullable=False)
#     slug = Column(String(60), unique=True, index=True, nullable=False)
    
#     # Subscription / Plan
#     plan = Column(String(20), default="free")  # free, starter, pro, enterprise
#     max_users = Column(Integer, default=5)     # Plan-based user limit
#     max_products = Column(Integer, default=100) # Plan-based product limit
    
#     # Features
#     allow_public_signup = Column(Boolean, default=False)  # Admin can toggle
#     is_active = Column(Boolean, default=True)
#     is_paused = Column(Boolean, default=False)  # Admin can pause org
    
#     # Billing
#     subscription_status = Column(String(20), default="trialing")  # trialing, active, past_due, canceled
#     subscription_ends_at = Column(DateTime, nullable=True)
    
#     # Relations
# #     owner_id = Column(
# #     UUID(as_uuid=True),
# #     ForeignKey("users.id"),
# #     nullable=True
# # )
# #     owner = relationship("User", foreign_keys=[owner_id], back_populates="owned_organization")
    
# #     users = relationship("User", back_populates="organization", foreign_keys="User.organization_id")
    
#     # This FK creates the cycle because User already FKs to organizations
#     # Add use_alter=True to break it
#     owner_id: Mapped[Optional[UUID]] = mapped_column(
#         UUID(as_uuid=True),
#         ForeignKey(
#             "users.id", 
#             ondelete="SET NULL",
#             use_alter=True,           # ← BREAKS THE CYCLE
#             name="fk_organization_owner"  # named constraint required with use_alter
#         ),
#         nullable=True,
#         index=True,
#     )
    
#     owner = relationship(
#         "User",
#         foreign_keys=[owner_id],
#         back_populates="owned_organization",
#         uselist=False,
#     )
    
#     users = relationship(
#         "User",
#         foreign_keys="User.organization_id",
#         back_populates="organization",
#     )
    
#     # categories = relationship("Category", backref="organization", cascade="all, delete")
#     # sales = relationship("Sales", backref="organization", cascade="all, delete")
#     # stock_history = relationship("StockHistory", backref="organization", cascade="all, delete")
#     # expenses = relationship("Expenses", backref="organization", cascade="all, delete")
#     # items = relationship("Items", backref="organization", cascade="all, delete")

#     def get_summary(self):
#         return {
#             "id": self.id,
#             "name": self.name,
#             "slug": self.slug,
#             "plan": self.plan,
#             "max_users": self.max_users,
#             "allow_public_signup": self.allow_public_signup,
#             "is_active": self.is_active,
#             "subscription_status": self.subscription_status,
#         }







# v2
# # app/models/organization.py
# from typing import Optional, List
# from sqlalchemy import (
#     String, Integer, Boolean, DateTime, ForeignKey
# )
# from sqlalchemy.orm import Mapped, mapped_column, relationship
# from sqlalchemy.dialects.postgresql import UUID
# from datetime import datetime, timezone

# from app.db.base_class import Base
# from app.db.mixins import UUIDMixin, TimestampMixin, SoftDeleteMixin


# class Organization(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
#     __tablename__ = "organizations"

#     name: Mapped[str] = mapped_column(String(120), nullable=False)
#     slug: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    
#     # Subscription / Plan
#     plan: Mapped[str] = mapped_column(String(20), default="free")
#     max_users: Mapped[int] = mapped_column(Integer, default=5)
#     max_products: Mapped[int] = mapped_column(Integer, default=100)
    
#     # Features
#     allow_public_signup: Mapped[bool] = mapped_column(Boolean, default=False)
#     is_active: Mapped[bool] = mapped_column(Boolean, default=True)
#     is_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    
#     # Billing
#     subscription_status: Mapped[str] = mapped_column(String(20), default="trialing")
#     subscription_ends_at: Mapped[Optional[datetime]] = mapped_column(
#         DateTime(timezone=True), nullable=True
#     )
    
#     # ── Owner FK (use_alter breaks circular dependency with users table) ──
#     owner_id: Mapped[Optional[UUID]] = mapped_column(
#         UUID(as_uuid=True),
#         ForeignKey(
#             "users.id",
#             ondelete="SET NULL",
#             use_alter=True,
#             name="fk_organization_owner"
#         ),
#         nullable=True,
#         index=True,
#     )
    
#     # ── Relationships ──
#     owner: Mapped[Optional["User"]] = relationship(
#         "User",
#         foreign_keys=[owner_id],
#         back_populates="owned_organization",
#         uselist=False,
#     )
    
#     # Use back_populates (not backref) to match User.organization
#     users: Mapped[List["User"]] = relationship(
#         "User",
#         foreign_keys="User.organization_id",
#         back_populates="organization",
#     )
    
#     # Other relationships — use back_populates consistently
#     categories: Mapped[List["Category"]] = relationship(
#         "Category", back_populates="organization", cascade="all, delete-orphan"
#     )
#     sales: Mapped[List["Sales"]] = relationship(
#         "Sales", back_populates="organization", cascade="all, delete-orphan"
#     )
#     stock_history: Mapped[List["StockHistory"]] = relationship(
#         "StockHistory", back_populates="organization", cascade="all, delete-orphan"
#     )
#     expenses: Mapped[List["Expenses"]] = relationship(
#         "Expenses", back_populates="organization", cascade="all, delete-orphan"
#     )
#     items: Mapped[List["Items"]] = relationship(
#         "Items", back_populates="organization", cascade="all, delete-orphan"
#     )

#     def get_summary(self) -> dict:
#         return {
#             "id": str(self.id),
#             "name": self.name,
#             "slug": self.slug,
#             "plan": self.plan,
#             "max_users": self.max_users,
#             "max_products": self.max_products,
#             "allow_public_signup": self.allow_public_signup,
#             "is_active": self.is_active,
#             "is_paused": self.is_paused,
#             "subscription_status": self.subscription_status,
#             "subscription_ends_at": self.subscription_ends_at.isoformat() if self.subscription_ends_at else None,
#             "owner_id": str(self.owner_id) if self.owner_id else None,
#             "created_at": self.created_at.isoformat() if self.created_at else None,
#             "updated_at": self.updated_at.isoformat() if self.updated_at else None,
#         }


# v2
# app/models/organization.py
from typing import Optional, List
from sqlalchemy import (
    String, Integer, Boolean, DateTime, ForeignKey
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone

from app.db.base_class import Base
from app.db.mixins import UUIDMixin, TimestampMixin, SoftDeleteMixin


class Organization(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    
    # Subscription / Plan — nullable=False with server_default for existing rows
    # plan: Mapped[str] = mapped_column(String(20), nullable=False, server_default="free")
    # max_users: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    # max_products: Mapped[int] = mapped_column(Integer, nullable=False, server_default="100")
    # 
    plan: Mapped[Optional[str]] = mapped_column(String(20), default="free")
    max_users: Mapped[Optional[int]] = mapped_column(Integer, default=5)
    max_products: Mapped[Optional[int]] = mapped_column(Integer, default=100)
    
    # Features
    allow_public_signup: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    is_paused: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    
    # Billing
    subscription_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="trialing")
    subscription_ends_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    # ── Owner FK (use_alter breaks circular dependency) ──
    owner_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_organization_owner"
        ),
        nullable=True,
        index=True,
    )
    
    # ── Relationships ──
    owner: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[owner_id],
        back_populates="owned_organization",
        uselist=False,
    )
    
    users: Mapped[List["User"]] = relationship(
        "User",
        foreign_keys="User.organization_id",
        back_populates="organization",
    )
    
    categories: Mapped[List["Category"]] = relationship(
        "Category", back_populates="organization", cascade="all, delete-orphan"
    )
    sales: Mapped[List["Sales"]] = relationship(
        "Sales", back_populates="organization", cascade="all, delete-orphan"
    )
    stock_history: Mapped[List["StockHistory"]] = relationship(
        "StockHistory", back_populates="organization", cascade="all, delete-orphan"
    )
    expenses: Mapped[List["Expenses"]] = relationship(
        "Expenses", back_populates="organization", cascade="all, delete-orphan"
    )
    items: Mapped[List["Items"]] = relationship(
        "Items", back_populates="organization", cascade="all, delete-orphan"
    )

    def get_summary(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "slug": self.slug,
            "plan": self.plan,
            "max_users": self.max_users,
            "max_products": self.max_products,
            "allow_public_signup": self.allow_public_signup,
            "is_active": self.is_active,
            "is_paused": self.is_paused,
            "subscription_status": self.subscription_status,
            "subscription_ends_at": self.subscription_ends_at.isoformat() if self.subscription_ends_at else None,
            "owner_id": str(self.owner_id) if self.owner_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

