# # v3 — Full Paystack Integration
# # app/api/v1/plans.py
# import json
# import logging
# from datetime import datetime, timedelta, timezone
# from uuid import uuid4

# from fastapi import APIRouter, Depends, Request, BackgroundTasks, HTTPException
# from sqlalchemy.orm import Session

# from app.api.deps.users import _get_org_id, get_db, get_current_user
# from app.api.deps.rbac import require_roles
# from app.models.user import User
# from app.models.organization import Organization
# from app.models.plans import (
#     Plan, Subscription, SubscriptionStatus, 
#     BillingInterval
# )
# from app.schemas.plans import (
#     PlanCreate, PlanUpdate, SubscribeRequest, 
#     InitializePaymentRequest
# )
# from app.services.paystack import PaystackService, PaystackError
# from app.utils.responses import api_response
# from app.core.config import settings

# logger = logging.getLogger(__name__)
# router = APIRouter()

# def _is_super_admin(user: User) -> bool:
#     return any(r.name == "super_admin" for r in user.roles)


# # ─────────────────────────────────────────────────────────────────────────
# #  PLAN CATALOG
# # ─────────────────────────────────────────────────────────────────────────

# @router.get("", summary="List available plans")
# async def list_plans(
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     q = db.query(Plan)
#     if not _is_super_admin(current_user):
#         q = q.filter(Plan.is_active == True)
#     plans = q.order_by(Plan.price_monthly.asc()).all()
#     return api_response(True, "Plans fetched.", data={"plans": [p.get_summary() for p in plans]})


# # ─────────────────────────────────────────────────────────────────────────
# #  PLAN CRUD — SUPER ADMIN (with Paystack sync)
# # ─────────────────────────────────────────────────────────────────────────

# @router.post(
#     "",
#     summary="Create a plan [super_admin only] — auto-creates Paystack plans",
#     dependencies=[Depends(require_roles("super_admin"))],
# )
# async def create_plan(data: PlanCreate, db: Session = Depends(get_db)):
#     if db.query(Plan).filter(Plan.slug == data.slug).first():
#         return api_response(False, f"Plan slug '{data.slug}' already exists.", status_code=400)

#     # Create Paystack plans for both intervals
#     paystack_monthly = None
#     paystack_yearly = None
    
#     try:
#         if data.price_monthly > 0:
#             paystack_monthly = PaystackService.create_plan(
#                 name=f"{data.name} (Monthly)",
#                 amount=PaystackService.kobo_amount(data.price_monthly),
#                 interval="monthly",
#                 description=data.description,
#                 currency=data.currency,
#             )
        
#         if data.price_yearly > 0:
#             paystack_yearly = PaystackService.create_plan(
#                 name=f"{data.name} (Yearly)",
#                 amount=PaystackService.kobo_amount(data.price_yearly),
#                 interval="annually",
#                 description=data.description,
#                 currency=data.currency,
#             )
#     except PaystackError as e:
#         # Rollback: attempt to delete created plans if any
#         logger.error(f"Paystack plan creation failed: {e.message}")
#         # Cleanup would require storing partial successes — for now, report error
#         return api_response(False, f"Paystack integration failed: {e.message}", status_code=502)

#     if data.is_default:
#         db.query(Plan).filter(Plan.is_default == True).update({"is_default": False})

#     plan = Plan(
#         **data.model_dump(exclude={"features", "paystack_plan_code_monthly", "paystack_plan_code_yearly"}),
#         features=json.dumps(data.features),
#         paystack_plan_code_monthly=paystack_monthly["plan_code"] if paystack_monthly else None,
#         paystack_plan_code_yearly=paystack_yearly["plan_code"] if paystack_yearly else None,
#     )
#     db.add(plan)
#     db.commit()
#     db.refresh(plan)
    
#     logger.info(f"Plan created with Paystack integration: {plan.id}")
#     return api_response(True, "Plan created.", data=plan.get_summary(), status_code=201)


# @router.put(
#     "/{plan_id}",
#     summary="Update a plan [super_admin only] — syncs with Paystack",
#     dependencies=[Depends(require_roles("super_admin"))],
# )
# async def update_plan(plan_id: str, data: PlanUpdate, db: Session = Depends(get_db)):
#     plan = db.query(Plan).filter(Plan.id == plan_id).first()
#     if not plan:
#         return api_response(False, "Plan not found.", status_code=404)

