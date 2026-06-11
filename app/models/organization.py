# app/models/organization.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import UUID
# from app.db.database import Base
from app.db.base_class import Base
from app.db.mixins import UUIDMixin, TimestampMixin, SoftDeleteMixin


# class Organization(Base):
class Organization(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):

    __tablename__ = "organizations"

    # id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    slug = Column(String(60), unique=True, index=True, nullable=False)
    
    # Subscription / Plan
    plan = Column(String(20), default="free")  # free, starter, pro, enterprise
    max_users = Column(Integer, default=5)     # Plan-based user limit
    max_products = Column(Integer, default=100) # Plan-based product limit
    
    # Features
    allow_public_signup = Column(Boolean, default=False)  # Admin can toggle
    is_active = Column(Boolean, default=True)
    is_paused = Column(Boolean, default=False)  # Admin can pause org
    
    # Billing
    subscription_status = Column(String(20), default="trialing")  # trialing, active, past_due, canceled
    subscription_ends_at = Column(DateTime, nullable=True)
    
    # Relations
    # owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    # owner_id = Column(
    #     UUID(as_uuid=True),
    #     ForeignKey("users.id")
    # )
    
    owner_id = Column(
    UUID(as_uuid=True),
    ForeignKey("users.id"),
    nullable=True
)
    owner = relationship("User", foreign_keys=[owner_id], back_populates="owned_organization")
    
    users = relationship("User", back_populates="organization", foreign_keys="User.organization_id")
    
    
    # categories = relationship("Category", backref="organization", cascade="all, delete")
    # sales = relationship("Sales", backref="organization", cascade="all, delete")
    # stock_history = relationship("StockHistory", backref="organization", cascade="all, delete")
    # expenses = relationship("Expenses", backref="organization", cascade="all, delete")
    # items = relationship("Items", backref="organization", cascade="all, delete")

    def get_summary(self):
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "plan": self.plan,
            "max_users": self.max_users,
            "allow_public_signup": self.allow_public_signup,
            "is_active": self.is_active,
            "subscription_status": self.subscription_status,
        }

