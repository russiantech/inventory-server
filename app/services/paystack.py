# import logging
# import hmac
# import hashlib
# import requests
# from typing import Optional, Dict, Any

# from app.core.config import get_settings
# settings = get_settings()

# logger = logging.getLogger(__name__)

# class PaystackError(Exception):
#     def __init__(self, message: str, status_code: int = 400, paystack_response: Optional[dict] = None):
#         self.message = message
#         self.status_code = status_code
#         self.paystack_response = paystack_response
#         super().__init__(self.message)

# class PaystackService:
#     """Professional Paystack integration for subscription management."""
    
#     BASE_URL = settings.paystack_base_url
#     HEADERS = {
#         "Authorization": f"Bearer {settings.paystack_secret_key}",
#         "Content-Type": "application/json",
#     }
    
#     @classmethod
#     def _request(cls, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
#         """Make authenticated request to Paystack API."""
#         url = f"{cls.BASE_URL}/{endpoint.lstrip('/')}"
#         try:
#             response = requests.request(
#                 method=method,
#                 url=url,
#                 headers=cls.HEADERS,
#                 timeout=30,
#                 **kwargs
#             )
#             response.raise_for_status()
#             data = response.json()
            
#             if not data.get("status"):
#                 logger.error(f"Paystack API error: {data}")
#                 raise PaystackError(
#                     message=data.get("message", "Paystack request failed"),
#                     status_code=response.status_code,
#                     paystack_response=data
#                 )
#             return data
            
#         except requests.exceptions.RequestException as e:
#             logger.error(f"Paystack request failed: {e}")
#             raise PaystackError(f"Payment service unavailable: {str(e)}", status_code=503)

#     # ── Plans ────────────────────────────────────────────────────────
    
#     @classmethod
#     def create_plan(
#         cls,
#         name: str,
#         amount: int,  # In kobo (NGN) or smallest currency unit
#         interval: str,  # "monthly" or "annually"
#         description: Optional[str] = None,
#         currency: str = "NGN"
#     ) -> Dict[str, Any]:
#         """
#         Create a plan on Paystack. Returns plan_code.
#         Amount must be in kobo (multiply NGN by 100).
#         """
#         payload = {
#             "name": name,
#             "amount": amount,
#             "interval": "monthly" if interval == "monthly" else "annually",
#             "currency": currency,
#         }
#         if description:
#             payload["description"] = description
        
#         data = cls._request("POST", "/plan", json=payload)
#         logger.info(f"Paystack plan created: {data['data']['plan_code']}")
#         return data["data"]

#     @classmethod
#     def update_plan(cls, plan_code: str, name: Optional[str] = None, amount: Optional[int] = None) -> Dict[str, Any]:
#         """Update plan details on Paystack."""
#         payload = {}
#         if name:
#             payload["name"] = name
#         if amount:
#             payload["amount"] = amount
        
#         data = cls._request("PUT", f"/plan/{plan_code}", json=payload)
#         return data["data"]

#     @classmethod
#     def fetch_plan(cls, plan_code: str) -> Dict[str, Any]:
#         """Retrieve plan details from Paystack."""
#         data = cls._request("GET", f"/plan/{plan_code}")
#         return data["data"]

#     # ── Customers ─────────────────────────────────────────────────────
    
#     @classmethod
#     def create_customer(
#         cls,
#         email: str,
#         first_name: Optional[str] = None,
#         last_name: Optional[str] = None,
#         phone: Optional[str] = None,
#         metadata: Optional[Dict] = None
#     ) -> Dict[str, Any]:
#         """Create or retrieve customer on Paystack."""
#         payload = {
#             "email": email,
#             "first_name": first_name or "",
#             "last_name": last_name or "",
#             "phone": phone or "",
#         }
#         if metadata:
#             payload["metadata"] = metadata
        
#         data = cls._request("POST", "/customer", json=payload)
#         return data["data"]

#     @classmethod
#     def fetch_customer(cls, email_or_code: str) -> Dict[str, Any]:
#         """Fetch customer by email or customer code."""
#         data = cls._request("GET", f"/customer/{email_or_code}")
#         return data["data"]

#     # ── Subscriptions ────────────────────────────────────────────────
    
#     @classmethod
#     def create_subscription(
#         cls,
#         customer_email: str,
#         plan_code: str,
#         authorization_code: Optional[str] = None,
#         start_date: Optional[str] = None,  # ISO 8601 format
#     ) -> Dict[str, Any]:
#         """
#         Create a subscription on Paystack.
#         If authorization_code is provided, charges immediately.
#         Otherwise, customer gets invoice to pay.
#         """
#         payload = {
#             "customer": customer_email,
#             "plan": plan_code,
#         }
#         if authorization_code:
#             payload["authorization"] = authorization_code
#         if start_date:
#             payload["start_date"] = start_date
        