#     payload = data.model_dump(exclude_unset=True)
    
#     # Sync price changes to Paystack
#     try:
#         if "price_monthly" in payload and plan.paystack_plan_code_monthly:
#             PaystackService.update_plan(
#                 plan.paystack_plan_code_monthly,
#                 amount=PaystackService.kobo_amount(payload["price_monthly"])
#             )
#         if "price_yearly" in payload and plan.paystack_plan_code_yearly:
#             PaystackService.update_plan(
#                 plan.paystack_plan_code_yearly,
#                 amount=PaystackService.kobo_amount(payload["price_yearly"])
#             )
#     except PaystackError as e:
#         logger.error(f"Paystack plan update failed: {e.message}")
#         # Continue with local update even if Paystack sync fails

#     if "features" in payload:
#         plan.features = json.dumps(payload.pop("features"))
#     if payload.get("is_default"):
#         db.query(Plan).filter(Plan.id != plan.id).update({"is_default": False})

#     for field, value in payload.items():
#         setattr(plan, field, value)

#     db.commit()
#     db.refresh(plan)
#     return api_response(True, "Plan updated.", data=plan.get_summary())


# @router.delete(
#     "/{plan_id}",
#     summary="Deactivate a plan [super_admin only] (soft — existing subscribers keep it)",
#     dependencies=[Depends(require_roles("super_admin"))],
# )
# async def deactivate_plan(plan_id: str, db: Session = Depends(get_db)):
#     plan = db.query(Plan).filter(Plan.id == plan_id).first()
#     if not plan:
#         return api_response(False, "Plan not found.", status_code=404)
#     plan.is_active = False
#     db.commit()
#     return api_response(True, "Plan deactivated.")


# # ─────────────────────────────────────────────────────────────────────────
# #  PAYMENT INITIALIZATION — For new subscriptions without saved card
# # ─────────────────────────────────────────────────────────────────────────

# @router.post(
#     "/initialize-payment",
#     summary="Initialize Paystack payment for subscription [admin]",
#     dependencies=[Depends(require_roles("admin", "super_admin"))],
# )
# async def initialize_payment(
#     data: InitializePaymentRequest,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     """Initialize a Paystack transaction for first-time subscription payment."""
#     plan = db.query(Plan).filter(Plan.id == data.plan_id, Plan.is_active == True).first()
#     if not plan:
#         return api_response(False, "Plan not found or unavailable.", status_code=404)

#     org_id = _get_org_id(current_user)
#     org = db.query(Organization).filter(Organization.id == org_id).first()
    
#     # Get or create Paystack customer
#     try:
#         customer = PaystackService.fetch_customer(current_user.email)
#     except PaystackError:
#         customer = PaystackService.create_customer(
#             email=current_user.email,
#             first_name=current_user.names or current_user.username,
#             metadata={"organization_id": str(org_id)}
#         )
    
#     # Determine plan code and amount
#     if data.billing_interval == "monthly":
#         plan_code = plan.paystack_plan_code_monthly
#         amount = plan.price_monthly
#     else:
#         plan_code = plan.paystack_plan_code_yearly
#         amount = plan.price_yearly
    
#     if not plan_code:
#         return api_response(False, "Paystack plan not configured for this interval.", status_code=400)

#     # Build callback URL
#     callback = data.callback_url or f"{settings.WEBHOOK_BASE_URL}/api/v1/plans/payment-callback"
    
#     # Initialize transaction
#     try:
#         tx_data = PaystackService.initialize_transaction(
#             email=current_user.email,
#             amount=PaystackService.kobo_amount(amount),
#             plan_code=plan_code,
#             callback_url=callback,
#             reference=f"DUNIS-SUB-{uuid4().hex[:12]}",
#             metadata={
#                 "organization_id": str(org_id),
#                 "plan_id": str(plan.id),
#                 "billing_interval": data.billing_interval,
#                 "user_id": str(current_user.id),
#             }
#         )
        
#         # Create pending subscription record
#         existing = db.query(Subscription).filter(
#             Subscription.organization_id == org_id
#         ).first()
        
