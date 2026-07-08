# app/models/user.py
import datetime
from typing import List, Optional
# from uuid import UUID
from sqlalchemy import Text, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.base_class import Base
from app.db.mixins import UUIDMixin, TimestampMixin, SoftDeleteMixin
from app.core.security.password import hash_password, verify_password
from app.models.association_tables import user_roles


class User(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    names: Mapped[Optional[str]] = mapped_column(String(100))
    phone: Mapped[Optional[str]] = mapped_column(String(20), unique=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    bio: Mapped[Optional[str]] = mapped_column(Text)
    ip: Mapped[Optional[str]] = mapped_column(String(50))
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    # After email_verified, before relationships:
    last_seen: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_online: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    
    # ── Organization ──

    # organization_id: Mapped[Optional[str]] = mapped_column(
    #     UUID(as_uuid=True),
    #     ForeignKey("organizations.id")
    # )
    organization_id: Mapped[Optional[UUID]] = mapped_column(
    UUID(as_uuid=True),
    ForeignKey("organizations.id", ondelete="SET NULL"),
    nullable=True,
    index=True,
    )
    
    organization = relationship("Organization", back_populates="users", foreign_keys=[organization_id])
    
    # is_org_admin = Mapped[bool] = Mapped(Boolean, default=False)  # Can manage org users/settings
    is_org_admin: Mapped[bool] = mapped_column(Boolean, default=False) # Flag to indicate if user is an organization admin
    
    # BREAK THE CYCLE: use_alter=True on the reverse relationship
    owned_organization = relationship(
        "Organization",
        foreign_keys="Organization.owner_id",
        back_populates="owner",
        uselist=False,
    )
    roles: Mapped[List["Role"]] = relationship(
        "Role", secondary=user_roles, back_populates="users", lazy="selectin"
    )
    stock_entries: Mapped[List["StockHistory"]] = relationship(
        "StockHistory", back_populates="recorded_by", foreign_keys="StockHistory.user_id"
    )
    stock_edits: Mapped[List["StockEditLog"]] = relationship(
        "StockEditLog", back_populates="user", foreign_keys="StockEditLog.user_id"
    )
    sales: Mapped[List["Sales"]] = relationship(
        "Sales", back_populates="recorded_by", foreign_keys="Sales.user_id"
    )
    expenses: Mapped[List["Expenses"]] = relationship(
        "Expenses", back_populates="recorded_by", foreign_keys="Expenses.user_id"
    )

    def set_password(self, password: str) -> None:
        if not password:
            raise ValueError("Password cannot be empty")
        self.password = hash_password(password)

    def check_password(self, password: str) -> bool:
        if not self.password:
            return False
        return verify_password(password, self.password)

    @property
    def role_names(self) -> List[str]:
        if not self.roles:
            return ["staff"]
        return [r.name for r in self.roles]

    @property
    def is_admin(self) -> bool:
        return any(r.name in ("admin", "super_admin") for r in self.roles)

    def has_role(self, *role_names: str) -> bool:
        names_lower = [r.lower() for r in role_names]
        return any(r.name.lower() in names_lower for r in self.roles)

    # def get_summary(self) -> dict:
    #     return {
    #         "id": str(self.id),
    #         "username": self.username,
    #         "email": self.email,
    #         "names": self.names,
    #         "phone": self.phone,
    #         "avatar_url": self.avatar_url,
    #         "bio": self.bio,
    #         "is_active": self.is_active,
    #         "is_online": self.is_online,  # Placeholder for online status
    #         "email_verified": self.email_verified,
    #         "roles": self.role_names,
    #         "is_org_admin": self.is_org_admin,
    #         "organization_id": self.organization_id,
    #         "last_seen": self.last_seen.isoformat() if self.last_seen else None,
    #         "created_at": self.created_at.isoformat() if self.created_at else None,
    #         "updated_at": self.updated_at.isoformat() if self.updated_at else None,
    #     }

    # v2
    def get_summary(self) -> dict:
        data = {
            "id": str(self.id),
            "username": self.username,
            "email": self.email,
            "names": self.names,
            "phone": self.phone,
            "avatar_url": self.avatar_url,
            "bio": self.bio,
            "is_active": self.is_active,
            "email_verified": self.email_verified,
            "roles": self.role_names,
            "is_org_admin": self.is_org_admin,
            "organization_id": str(self.organization_id) if self.organization_id else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        return data
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username})>"
