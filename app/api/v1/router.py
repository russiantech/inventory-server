# app/api/v1/router.py
from fastapi import APIRouter
from app.core.config import get_settings
from app.api.v1 import auth, users, roles, categories, items, stock, sales, reports, expenses

settings = get_settings()

v1_router = APIRouter(prefix=settings.api_prefix)

# Auth
v1_router.include_router(auth.router,       prefix="/auth",       tags=["Auth"])
v1_router.include_router(users.router,      prefix="/users",      tags=["Users"])
v1_router.include_router(roles.router,      prefix="/roles",      tags=["Roles"])

# Inventory
v1_router.include_router(categories.router, prefix="/categories", tags=["Categories"])
v1_router.include_router(items.router,      prefix="/items",      tags=["Items"])
v1_router.include_router(stock.router,      prefix="/stock",      tags=["Stock"])

# Sales & Expenses
v1_router.include_router(sales.router,      prefix="/sales",      tags=["Sales"])
v1_router.include_router(expenses.router,   prefix="/expenses",   tags=["Expenses"])

# Reports
v1_router.include_router(reports.router,    prefix="/reports",    tags=["Reports"])
