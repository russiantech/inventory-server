# scripts/seed_plans.py
"""
Seed example subscription plans.

Run once (or whenever plans change) with:
    python -m scripts.seed_plans

Idempotent — existing plans (matched by slug) are updated in place rather
than duplicated, so it's safe to re-run after editing the PLANS list below.
"""
import json
# from app.core.database_class import SessionLocal
from app.models.plans import Plan
from app.db.session import SessionLocal


PLANS = [
    {
        "name": "Free",
        "slug": "free",
        "description": "Get started with the basics — perfect for trying things out.",
        "price_monthly": 0,
        "price_yearly": 0,
        "currency": "NGN",
        "max_users": 2,
        "max_products": 50,
        "max_warehouses": 1,
        "storage_quota_mb": 100,
        "features": [
            "Up to 2 team members",
            "Basic sales & stock tracking",
            "Email support",
        ],
        "is_active": True,
        "is_default": True,   # auto-assigned to brand-new organizations
    },
    {
        "name": "Starter",
        "slug": "starter",
        "description": "For small businesses ready to grow beyond the basics.",
        "price_monthly": 5000,
        "price_yearly": 50000,   # ~2 months free
        "currency": "NGN",
        "max_users": 5,
        "max_products": 500,
        "max_warehouses": 2,
        "storage_quota_mb": 1024,
        "features": [
            "Up to 5 team members",
            "Multi-warehouse stock tracking",
            "Sales & expense reports",
            "Priority email support",
        ],
        "is_active": True,
        "is_default": False,
    },
    {
        "name": "Pro",
        "slug": "pro",
        "description": "Advanced reporting and higher limits for growing teams.",
        "price_monthly": 15000,
        "price_yearly": 150000,  # ~2 months free
        "currency": "NGN",
        "max_users": 20,
        "max_products": 5000,
        "max_warehouses": 10,
        "storage_quota_mb": 10240,
        "features": [
            "Up to 20 team members",
            "Advanced financial reports",
            "Staff visibility controls",
            "Public signup with admin approval",
            "Priority chat & email support",
        ],
        "is_active": True,
        "is_default": False,
    },
    {
        "name": "Enterprise",
        "slug": "enterprise",
        "description": "Unlimited scale, dedicated support, and custom terms.",
        "price_monthly": 50000,
        "price_yearly": 500000,
        "currency": "NGN",
        "max_users": 100,
        "max_products": None,       # unlimited
        "max_warehouses": None,     # unlimited
        "storage_quota_mb": 51200,
        "features": [
            "Up to 100 team members (custom limits available)",
            "Unlimited products & warehouses",
            "Dedicated account manager",
            "Custom integrations & SLAs",
        ],
        "is_active": True,
        "is_default": False,
    },
]


def run():
    db = SessionLocal()
    try:
        # Only one plan may be is_default at a time.
        default_slugs = [p["slug"] for p in PLANS if p["is_default"]]
        if len(default_slugs) > 1:
            raise ValueError(f"Multiple default plans defined: {default_slugs}")

        for data in PLANS:
            features = data.pop("features")
            plan = db.query(Plan).filter(Plan.slug == data["slug"]).first()

            if data.get("is_default"):
                db.query(Plan).filter(Plan.is_default == True, Plan.slug != data["slug"]).update(
                    {"is_default": False}
                )

            if plan:
                for field, value in data.items():
                    setattr(plan, field, value)
                plan.features = json.dumps(features)
                print(f"Updated plan: {plan.name}")
            else:
                plan = Plan(**data, features=json.dumps(features))
                db.add(plan)
                print(f"Created plan: {plan.name}")

        db.commit()
        print("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    run()