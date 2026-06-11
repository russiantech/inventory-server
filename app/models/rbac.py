# app/models/rbac.py
from typing import List, Optional
from sqlalchemy import String, Text, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base_class import Base
from app.db.mixins import UUIDMixin, TimestampMixin
from app.models.association_tables import user_roles


class Role(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
   
    organization_id: Mapped[UUID] = mapped_column(
    UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization = relationship("Organization", backref="roles")
    users: Mapped[List["User"]] = relationship(
        "User", secondary=user_roles, back_populates="roles"
    )
    
    def get_summary(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "is_default": self.is_default,
            "organization_id": self.organization_id,
        }

    def __repr__(self) -> str:
        return f"<Role(name={self.name})>"