#         data = cls._request("POST", "/subscription", json=payload)
#         logger.info(f"Paystack subscription created: {data['data']['subscription_code']}")
#         return data["data"]

#     @classmethod
#     def fetch_subscription(cls, subscription_code: str) -> Dict[str, Any]:
#         """Get subscription details."""
#         data = cls._request("GET", f"/subscription/{subscription_code}")
#         return data["data"]

#     @classmethod
#     def disable_subscription(cls, subscription_code: str, email_token: str) -> Dict[str, Any]:
#         """
#         PROFESSIONAL UNSUBSCRIPTION.
#         Disable subscription on Paystack. This immediately stops recurring charges.
#         Customer retains access until period end.
#         """
#         payload = {
#             "code": subscription_code,
#             "token": email_token,
#         }
#         data = cls._request("POST", "/subscription/disable", json=payload)
#         logger.info(f"Paystack subscription disabled: {subscription_code}")
#         return data["data"]

#     @classmethod
#     def enable_subscription(cls, subscription_code: str, email_token: str) -> Dict[str, Any]:
#         """Re-enable a previously disabled subscription."""
#         payload = {
#             "code": subscription_code,
#             "token": email_token,
#         }
#         data = cls._request("POST", "/subscription/enable", json=payload)
#         return data["data"]

#     @classmethod
#     def generate_update_subscription_link(cls, subscription_code: str) -> str:
#         """
#         Generate a link for customer to update their card details.
#         """
#         data = cls._request("GET", f"/subscription/{subscription_code}/manage/link")
#         return data["data"]["link"]

#     # ── Transactions ─────────────────────────────────────────────────
    
#     @classmethod
#     def initialize_transaction(
#         cls,
#         email: str,
#         amount: int,  # kobo
#         plan_code: Optional[str] = None,
#         callback_url: Optional[str] = None,
#         reference: Optional[str] = None,
#         metadata: Optional[Dict] = None,
#     ) -> Dict[str, Any]:
#         """
#         Initialize a transaction. Used for first-time subscription payment
#         or when no authorization code exists.
#         """
#         payload = {
#             "email": email,
#             "amount": amount,
#             "channels": ["card", "bank", "ussd", "qr", "mobile_money", "bank_transfer"],
#         }
#         if plan_code:
#             payload["plan"] = plan_code
#         if callback_url:
#             payload["callback_url"] = callback_url
#         if reference:
#             payload["reference"] = reference
#         if metadata:
#             payload["metadata"] = metadata
        
#         data = cls._request("POST", "/transaction/initialize", json=payload)
#         return data["data"]

#     @classmethod
#     def verify_transaction(cls, reference: str) -> Dict[str, Any]:
#         """Verify transaction status."""
#         data = cls._request("GET", f"/transaction/verify/{reference}")
#         return data["data"]

#     @classmethod
#     def charge_authorization(
#         cls,
#         email: str,
#         amount: int,
#         authorization_code: str,
#         reference: Optional[str] = None,
#         metadata: Optional[Dict] = None,
#     ) -> Dict[str, Any]:
#         """Charge an existing authorization (for one-off or retry)."""
#         payload = {
#             "email": email,
#             "amount": amount,
#             "authorization_code": authorization_code,
#         }
#         if reference:
#             payload["reference"] = reference
#         if metadata:
#             payload["metadata"] = metadata
        
#         data = cls._request("POST", "/transaction/charge_authorization", json=payload)
#         return data["data"]

#     # ── Webhook Verification ───────────────────────────────────────
    
#     @classmethod
#     def verify_webhook_signature(cls, payload: bytes, signature: str) -> bool:
#         """
#         Verify Paystack webhook signature using HMAC SHA512.
#         """
#         if not settings.paystack_webhook_secret:
#             logger.warning("PAYSTACK_WEBHOOK_SECRET not set, skipping signature verification")
#             return True
        
#         expected = hmac.new(
#             settings.paystack_webhook_secret.encode("utf-8"),
#             payload,
#             hashlib.sha512
#         ).hexdigest()
        
#         return hmac.compare_digest(expected, signature)

#     # ── Helpers ─────────────────────────────────────────────────────
    
#     @classmethod
#     def kobo_amount(cls, amount_naira: float) -> int:
#         """Convert Naira to kobo (Paystack uses smallest currency unit)."""
#         return int(amount_naira * 100)
    
#     @classmethod
#     def naira_amount(cls, amount_kobo: int) -> float:
#         """Convert kobo back to Naira."""
#         return amount_kobo / 100



# v2
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
    If `plan_code` is provided, Paystack auto-creates a subscription on the
    customer once this first charge succeeds.
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