#         if existing:
#             # Update existing pending subscription
#             existing.plan_id = plan.id
#             existing.billing_interval = BillingInterval(data.billing_interval)
#             existing.status = SubscriptionStatus.pending
#             existing.paystack_customer_code = customer.get("customer_code")
#             existing.paystack_transaction_reference = tx_data["reference"]
#         else:
#             sub = Subscription(
#                 organization_id=org_id,
#                 plan_id=plan.id,
#                 billing_interval=BillingInterval(data.billing_interval),
#                 status=SubscriptionStatus.pending,
#                 paystack_customer_code=customer.get("customer_code"),
#                 paystack_transaction_reference=tx_data["reference"],
#             )
#             db.add(sub)
        
#         db.commit()
        
#         return api_response(
#             True, 
#             "Payment initialized.", 
#             data={
#                 "authorization_url": tx_data["authorization_url"],
#                 "reference": tx_data["reference"],
#                 "access_code": tx_data["access_code"],
#             }
#         )
        
#     except PaystackError as e:
#         return api_response(False, f"Payment initialization failed: {e.message}", status_code=502)


# @router.get(
#     "/payment-callback",
#     summary="Handle Paystack payment callback (redirect after payment)",
# )
# async def payment_callback(
#     reference: str,
#     trxref: Optional[str] = None,
#     db: Session = Depends(get_db),
# ):
#     """
#     Handle redirect from Paystack after payment.
#     Verifies transaction and activates subscription.
#     """
#     sub = db.query(Subscription).filter(
#         Subscription.paystack_transaction_reference == reference
#     ).first()
    
#     if not sub:
#         # Could be a direct payment, log and redirect
#         logger.warning(f"Callback received for unknown reference: {reference}")
#         return api_response(False, "Subscription not found.", status_code=404)

#     try:
#         verification = PaystackService.verify_transaction(reference)
#         tx_data = verification
        
#         if tx_data["status"] == "success":
#             # Extract authorization details for recurring charges
#             auth_data = tx_data.get("authorization", {})
            
#             sub.status = SubscriptionStatus.active
#             sub.paystack_authorization_code = auth_data.get("authorization_code")
#             sub.paystack_card_type = auth_data.get("card_type")
#             sub.paystack_last4 = auth_data.get("last4")
#             sub.paystack_exp_month = auth_data.get("exp_month")
#             sub.paystack_exp_year = auth_data.get("exp_year")
            
#             # Set period (Paystack handles this, but we track locally)
#             now = datetime.now(timezone.utc)
#             period_days = 365 if sub.billing_interval == BillingInterval.yearly else 30
#             sub.current_period_start = now
#             sub.current_period_end = now + timedelta(days=period_days)
            
#             # Sync org limits
#             org = db.query(Organization).filter(Organization.id == sub.organization_id).first()
#             if org and sub.plan:
#                 org.max_users = sub.plan.max_users
            
#             db.commit()
            
#             logger.info(f"Subscription activated via callback: {sub.id}")
#             return api_response(True, "Payment successful. Subscription activated.")
#         else:
#             sub.status = SubscriptionStatus.incomplete
#             db.commit()
#             return api_response(False, "Payment verification failed.", status_code=400)
            
#     except PaystackError as e:
#         sub.status = SubscriptionStatus.incomplete
#         db.commit()
#         return api_response(False, f"Verification error: {e.message}", status_code=502)


# # ─────────────────────────────────────────────────────────────────────────
# #  SUBSCRIPTION MANAGEMENT — Org Admins
# # ─────────────────────────────────────────────────────────────────────────

# @router.get(
#     "/subscription",
#     summary="Get current organization's subscription",
#     dependencies=[Depends(require_roles("admin", "super_admin"))],
# )
# async def get_my_subscription(
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     org_id = _get_org_id(current_user)
#     sub = db.query(Subscription).filter(Subscription.organization_id == org_id).first()
#     if not sub:
#         return api_response(True, "No active subscription.", data={"subscription": None})
#     return api_response(True, "Subscription fetched.", data={"subscription": sub.get_summary()})


