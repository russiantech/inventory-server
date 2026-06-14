# app/services/paystack_service.py
"""
Thin async wrapper around the Paystack API.

Docs: https://paystack.com/docs/api/

All methods return the parsed `data` portion of a successful response, or
raise PaystackError on failure (network error, non-2xx, or `status: false`).
"""

import hashlib
import hmac
import logging
from typing import Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.paystack.co"


class PaystackError(Exception):
    pass


def _headers() -> dict:
    cfg = get_settings()
    return {
        "Authorization": f"Bearer {cfg.paystack_secret_key}",
        "Content-Type": "application/json",
    }


async def _request(method: str, path: str, **kwargs) -> dict:
    cfg = get_settings()
    if not cfg.paystack_secret_key:
        raise PaystackError("Paystack secret key is not configured (APP_PAYSTACK_SECRET_KEY).")

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.request(method, f"{BASE_URL}{path}", headers=_headers(), **kwargs)

    try:
        body = resp.json()
    except Exception:
        body = {}

    if resp.status_code >= 400 or not body.get("status", False):
        msg = body.get("message", f"Paystack request failed ({resp.status_code})")
        logger.error("Paystack %s %s -> %s: %s", method, path, resp.status_code, msg)
        raise PaystackError(msg)

    return body.get("data", {})


# ── Plans (Paystack Plan objects) ─────────────────────────────────────────────

async def create_plan(
    name: str,
    amount_kobo: int,
    interval: str,          # "monthly" | "annually"
    description: str = "",
    currency: str = "NGN",
) -> dict:
    """Create a recurring billing plan on Paystack. Returns plan data including plan_code."""
    payload = {
        "name": name,
        "amount": amount_kobo,
        "interval": interval,
        "currency": currency,
    }
    if description:
        payload["description"] = description
    return await _request("POST", "/plan", json=payload)


async def list_plans_on_paystack(per_page: int = 50) -> list:
    """Fetch all plans from Paystack (used to check for duplicates by name)."""
    data = await _request("GET", "/plan", params={"perPage": per_page})
    return data if isinstance(data, list) else []


# ── Customers ──────────────────────────────────────────────────────────────

async def get_or_create_customer(email: str, first_name: str = "", last_name: str = "") -> dict:
    """Paystack upserts on email — safe to call repeatedly."""
    return await _request(
        "POST",
        "/customer",
        json={"email": email, "first_name": first_name, "last_name": last_name},
    )


# ── Transactions (initial checkout) ─────────────────────────────────────────

async def initialize_transaction(
    email: str,
    amount_kobo: int,
    plan_code: Optional[str],
    callback_url: str,
    metadata: dict,
) -> dict:
    """
    Returns {authorization_url, access_code, reference}.
    If `plan_code` is provided, Paystack auto-creates a recurring subscription
    on the customer once this first charge succeeds.
    """
    payload = {
        "email": email,
        "amount": amount_kobo,
        "callback_url": callback_url,
        "metadata": metadata,
    }
    if plan_code:
        payload["plan"] = plan_code
    return await _request("POST", "/transaction/initialize", json=payload)


async def verify_transaction(reference: str) -> dict:
    """Returns full transaction object including `customer`, `plan`, `status`."""
    return await _request("GET", f"/transaction/verify/{reference}")


# ── Subscriptions ────────────────────────────────────────────────────────────

async def fetch_subscription(subscription_code: str) -> dict:
    return await _request("GET", f"/subscription/{subscription_code}")


async def list_customer_subscriptions(customer_code: str) -> list:
    data = await _request("GET", "/subscription", params={"customer": customer_code})
    return data if isinstance(data, list) else []


async def disable_subscription(subscription_code: str, email_token: str) -> dict:
    """Cancels future billing. The current paid period remains usable."""
    return await _request(
        "POST",
        "/subscription/disable",
        json={"code": subscription_code, "token": email_token},
    )


async def enable_subscription(subscription_code: str, email_token: str) -> dict:
    return await _request(
        "POST",
        "/subscription/enable",
        json={"code": subscription_code, "token": email_token},
    )


# ── Webhooks ─────────────────────────────────────────────────────────────────

def verify_webhook_signature(raw_body: bytes, signature: Optional[str]) -> bool:
    """Paystack signs webhook payloads with HMAC-SHA512 of the raw body
    using your secret key, sent in the `x-paystack-signature` header."""
    cfg = get_settings()
    if not signature or not cfg.paystack_secret_key:
        return False
    expected = hmac.new(
        cfg.paystack_secret_key.encode("utf-8"), raw_body, hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

