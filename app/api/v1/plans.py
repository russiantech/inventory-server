

# v2
# app/api/v1/plans.py
import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session

from app.api.deps.users import _get_org_id, get_db, get_current_user
from app.api.deps.rbac import require_roles
from app.core.config import get_settings
from app.models.user import User
from app.models.organization import Organization
from app.models.plans import Plan, Subscription, SubscriptionStatus, BillingInterval
from app.schemas.plans import PlanCreate, PlanUpdate, SubscribeRequest
from app.utils.responses import api_response
from app.services import paystack as paystack_service
from app.services.paystack import PaystackError

logger = logging.getLogger(__name__)
router = APIRouter()


def _is_super_admin(user: User) -> bool:
    return any(r.name == "super_admin" for r in user.roles)


def _period_days(interval: BillingInterval) -> int:
    return 365 if interval == BillingInterval.yearly else 30


def _plan_code_for(plan: Plan, interval: BillingInterval) -> str | None:
    return (
        plan.paystack_plan_code_yearly
        if interval == BillingInterval.yearly
        else plan.paystack_plan_code_monthly
    )


async def _ensure_paystack_plan_code(plan: Plan, interval: BillingInterval, db: Session) -> str:
    """
    Get the Paystack plan code for this plan/interval, creating it on Paystack
    automatically if it doesn't exist yet. Persists the code back to the DB.

    This means super_admins never need to manually copy plan codes from the
    Paystack dashboard — the first subscriber triggers auto-creation.
    """
    existing_code = _plan_code_for(plan, interval)
    if existing_code:
        return existing_code

    amount = float(plan.price_yearly if interval == BillingInterval.yearly else plan.price_monthly)
    if amount <= 0:
        # Free — should never reach here, but guard anyway
        raise PaystackError("Cannot create a Paystack plan for a zero-price interval.")

    paystack_interval = "annually" if interval == BillingInterval.yearly else "monthly"
    interval_label = "Yearly" if interval == BillingInterval.yearly else "Monthly"
    plan_name = f"{plan.name} ({interval_label})"

    logger.info(f"Auto-creating Paystack plan for '{plan_name}' @ {amount} {plan.currency}")

    try:
        result = await paystack_service.create_plan(
            name=plan_name,
            amount_kobo=int(round(amount * 100)),
            interval=paystack_interval,
            description=plan.description or plan.name,
            currency=plan.currency,
        )
    except PaystackError:
        raise

    plan_code = result["plan_code"]

    # Persist immediately so the next subscriber doesn't create a duplicate
    if interval == BillingInterval.yearly:
        plan.paystack_plan_code_yearly = plan_code
    else:
        plan.paystack_plan_code_monthly = plan_code
    db.commit()

    logger.info(f"Paystack plan auto-created: {plan_code} for '{plan_name}'")
    return plan_code


# ─────────────────────────────────────────────────────────────────────────
#  Catalog
# ─────────────────────────────────────────────────────────────────────────

@router.get("", summary="List available plans")
async def list_plans(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Plan)
    if not _is_super_admin(current_user):
        q = q.filter(Plan.is_active == True)
    plans = q.order_by(Plan.price_monthly.asc()).all()
    return api_response(True, "Plans fetched.", data={"plans": [p.get_summary() for p in plans]})