# @router.post(
#     "/subscribe",
#     summary="Subscribe with existing authorization (change plan) [admin]",
#     dependencies=[Depends(require_roles("admin", "super_admin"))],
# )
# async def subscribe(
#     data: SubscribeRequest,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     """
#     Subscribe or change plan using existing authorization code (saved card).
#     For new subscriptions without card, use /initialize-payment first.
#     """
#     plan = db.query(Plan).filter(Plan.id == data.plan_id, Plan.is_active == True).first()
#     if not plan:
#         return api_response(False, "Plan not found or unavailable.", status_code=404)

#     org_id = _get_org_id(current_user)
#     org = db.query(Organization).filter(Organization.id == org_id).first()

#     # Check user count against plan limit
#     current_user_count = db.query(User).filter(
#         User.organization_id == org_id, User.deleted == False
#     ).count()
#     if plan.max_users and current_user_count > plan.max_users:
#         return api_response(
#             False,
#             f"Your organization currently has {current_user_count} users, "
#             f"which exceeds the {plan.max_users}-user limit on the {plan.name} plan. "
#             f"Deactivate or remove users before downgrading.",
#             status_code=400,
#         )

#     # Determine Paystack plan code
#     if data.billing_interval == "monthly":
#         plan_code = plan.paystack_plan_code_monthly
#         amount = plan.price_monthly
#     else:
#         plan_code = plan.paystack_plan_code_yearly
#         amount = plan.price_yearly
    
#     if not plan_code:
#         return api_response(False, "Paystack plan not configured for this interval.", status_code=400)

#     # Get existing subscription
#     sub = db.query(Subscription).filter(Subscription.organization_id == org_id).first()
    
#     try:
#         if sub and sub.paystack_authorization_code:
#             # Has saved card — create/update Paystack subscription directly
#             paystack_sub = PaystackService.create_subscription(
#                 customer_email=current_user.email,
#                 plan_code=plan_code,
#                 authorization_code=sub.paystack_authorization_code,
#             )
            
#             # Update subscription
#             sub.plan_id = plan.id
#             sub.billing_interval = BillingInterval(data.billing_interval)
#             sub.status = SubscriptionStatus.active
#             sub.paystack_subscription_code = paystack_sub["subscription_code"]
#             sub.paystack_email_token = paystack_sub["email_token"]
#             sub.canceled_at = None
#             sub.cancel_at_period_end = False
            
#         elif sub and sub.paystack_customer_code:
#             # Has customer but no authorization — needs to pay first
#             return api_response(
#                 False, 
#                 "No saved payment method. Please initialize payment first.",
#                 status_code=400,
#                 data={"action_required": "initialize_payment"}
#             )
#         else:
#             # No existing subscription record — needs payment first
#             return api_response(
#                 False,
#                 "No active payment method. Please initialize payment first.",
#                 status_code=400,
#                 data={"action_required": "initialize_payment"}
#             )

#         # Sync period
#         now = datetime.now(timezone.utc)
#         period_days = 365 if data.billing_interval == BillingInterval.yearly else 30
#         sub.current_period_start = now
#         sub.current_period_end = now + timedelta(days=period_days)

#         # Sync org limits
#         if org:
#             org.max_users = plan.max_users

#         db.commit()
#         db.refresh(sub)

#         logger.info(f"Org {org_id} subscribed to plan '{plan.slug}' ({data.billing_interval})")
#         return api_response(True, f"Subscribed to {plan.name}.", data={"subscription": sub.get_summary()})
        
#     except PaystackError as e:
#         return api_response(False, f"Paystack error: {e.message}", status_code=502)


# @router.post(
#     "/unsubscribe",
#     summary="Cancel subscription professionally via Paystack [admin]",
#     dependencies=[Depends(require_roles("admin", "super_admin"))],
# )
# async def unsubscribe(
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     """
#     PROFESSIONAL UNSUBSCRIPTION.
#     Disables subscription on Paystack (stops recurring charges immediately).
#     Customer retains access until the current period ends.
#     """
#     org_id = _get_org_id(current_user)
#     sub = db.query(Subscription).filter(Subscription.organization_id == org_id).first()
    
#     if not sub or sub.status in (SubscriptionStatus.canceled, SubscriptionStatus.expired):
#         return api_response(False, "No active subscription to cancel.", status_code=400)

