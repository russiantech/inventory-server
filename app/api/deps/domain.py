
# app/api/deps/domain.py
"""
Domain resolution middleware for multi-tenant custom domains.

Resolves the current organization from:
1. Custom domain (Host header matches custom_domain)
2. Subdomain (tenant-slug.dunis.app)
3. X-Organization-ID header (for API clients)
4. JWT token org_id claim (fallback)

Usage:
    @router.get("/products")
    async def list_products(
        org: Organization = Depends(get_current_org),
        db: Session = Depends(get_db),
    ):
        # All queries are automatically scoped to org.id
        ...
"""

import logging
from typing import Optional
from fastapi import Request, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.organization import Organization
from app.api.deps.users import get_current_user_optional

logger = logging.getLogger(__name__)

# Cache: domain -> org_id (TTL 5 minutes in production)
_domain_cache: dict[str, tuple[str, float]] = {}
_CACHE_TTL_SECONDS = 300


def _get_base_domain() -> str:
    from app.core.config import get_settings
    return get_settings().domain or "dunis.app"


def _extract_slug_from_host(host: str, base_domain: str) -> Optional[str]:
    """Extract tenant slug from subdomain like 'acme.dunis.app'."""
    host = host.lower().strip()
    base = base_domain.lower().strip()
    
    # Remove port if present
    if ":" in host:
        host = host.split(":")[0]
    
    # Exact match for base domain (no tenant)
    if host == base:
        return None
    
    # Subdomain pattern: {slug}.{base_domain}
    suffix = f".{base}"
    if host.endswith(suffix):
        slug = host[:-len(suffix)]
        # Ignore www and common subdomains
        if slug in ("www", "api", "admin", "app", "static", "cdn"):
            return None
        return slug
    
    return None


def _resolve_org_from_host(host: str, db: Session) -> Optional[Organization]:
    """Resolve organization from Host header."""
    if not host:
        return None
    
    host = host.lower().strip()
    base_domain = _get_base_domain()
    
    # 1. Check custom domain (exact match)
    org = db.query(Organization).filter(
        Organization.custom_domain == host,
        Organization.is_active == True,
        Organization.domain_verified == True,
    ).first()
    if org:
        return org
    
    # 2. Check default subdomain pattern
    slug = _extract_slug_from_host(host, base_domain)
    if slug:
        org = db.query(Organization).filter(
            Organization.slug == slug,
            Organization.is_active == True,
        ).first()
        if org:
            return org
    
    return None


def _resolve_org_from_header(request: Request, db: Session) -> Optional[Organization]:
    """Resolve from X-Organization-ID or X-Organization-Slug header."""
    org_id = request.headers.get("X-Organization-ID")
    if org_id:
        try:
            from uuid import UUID
            org = db.query(Organization).filter(
                Organization.id == UUID(org_id),
                Organization.is_active == True,
            ).first()
            if org:
                return org
        except ValueError:
            pass
    
    org_slug = request.headers.get("X-Organization-Slug")
    if org_slug:
        org = db.query(Organization).filter(
            Organization.slug == org_slug.lower(),
            Organization.is_active == True,
        ).first()
        if org:
            return org
    
    return None


async def get_current_org(
    request: Request,
    db: Session = Depends(get_db),
) -> Organization:
    """
    Resolve organization from request context.
    Raises 404 if no valid organization found.
    """
    host = request.headers.get("Host", "")
    
    # 1. Try custom domain / subdomain from Host header
    org = _resolve_org_from_host(host, db)
    if org:
        # Attach to request state for downstream use
        request.state.organization = org
        request.state.tenant_id = str(org.id)
        return org
    
    # 2. Try explicit headers (API clients, mobile apps)
    org = _resolve_org_from_header(request, db)
    if org:
        request.state.organization = org
        request.state.tenant_id = str(org.id)
        return org
    
    # 3. Try from authenticated user's organization
    current_user = await get_current_user_optional(request, db)
    if current_user and current_user.organization_id:
        org = db.query(Organization).filter(
            Organization.id == current_user.organization_id,
            Organization.is_active == True,
        ).first()
        if org:
            request.state.organization = org
            request.state.tenant_id = str(org.id)
            return org
    
    raise HTTPException(status_code=404, detail="Organization not found. Please check your domain or contact support.")


async def get_current_org_optional(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[Organization]:
    """Optional org resolution — returns None instead of raising."""
    try:
        return await get_current_org(request, db)
    except HTTPException:
        return None


async def require_org_admin(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
) -> Organization:
    """Require current user to be admin of the resolved organization."""
    org = await get_current_org(request, db)
    
    if not current_user.organization_id or current_user.organization_id != org.id:
        raise HTTPException(status_code=403, detail="You do not belong to this organization.")
    
    if not (current_user.is_org_admin or current_user.has_role("admin", "super_admin")):
        raise HTTPException(status_code=403, detail="Organization admin privileges required.")
    
    return org


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