@router.post(
    "",
    summary="Create a plan [super_admin only]",
    dependencies=[Depends(require_roles("super_admin"))],
)
async def create_plan(data: PlanCreate, db: Session = Depends(get_db)):
    if db.query(Plan).filter(Plan.slug == data.slug).first():
        return api_response(False, f"Plan slug '{data.slug}' already exists.", status_code=400)

    if data.is_default:
        db.query(Plan).filter(Plan.is_default == True).update({"is_default": False})

    plan = Plan(
        **data.model_dump(exclude={"features"}),
        features=json.dumps(data.features),
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    # Auto-create Paystack plan objects for paid intervals — best effort,
    # don't fail the whole request if Paystack is down (subscriber flow will retry).
    if float(plan.price_monthly) > 0 and not plan.paystack_plan_code_monthly:
        try:
            result = await paystack_service.create_plan(
                name=f"{plan.name} (Monthly)",
                amount_kobo=int(round(float(plan.price_monthly) * 100)),
                interval="monthly",
                description=plan.description or plan.name,
                currency=plan.currency,
            )
            plan.paystack_plan_code_monthly = result["plan_code"]
            db.commit()
        except PaystackError as e:
            logger.warning(f"Could not auto-create monthly Paystack plan for '{plan.name}': {e}")

    if float(plan.price_yearly) > 0 and not plan.paystack_plan_code_yearly:
        try:
            result = await paystack_service.create_plan(
                name=f"{plan.name} (Yearly)",
                amount_kobo=int(round(float(plan.price_yearly) * 100)),
                interval="annually",
                description=plan.description or plan.name,
                currency=plan.currency,
            )
            plan.paystack_plan_code_yearly = result["plan_code"]
            db.commit()
        except PaystackError as e:
            logger.warning(f"Could not auto-create yearly Paystack plan for '{plan.name}': {e}")

    db.refresh(plan)
    logger.info(f"Plan created: {plan.slug} (monthly={plan.paystack_plan_code_monthly}, yearly={plan.paystack_plan_code_yearly})")
    return api_response(True, "Plan created.", data=plan.get_summary(), status_code=201)


@router.put(
    "/{plan_id}",
    summary="Update a plan [super_admin only]",
    dependencies=[Depends(require_roles("super_admin"))],
)
async def update_plan(plan_id: str, data: PlanUpdate, db: Session = Depends(get_db)):
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if not plan:
        return api_response(False, "Plan not found.", status_code=404)

    payload = data.model_dump(exclude_unset=True)
    if "features" in payload:
        plan.features = json.dumps(payload.pop("features"))
    if payload.get("is_default"):
        db.query(Plan).filter(Plan.id != plan.id).update({"is_default": False})

    for field, value in payload.items():
        setattr(plan, field, value)

    db.commit()
    db.refresh(plan)

    # Sync to Paystack: auto-create missing plan codes, re-create if price changed
    # (Paystack doesn't support updating plan amounts, so we create new ones)
    price_changed = "price_monthly" in payload or "price_yearly" in payload
    name_changed = "name" in payload

    if float(plan.price_monthly) > 0:
        if not plan.paystack_plan_code_monthly or price_changed or name_changed:
            try:
                result = await paystack_service.create_plan(
                    name=f"{plan.name} (Monthly)",
                    amount_kobo=int(round(float(plan.price_monthly) * 100)),
                    interval="monthly",
                    description=plan.description or plan.name,
                    currency=plan.currency,
                )
                plan.paystack_plan_code_monthly = result["plan_code"]
                db.commit()
                logger.info(f"Paystack monthly plan updated/created: {result['plan_code']}")
            except PaystackError as e:
                logger.warning(f"Could not sync monthly Paystack plan for '{plan.name}': {e}")

    if float(plan.price_yearly) > 0:
        if not plan.paystack_plan_code_yearly or price_changed or name_changed:
            try:
                result = await paystack_service.create_plan(
                    name=f"{plan.name} (Yearly)",
                    amount_kobo=int(round(float(plan.price_yearly) * 100)),
                    interval="annually",
                    description=plan.description or plan.name,
                    currency=plan.currency,
                )
                plan.paystack_plan_code_yearly = result["plan_code"]
                db.commit()
                logger.info(f"Paystack yearly plan updated/created: {result['plan_code']}")
            except PaystackError as e:
                logger.warning(f"Could not sync yearly Paystack plan for '{plan.name}': {e}")

    db.refresh(plan)
    return api_response(True, "Plan updated.", data=plan.get_summary())


@router.delete(
    "/{plan_id}",
    summary="Deactivate a plan [super_admin only] (soft — existing subscribers keep it)",
    dependencies=[Depends(require_roles("super_admin"))],
)
async def deactivate_plan(plan_id: str, db: Session = Depends(get_db)):
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if not plan:
        return api_response(False, "Plan not found.", status_code=404)
    plan.is_active = False
    db.commit()
    return api_response(True, "Plan deactivated.")


# ─────────────────────────────────────────────────────────────────────────
#  Subscriptions — organization admins manage their own org's subscription
# ─────────────────────────────────────────────────────────────────────────

@router.get(
    "/subscription",
    summary="Get current organization's subscription",
    dependencies=[Depends(require_roles("admin", "super_admin"))],
)
async def get_my_subscription(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = _get_org_id(current_user)
    sub = db.query(Subscription).filter(Subscription.organization_id == org_id).first()
    if not sub:
        return api_response(True, "No active subscription.", data={"subscription": None})
    return api_response(True, "Subscription fetched.", data={"subscription": sub.get_summary()})


@router.post(
    "/subscribe",
    summary="Subscribe (or change plan) for current organization [admin]",
    dependencies=[Depends(require_roles("admin", "super_admin"))],
)
async def subscribe(
    data: SubscribeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Free plans (price = 0) activate immediately.

    Paid plans return a Paystack `checkout_url` — the frontend redirects the
    user there. Payment confirmation happens via /subscribe/verify (on
    redirect back) AND the /webhook/paystack endpoint (source of truth).
    """
    plan = db.query(Plan).filter(Plan.id == data.plan_id, Plan.is_active == True).first()
    if not plan:
        return api_response(False, "Plan not found or unavailable.", status_code=404)

    org_id = _get_org_id(current_user)

    current_user_count = db.query(User).filter(
        User.organization_id == org_id, User.deleted == False
    ).count()
    if plan.max_users and current_user_count > plan.max_users:
        return api_response(
            False,
            f"Your organization currently has {current_user_count} users, "
            f"which exceeds the {plan.max_users}-user limit on the {plan.name} plan. "
            f"Deactivate or remove users before downgrading.",
            status_code=400,
        )

    sub = db.query(Subscription).filter(Subscription.organization_id == org_id).first()
    now = datetime.now(timezone.utc)
    period_end = now + timedelta(days=_period_days(data.billing_interval))

    # ── Free plan: activate immediately, no payment needed ──
    if float(plan.price_monthly) == 0 and float(plan.price_yearly) == 0:
        if sub:
            sub.plan_id = plan.id
            sub.billing_interval = data.billing_interval
            sub.status = SubscriptionStatus.active
            sub.current_period_start = now
            sub.current_period_end = period_end
            sub.canceled_at = None
            sub.pending_reference = None
        else:
            sub = Subscription(
                organization_id=org_id,
                plan_id=plan.id,
                billing_interval=data.billing_interval,
                status=SubscriptionStatus.active,
                current_period_start=now,
                current_period_end=period_end,
            )
            db.add(sub)

        org = db.query(Organization).filter(Organization.id == org_id).first()
        if org is not None:
            org.max_users = plan.max_users

        db.commit()
        db.refresh(sub)
        logger.info(f"Org {org_id} switched to free plan '{plan.slug}' by {current_user.username}")
        return api_response(True, f"Subscribed to {plan.name}.", data={"subscription": sub.get_summary()})

    # ── Paid plan: get or auto-create Paystack plan, then initialize checkout ──
    try:
        plan_code = await _ensure_paystack_plan_code(plan, data.billing_interval, db)
    except PaystackError as e:
        logger.error(f"Failed to ensure Paystack plan code for plan {plan.id}: {e}")
        return api_response(False, f"Could not prepare billing plan: {e}", status_code=502)

    amount = plan.price_yearly if data.billing_interval == BillingInterval.yearly else plan.price_monthly
    cfg = get_settings()
    callback_url = f"{cfg.frontend_url.rstrip('/')}/settings?paystack_callback=1"

    try:
        tx = await paystack_service.initialize_transaction(
            email=current_user.email,
            amount_kobo=int(round(float(amount) * 100)),
            plan_code=plan_code,
            callback_url=callback_url,
            metadata={
                "org_id": str(org_id),
                "plan_id": str(plan.id),
                "billing_interval": data.billing_interval.value,
                "user_id": str(current_user.id),
            },
        )
    except PaystackError as e:
        logger.error(f"Paystack initialize failed for org {org_id}: {e}")
        return api_response(False, f"Could not start checkout: {e}", status_code=502)

    # Record a pending subscription so the webhook/verify step has something to update.
    if sub:
        sub.plan_id = plan.id
        sub.billing_interval = data.billing_interval
        sub.status = SubscriptionStatus.pending
        sub.pending_reference = tx["reference"]
    else:
        sub = Subscription(
            organization_id=org_id,
            plan_id=plan.id,
            billing_interval=data.billing_interval,
            status=SubscriptionStatus.pending,
            current_period_start=now,
            pending_reference=tx["reference"],
        )
        db.add(sub)

    db.commit()
    db.refresh(sub)

    return api_response(
        True,
        "Redirecting to Paystack checkout.",
        data={"checkout_url": tx["authorization_url"], "reference": tx["reference"], "subscription": sub.get_summary()},
    )


@router.get(
    "/subscribe/verify",
    summary="Verify a Paystack checkout after redirect back [admin]",
    dependencies=[Depends(require_roles("admin", "super_admin"))],
)
async def verify_subscription_payment(
    reference: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = _get_org_id(current_user)

    try:
        tx = await paystack_service.verify_transaction(reference)
    except PaystackError as e:
        return api_response(False, f"Could not verify payment: {e}", status_code=502)

    if tx.get("status") != "success":
        return api_response(False, f"Payment not successful (status: {tx.get('status')}).", status_code=400)

    sub = db.query(Subscription).filter(
        Subscription.organization_id == org_id,
        Subscription.pending_reference == reference,
    ).first()
    if not sub:
        # Webhook may have already processed it and cleared pending_reference.
        sub = db.query(Subscription).filter(Subscription.organization_id == org_id).first()
        if sub and sub.status == SubscriptionStatus.active:
            return api_response(True, "Payment already confirmed.", data={"subscription": sub.get_summary()})
        return api_response(False, "No matching pending subscription found.", status_code=404)

    _activate_from_transaction(db, sub, tx)
    db.commit()
    db.refresh(sub)

    logger.info(f"Org {org_id} payment verified (ref={reference}), plan='{sub.plan.slug}'")
    return api_response(True, "Payment confirmed — subscription active.", data={"subscription": sub.get_summary()})


def _activate_from_transaction(db: Session, sub: Subscription, tx: dict):
    """Shared activation logic for both /verify and the charge.success webhook."""
    plan = sub.plan
    now = datetime.now(timezone.utc)

    sub.status = SubscriptionStatus.active
    sub.current_period_start = now
    sub.current_period_end = now + timedelta(days=_period_days(sub.billing_interval))
    sub.canceled_at = None
    sub.last_payment_reference = tx.get("reference")

    customer = tx.get("customer") or {}
    if customer.get("customer_code"):
        sub.paystack_customer_code = customer["customer_code"]

    org = db.query(Organization).filter(Organization.id == sub.organization_id).first()
    if org is not None and plan is not None:
        org.max_users = plan.max_users


@router.post(
    "/unsubscribe",
    summary="Cancel current organization's subscription [admin]",
    dependencies=[Depends(require_roles("admin", "super_admin"))],
)
async def unsubscribe(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = _get_org_id(current_user)
    sub = db.query(Subscription).filter(Subscription.organization_id == org_id).first()
    if not sub or sub.status == SubscriptionStatus.canceled:
        return api_response(False, "No active subscription to cancel.", status_code=400)

    await _cancel_subscription(db, sub, actor=current_user.username)
    db.commit()

    return api_response(True, "Subscription canceled. Access continues until the current period ends.")


async def _cancel_subscription(db: Session, sub: Subscription, actor: str):
    """Cancels on Paystack (if linked) and marks canceled locally.
    Raises HTTPException(502) if a Paystack-managed subscription can't be
    disabled — we must not silently leave the customer being billed."""
    if sub.paystack_subscription_code and sub.paystack_email_token:
        try:
            await paystack_service.disable_subscription(
                sub.paystack_subscription_code, sub.paystack_email_token
            )
            logger.info(f"Paystack subscription {sub.paystack_subscription_code} disabled by {actor}")
        except PaystackError as e:
            logger.error(f"Failed to disable Paystack subscription {sub.paystack_subscription_code}: {e}")
            raise HTTPException(
                status_code=502,
                detail=f"Could not cancel billing on Paystack: {e}. Please try again or contact support.",
            )
    elif sub.paystack_subscription_code and not sub.paystack_email_token:
        # Shouldn't normally happen, but don't silently leave an active Paystack
        # subscription running if we're missing the token to cancel it.
        logger.warning(
            f"Subscription {sub.id} has paystack_subscription_code but no email_token — "
            f"cannot auto-cancel on Paystack. Manual cancellation in Paystack dashboard required."
        )

    sub.status = SubscriptionStatus.canceled
    sub.canceled_at = datetime.now(timezone.utc)
    sub.pending_reference = None


# ─────────────────────────────────────────────────────────────────────────
#  Webhook — Paystack source of truth for subscription lifecycle events
# ─────────────────────────────────────────────────────────────────────────

@router.post("/webhook/paystack", summary="Paystack webhook receiver")
async def paystack_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    signature = request.headers.get("x-paystack-signature")

    if not paystack_service.verify_webhook_signature(raw_body, signature):
        logger.warning("Rejected Paystack webhook: invalid signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    event = payload.get("event")
    data = payload.get("data", {})
    logger.info(f"Paystack webhook received: {event}")

    if event == "charge.success":
        await _handle_charge_success(db, data)
    elif event == "subscription.create":
        _handle_subscription_create(db, data)
    elif event in ("subscription.disable", "subscription.not_renew"):
        _handle_subscription_disable(db, data)
    elif event == "invoice.payment_failed":
        _handle_payment_failed(db, data)
    elif event == "invoice.update":
        _handle_invoice_update(db, data)
    else:
        logger.debug(f"Unhandled Paystack event: {event}")

    db.commit()
    # Paystack just needs a 200 — content is ignored.
    return api_response(True, "Webhook processed.")


async def _handle_charge_success(db: Session, data: dict):
    reference = data.get("reference")
    metadata = data.get("metadata") or {}
    org_id = metadata.get("org_id")

    sub = None
    if reference:
        sub = db.query(Subscription).filter(Subscription.pending_reference == reference).first()
    if not sub and org_id:
        sub = db.query(Subscription).filter(Subscription.organization_id == org_id).first()
    if not sub:
        logger.warning(f"charge.success: no matching subscription (ref={reference}, org={org_id})")
        return

    _activate_from_transaction(db, sub, data)
    logger.info(f"Webhook activated subscription for org {sub.organization_id} (ref={reference})")


def _handle_subscription_create(db: Session, data: dict):
    """Paystack creates the recurring subscription object after the first
    successful plan-linked charge. We link it here so we can later cancel it."""
    customer = data.get("customer") or {}
    customer_code = customer.get("customer_code")
    subscription_code = data.get("subscription_code")
    email_token = data.get("email_token")

    if not customer_code or not subscription_code:
        logger.warning("subscription.create webhook missing customer_code/subscription_code")
        return

    sub = db.query(Subscription).filter(Subscription.paystack_customer_code == customer_code).first()
    if not sub:
        logger.warning(f"subscription.create: no local subscription for customer {customer_code}")
        return

    sub.paystack_subscription_code = subscription_code
    sub.paystack_email_token = email_token
    if sub.status == SubscriptionStatus.pending:
        sub.status = SubscriptionStatus.active
    logger.info(f"Linked Paystack subscription {subscription_code} to org {sub.organization_id}")


def _handle_subscription_disable(db: Session, data: dict):
    subscription_code = data.get("subscription_code")
    if not subscription_code:
        return
    sub = db.query(Subscription).filter(Subscription.paystack_subscription_code == subscription_code).first()
    if not sub:
        return
    sub.status = SubscriptionStatus.canceled
    sub.canceled_at = datetime.now(timezone.utc)
    logger.info(f"Paystack disabled subscription {subscription_code} (org {sub.organization_id})")


def _handle_payment_failed(db: Session, data: dict):
    subscription_obj = data.get("subscription") or {}
    subscription_code = subscription_obj.get("subscription_code")
    customer = data.get("customer") or {}
    customer_code = customer.get("customer_code")

    sub = None
    if subscription_code:
        sub = db.query(Subscription).filter(Subscription.paystack_subscription_code == subscription_code).first()
    if not sub and customer_code:
        sub = db.query(Subscription).filter(Subscription.paystack_customer_code == customer_code).first()
    if not sub:
        return

    sub.status = SubscriptionStatus.past_due
    logger.warning(f"Payment failed for org {sub.organization_id} (sub={subscription_code}) — marked past_due")


def _handle_invoice_update(db: Session, data: dict):
    """Successful renewal invoice — extend the current period."""
    if data.get("status") != "success":
        return
    subscription_obj = data.get("subscription") or {}
    subscription_code = subscription_obj.get("subscription_code")
    if not subscription_code:
        return

    sub = db.query(Subscription).filter(Subscription.paystack_subscription_code == subscription_code).first()
    if not sub:
        return

    now = datetime.now(timezone.utc)
    sub.status = SubscriptionStatus.active
    sub.current_period_start = now
    sub.current_period_end = now + timedelta(days=_period_days(sub.billing_interval))
    logger.info(f"Renewed subscription for org {sub.organization_id} via invoice.update")


# ─────────────────────────────────────────────────────────────────────────
#  Super-admin: assign/override plans for any organization (comp accounts)
# ─────────────────────────────────────────────────────────────────────────

@router.post(
    "/organizations/{org_id}/subscribe",
    summary="Assign a plan to any organization [super_admin only] — bypasses Paystack (comp)",
    dependencies=[Depends(require_roles("super_admin"))],
)
async def admin_subscribe_org(
    org_id: str,
    data: SubscribeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        return api_response(False, "Organization not found.", status_code=404)

    plan = db.query(Plan).filter(Plan.id == data.plan_id).first()
    if not plan:
        return api_response(False, "Plan not found.", status_code=404)

    sub = db.query(Subscription).filter(Subscription.organization_id == org.id).first()
    now = datetime.now(timezone.utc)
    period_end = now + timedelta(days=_period_days(data.billing_interval))

    # If the org has an active Paystack-billed subscription, cancel it first —
    # a super_admin override should not leave the org being double-billed.
    if sub and sub.paystack_subscription_code and sub.status == SubscriptionStatus.active:
        try:
            await _cancel_subscription(db, sub, actor=current_user.username)
            logger.info(f"Cancelled existing Paystack subscription for org {org.id} prior to admin override")
        except HTTPException as e:
            return api_response(
                False,
                f"Org has an active Paystack subscription that couldn't be cancelled automatically "
                f"({e.detail}). Resolve in the Paystack dashboard before reassigning.",
                status_code=502,
            )

    if sub:
        sub.plan_id = plan.id
        sub.billing_interval = data.billing_interval
        sub.status = SubscriptionStatus.active
        sub.current_period_start = now
        sub.current_period_end = period_end
        sub.canceled_at = None
        sub.pending_reference = None
        # Comp override: detach from Paystack billing.
        sub.paystack_subscription_code = None
        sub.paystack_email_token = None
    else:
        sub = Subscription(
            organization_id=org.id,
            plan_id=plan.id,
            billing_interval=data.billing_interval,
            status=SubscriptionStatus.active,
            current_period_start=now,
            current_period_end=period_end,
        )
        db.add(sub)

    org.max_users = plan.max_users
    db.commit()
    db.refresh(sub)

    logger.info(f"Super admin {current_user.username} assigned org '{org.name}' to plan '{plan.slug}' (comp)")
    return api_response(True, f"Organization '{org.name}' subscribed to {plan.name}.", data={"subscription": sub.get_summary()})


@router.post(
    "/organizations/{org_id}/unsubscribe",
    summary="Cancel any organization's subscription [super_admin only]",
    dependencies=[Depends(require_roles("super_admin"))],
)
async def admin_unsubscribe_org(
    org_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sub = db.query(Subscription).filter(Subscription.organization_id == org_id).first()
    if not sub or sub.status == SubscriptionStatus.canceled:
        return api_response(False, "No active subscription to cancel.", status_code=400)

    await _cancel_subscription(db, sub, actor=current_user.username)
    db.commit()

    logger.info(f"Super admin {current_user.username} canceled subscription for org {org_id}")
    return api_response(True, "Subscription canceled for organization.")


# ─────────────────────────────────────────────────────────────────────────
#  Super-admin oversight — all organizations & their subscriptions
# ─────────────────────────────────────────────────────────────────────────

@router.get(
    "/organizations",
    summary="List all organizations with their subscription status [super_admin only]",
    dependencies=[Depends(require_roles("super_admin"))],
)
async def list_organizations(request: Request, db: Session = Depends(get_db)):
    orgs = db.query(Organization).order_by(Organization.created_at.desc()).all()
    data = []
    for org in orgs:
        sub = db.query(Subscription).filter(Subscription.organization_id == org.id).first()
        user_count = db.query(User).filter(User.organization_id == org.id, User.deleted == False).count()
        data.append({
            "id": str(org.id),
            "name": org.name,
            "allow_public_signup": getattr(org, "allow_public_signup", False),
            "max_users": org.max_users,
            "user_count": user_count,
            "created_at": org.created_at.isoformat() if org.created_at else None,
            "subscription": sub.get_summary() if sub else None,
        })
    return api_response(True, "Organizations fetched.", data={"organizations": data})