#     # Disable on Paystack if we have the codes
#     if sub.paystack_subscription_code and sub.paystack_email_token:
#         try:
#             PaystackService.disable_subscription(
#                 sub.paystack_subscription_code,
#                 sub.paystack_email_token
#             )
#             logger.info(f"Paystack subscription disabled: {sub.paystack_subscription_code}")
#         except PaystackError as e:
#             logger.error(f"Paystack disable failed: {e.message}")
#             # Continue with local cancellation even if Paystack fails
#             # (could be already disabled, or network issue)

#     # Local state: mark as canceled but keep access until period end
#     sub.status = SubscriptionStatus.canceled
#     sub.canceled_at = datetime.now(timezone.utc)
#     sub.cancel_at_period_end = True  # Access continues until period_end
    
#     db.commit()

#     logger.info(f"Org {org_id} canceled subscription by {current_user.username}")
#     return api_response(
#         True, 
#         "Subscription canceled. You retain access until the current billing period ends."
#     )


# # ─────────────────────────────────────────────────────────────────────────
# #  SUPER-ADMIN OVERSIGHT
# # ─────────────────────────────────────────────────────────────────────────

# @router.post(
#     "/organizations/{org_id}/subscribe",
#     summary="Assign a plan to any organization [super_admin only]",
#     dependencies=[Depends(require_roles("super_admin"))],
# )
# async def admin_subscribe_org(
#     org_id: str,
#     data: SubscribeRequest,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     org = db.query(Organization).filter(Organization.id == org_id).first()
#     if not org:
#         return api_response(False, "Organization not found.", status_code=404)

#     plan = db.query(Plan).filter(Plan.id == data.plan_id).first()
#     if not plan:
#         return api_response(False, "Plan not found.", status_code=404)

#     # Determine plan code
#     if data.billing_interval == "monthly":
#         plan_code = plan.paystack_plan_code_monthly
#     else:
#         plan_code = plan.paystack_plan_code_yearly
    
#     sub = db.query(Subscription).filter(Subscription.organization_id == org.id).first()
#     period_days = 365 if data.billing_interval == BillingInterval.yearly else 30
#     now = datetime.now(timezone.utc)
#     period_end = now + timedelta(days=period_days)

#     if sub:
#         sub.plan_id = plan.id
#         sub.billing_interval = BillingInterval(data.billing_interval)
#         sub.status = SubscriptionStatus.active
#         sub.current_period_start = now
#         sub.current_period_end = period_end
#         sub.canceled_at = None
#         sub.cancel_at_period_end = False
#     else:
#         sub = Subscription(
#             organization_id=org.id,
#             plan_id=plan.id,
#             billing_interval=BillingInterval(data.billing_interval),
#             status=SubscriptionStatus.active,
#             current_period_start=now,
#             current_period_end=period_end,
#         )
#         db.add(sub)

#     org.max_users = plan.max_users
#     db.commit()
#     db.refresh(sub)

#     logger.info(f"Super admin assigned org '{org.name}' to plan '{plan.slug}'")
#     return api_response(True, f"Organization '{org.name}' subscribed to {plan.name}.", data={"subscription": sub.get_summary()})


# @router.post(
#     "/organizations/{org_id}/unsubscribe",
#     summary="Cancel any organization's subscription [super_admin only]",
#     dependencies=[Depends(require_roles("super_admin"))],
# )
# async def admin_unsubscribe_org(
#     org_id: str,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     sub = db.query(Subscription).filter(Subscription.organization_id == org_id).first()
#     if not sub or sub.status == SubscriptionStatus.canceled:
#         return api_response(False, "No active subscription to cancel.", status_code=400)

#     # Disable on Paystack
#     if sub.paystack_subscription_code and sub.paystack_email_token:
#         try:
#             PaystackService.disable_subscription(
#                 sub.paystack_subscription_code,
#                 sub.paystack_email_token
#             )
#         except PaystackError as e:
#             logger.error(f"Paystack disable failed for admin unsubscribe: {e.message}")

#     sub.status = SubscriptionStatus.canceled
#     sub.canceled_at = datetime.now(timezone.utc)
#     db.commit()

#     logger.info(f"Super admin canceled subscription for org {org_id}")
#     return api_response(True, "Subscription canceled for organization.")


