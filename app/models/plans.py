# app/models/plan.py
"""
Subscription plans & organization subscriptions.

- Plan: a billable tier (e.g. "Free", "Starter", "Pro", "Enterprise"),
  managed exclusively by super_admins.
- Subscription: links an Organization to a Plan, tracks status
  (active / canceled / past_due / trialing) and billing period.

Add to your models __init__ / metadata import list so Alembic picks these up:
    from app.models.plan import Plan, Subscription
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Boolean, Integer, Numeric, DateTime, ForeignKey, Enum, Text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class BillingInterval(str, enum.Enum):
    monthly = "monthly"
    yearly = "yearly"


class SubscriptionStatus(str, enum.Enum):
    pending = "pending"        # checkout initialized, awaiting Paystack confirmation
    trialing = "trialing"
    active = "active"
    past_due = "past_due"
    canceled = "canceled"
    expired = "expired"


class Plan(Base):
    """A subscription tier. Created/edited by super_admins only."""
    __tablename__ = "plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, nullable=False)          # e.g. "Free", "Pro"
    slug = Column(String(100), unique=True, nullable=False)          # e.g. "free", "pro"
    description = Column(Text, nullable=True)

    price_monthly = Column(Numeric(10, 2), nullable=False, default=0)
    price_yearly = Column(Numeric(10, 2), nullable=False, default=0)
    currency = Column(String(3), nullable=False, default="NGN")

    max_users = Column(Integer, nullable=False, default=5)
    max_products = Column(Integer, nullable=True)          # None = unlimited
    max_warehouses = Column(Integer, nullable=True)        # None = unlimited
    storage_quota_mb = Column(Integer, nullable=False, default=512)

    # Paystack "Plan" objects (created on Paystack — interval-specific).
    # Required for paid plans so subscribe() can hand Paystack a plan code.
    paystack_plan_code_monthly = Column(String(100), nullable=True)
    paystack_plan_code_yearly = Column(String(100), nullable=True)

    features = Column(Text, nullable=True)   # JSON-encoded list of feature flags / bullet points

    is_active = Column(Boolean, default=True, nullable=False)   # plan available for new subscriptions
    is_default = Column(Boolean, default=False, nullable=False) # auto-assigned to new orgs

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                         onupdate=lambda: datetime.now(timezone.utc))

    subscriptions = relationship("Subscription", back_populates="plan")

    def get_summary(self) -> dict:
        import json
        return {
            "id": str(self.id),
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "price_monthly": float(self.price_monthly),
            "price_yearly": float(self.price_yearly),
            "currency": self.currency,
            "max_users": self.max_users,
            "max_products": self.max_products,
            "max_warehouses": self.max_warehouses,
            "storage_quota_mb": self.storage_quota_mb,
            "features": json.loads(self.features) if self.features else [],
            "is_active": self.is_active,
            "is_default": self.is_default,
            "paystack_plan_code_monthly": self.paystack_plan_code_monthly,
            "paystack_plan_code_yearly": self.paystack_plan_code_yearly,
            "is_free": float(self.price_monthly) == 0 and float(self.price_yearly) == 0,
        }


class Subscription(Base):
    """Links an Organization to a Plan."""
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, unique=True)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("plans.id"), nullable=False)

    status = Column(Enum(SubscriptionStatus), nullable=False, default=SubscriptionStatus.trialing)
    billing_interval = Column(Enum(BillingInterval), nullable=False, default=BillingInterval.monthly)

    current_period_start = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    canceled_at = Column(DateTime(timezone=True), nullable=True)

    # Paystack linkage
    paystack_customer_code = Column(String(100), nullable=True)
    paystack_subscription_code = Column(String(100), nullable=True)
    paystack_email_token = Column(String(255), nullable=True)   # required to disable/enable subscription
    pending_reference = Column(String(100), nullable=True)      # transaction ref awaiting verification
    last_payment_reference = Column(String(100), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                         onupdate=lambda: datetime.now(timezone.utc))

    organization = relationship("Organization", backref="subscription", uselist=False)
    plan = relationship("Plan", back_populates="subscriptions")

    def get_summary(self) -> dict:
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "plan": self.plan.get_summary() if self.plan else None,
            "status": self.status.value if hasattr(self.status, "value") else self.status,
            "billing_interval": self.billing_interval.value if hasattr(self.billing_interval, "value") else self.billing_interval,
            "current_period_start": self.current_period_start.isoformat() if self.current_period_start else None,
            "current_period_end": self.current_period_end.isoformat() if self.current_period_end else None,
            "canceled_at": self.canceled_at.isoformat() if self.canceled_at else None,
            "is_paystack_managed": bool(self.paystack_subscription_code),
            "pending_reference": self.pending_reference,
        }