# @router.get(
#     "/organizations",
#     summary="List all organizations with subscription status [super_admin only]",
#     dependencies=[Depends(require_roles("super_admin"))],
# )
# async def list_organizations(request: Request, db: Session = Depends(get_db)):
#     orgs = db.query(Organization).order_by(Organization.created_at.desc()).all()
#     data = []
#     for org in orgs:
#         sub = db.query(Subscription).filter(Subscription.organization_id == org.id).first()
#         user_count = db.query(User).filter(User.organization_id == org.id, User.deleted == False).count()
#         data.append({
#             "id": str(org.id),
#             "name": org.name,
#             "allow_public_signup": getattr(org, "allow_public_signup", False),
#             "max_users": org.max_users,
#             "user_count": user_count,
#             "created_at": org.created_at.isoformat() if org.created_at else None,
#             "subscription": sub.get_summary() if sub else None,
#         })
#     return api_response(True, "Organizations fetched.", data={"organizations": data})


# # ─────────────────────────────────────────────────────────────────────────
# #  WEBHOOKS — Paystack Event Handling
# # ─────────────────────────────────────────────────────────────────────────

# @router.post(
#     "/webhook",
#     summary="Receive Paystack webhooks",
#     include_in_schema=False,  # Hide from docs
# )
# async def paystack_webhook(
#     request: Request,
#     background_tasks: BackgroundTasks,
#     db: Session = Depends(get_db),
# ):
#     """
#     Handle Paystack webhooks for subscription lifecycle events.
#     Verifies signature for security.
#     """
#     payload = await request.body()
#     signature = request.headers.get("x-paystack-signature", "")
    
#     # Verify signature
#     if not PaystackService.verify_webhook_signature(payload, signature):
#         logger.warning("Invalid webhook signature received")
#         raise HTTPException(status_code=400, detail="Invalid signature")

#     try:
#         event_data = await request.json()
#     except Exception:
#         raise HTTPException(status_code=400, detail="Invalid JSON")

#     event = event_data.get("event")
#     data = event_data.get("data", {})
    
#     logger.info(f"Paystack webhook received: {event}")

#     # Process asynchronously to respond quickly to Paystack
#     background_tasks.add_task(_process_webhook, event, data, db)
    
#     return {"status": "success"}


# def _process_webhook(event: str, data: dict, db: Session):
#     """Process webhook event in background."""
#     from app.db.session import SessionLocal
    
#     db = SessionLocal()
#     try:
#         if event == "subscription.create":
#             _handle_subscription_created(data, db)
#         elif event == "subscription.disable":
#             _handle_subscription_disabled(data, db)
#         elif event == "subscription.enable":
#             _handle_subscription_enabled(data, db)
#         elif event == "charge.success":
#             _handle_charge_success(data, db)
#         elif event == "invoice.create":
#             _handle_invoice_created(data, db)
#         elif event == "invoice.payment_failed":
#             _handle_payment_failed(data, db)
#         elif event == "subscription.not_renew":
#             _handle_subscription_not_renew(data, db)
#         else:
#             logger.info(f"Unhandled webhook event: {event}")
            
#     except Exception as e:
#         logger.error(f"Webhook processing error: {e}")
#         db.rollback()
#     finally:
#         db.close()


# def _handle_subscription_created(data: dict, db: Session):
#     """Subscription created on Paystack — update local record."""
#     sub_code = data.get("subscription_code")
#     sub = db.query(Subscription).filter(
#         Subscription.paystack_subscription_code == sub_code
#     ).first()
    
#     if not sub:
#         # Try to find by customer code and plan
#         customer_code = data.get("customer", {}).get("customer_code")
#         plan_code = data.get("plan", {}).get("plan_code")
        
#         # Find matching pending subscription
#         sub = db.query(Subscription).filter(
#             Subscription.paystack_customer_code == customer_code,
#             Subscription.status == SubscriptionStatus.pending
#         ).first()
    
#     if sub:
#         sub.paystack_subscription_code = sub_code
#         sub.paystack_email_token = data.get("email_token")
#         sub.status = SubscriptionStatus.active
        
#         # Update period from Paystack data
#         next_payment = data.get("next_payment_date")
#         if next_payment:
#             sub.current_period_end = datetime.fromisoformat(next_payment.replace("Z", "+00:00"))
        
#         db.commit()
#         logger.info(f"Webhook: Subscription activated {sub_code}")


# def _handle_subscription_disabled(data: dict, db: Session):
#     """Subscription disabled on Paystack (unsubscribed)."""
#     sub_code = data.get("subscription_code")
#     sub = db.query(Subscription).filter(
#         Subscription.paystack_subscription_code == sub_code
#     ).first()
    
#     if sub:
#         sub.status = SubscriptionStatus.canceled
#         sub.canceled_at = datetime.now(timezone.utc)
#         db.commit()
#         logger.info(f"Webhook: Subscription disabled {sub_code}")


# def _handle_subscription_enabled(data: dict, db: Session):
#     """Subscription re-enabled on Paystack."""
#     sub_code = data.get("subscription_code")
#     sub = db.query(Subscription).filter(
#         Subscription.paystack_subscription_code == sub_code
#     ).first()
    
#     if sub:
#         sub.status = SubscriptionStatus.active
#         sub.canceled_at = None
#         db.commit()
#         logger.info(f"Webhook: Subscription re-enabled {sub_code}")


# def _handle_charge_success(data: dict, db: Session):
#     """Successful charge — update authorization details."""
#     reference = data.get("reference")
#     sub = db.query(Subscription).filter(
#         Subscription.paystack_transaction_reference == reference
#     ).first()
    
#     if not sub:
#         # Try metadata
#         metadata = data.get("metadata", {})
#         org_id = metadata.get("organization_id")
#         if org_id:
#             sub = db.query(Subscription).filter(
#                 Subscription.organization_id == org_id
#             ).first()
    
#     if sub:
#         auth = data.get("authorization", {})
#         sub.paystack_authorization_code = auth.get("authorization_code")
#         sub.paystack_card_type = auth.get("card_type")
#         sub.paystack_last4 = auth.get("last4")
#         sub.paystack_exp_month = auth.get("exp_month")
#         sub.paystack_exp_year = auth.get("exp_year")
        
#         if sub.status == SubscriptionStatus.pending:
#             sub.status = SubscriptionStatus.active
        
#         db.commit()
#         logger.info(f"Webhook: Charge success for subscription {sub.id}")


# def _handle_invoice_created(data: dict, db: Session):
#     """Invoice created — subscription renewing."""
#     sub_code = data.get("subscription", {}).get("subscription_code")
#     if sub_code:
#         sub = db.query(Subscription).filter(
#             Subscription.paystack_subscription_code == sub_code
#         ).first()
        
#         if sub:
#             # Update period
#             period_start = data.get("period_start")
#             period_end = data.get("period_end")
#             if period_start and period_end:
#                 sub.current_period_start = datetime.fromisoformat(period_start.replace("Z", "+00:00"))
#                 sub.current_period_end = datetime.fromisoformat(period_end.replace("Z", "+00:00"))
#                 db.commit()


# def _handle_payment_failed(data: dict, db: Session):
#     """Invoice payment failed — mark past_due."""
#     sub_code = data.get("subscription", {}).get("subscription_code")
#     if sub_code:
#         sub = db.query(Subscription).filter(
#             Subscription.paystack_subscription_code == sub_code
#         ).first()
        
#         if sub:
#             sub.status = SubscriptionStatus.past_due
#             db.commit()
#             logger.warning(f"Webhook: Payment failed for subscription {sub.id}")


# def _handle_subscription_not_renew(data: dict, db: Session):
#     """Subscription set to not renew (cancel at period end)."""
#     sub_code = data.get("subscription_code")
#     sub = db.query(Subscription).filter(
#         Subscription.paystack_subscription_code == sub_code
#     ).first()
    
#     if sub:
#         sub.cancel_at_period_end = True
#         db.commit()
#         logger.info(f"Webhook: Subscription not renewing {sub_code}")
    








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

    # ── Paid plan: initialize Paystack checkout ──
    plan_code = _plan_code_for(plan, data.billing_interval)
    if not plan_code:
        return api_response(
            False,
            f"The {plan.name} plan ({data.billing_interval.value}) isn't configured for billing yet. "
            f"Please contact support.",
            status_code=400,
        )

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

