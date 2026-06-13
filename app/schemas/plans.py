# # app/schemas/plan.py
# from typing import Optional, List
# from pydantic import BaseModel, Field

# from app.models.plans import BillingInterval


# class PlanCreate(BaseModel):
#     name: str
#     slug: str
#     description: Optional[str] = None
#     price_monthly: float = 0
#     price_yearly: float = 0
#     currency: str = "NGN"
#     max_users: int = 5
#     max_products: Optional[int] = None
#     max_warehouses: Optional[int] = None
#     features: List[str] = Field(default_factory=list)
#     is_active: bool = True
#     is_default: bool = False


# class PlanUpdate(BaseModel):
#     name: Optional[str] = None
#     description: Optional[str] = None
#     price_monthly: Optional[float] = None
#     price_yearly: Optional[float] = None
#     currency: Optional[str] = None
#     max_users: Optional[int] = None
#     max_products: Optional[int] = None
#     max_warehouses: Optional[int] = None
#     features: Optional[List[str]] = None
#     is_active: Optional[bool] = None
#     is_default: Optional[bool] = None


# class SubscribeRequest(BaseModel):
#     plan_id: str
#     billing_interval: BillingInterval = BillingInterval.monthly






# # v2
# # app/schemas/plan.py
# from typing import Optional, List
# from pydantic import BaseModel, Field

# from app.models.plans import BillingInterval


# class PlanCreate(BaseModel):
#     name: str
#     slug: str
#     description: Optional[str] = None
#     price_monthly: float = 0
#     price_yearly: float = 0
#     currency: str = "NGN"
#     max_users: int = 5
#     max_products: Optional[int] = None
#     max_warehouses: Optional[int] = None
#     storage_quota_mb: int = 512
#     features: List[str] = Field(default_factory=list)
#     is_active: bool = True
#     is_default: bool = False


# class PlanUpdate(BaseModel):
#     name: Optional[str] = None
#     description: Optional[str] = None
#     price_monthly: Optional[float] = None
#     price_yearly: Optional[float] = None
#     currency: Optional[str] = None
#     max_users: Optional[int] = None
#     max_products: Optional[int] = None
#     max_warehouses: Optional[int] = None
#     storage_quota_mb: Optional[int] = None
#     features: Optional[List[str]] = None
#     is_active: Optional[bool] = None
#     is_default: Optional[bool] = None


# class SubscribeRequest(BaseModel):
#     plan_id: str
#     billing_interval: BillingInterval = BillingInterval.monthly




# # v3
# from pydantic import BaseModel, Field, field_validator
# from typing import Optional, List

# class PlanCreate(BaseModel):
#     name: str = Field(..., min_length=1, max_length=100)
#     slug: str = Field(..., min_length=1, max_length=100)
#     description: Optional[str] = None
#     price_monthly: float = Field(..., ge=0)
#     price_yearly: float = Field(..., ge=0)
#     currency: str = Field(default="NGN", max_length=3)
#     max_users: int = Field(..., ge=1)
#     max_products: Optional[int] = Field(None, ge=0)
#     max_warehouses: Optional[int] = Field(None, ge=0)
#     storage_quota_mb: int = Field(default=512, ge=0)
#     features: List[str] = Field(default_factory=list)
#     is_active: bool = True
#     is_default: bool = False
    
#     # Paystack fields (optional during creation, can be added after Paystack plan creation)
#     paystack_plan_code_monthly: Optional[str] = None
#     paystack_plan_code_yearly: Optional[str] = None

# class PlanUpdate(BaseModel):
#     name: Optional[str] = None
#     description: Optional[str] = None
#     price_monthly: Optional[float] = Field(None, ge=0)
#     price_yearly: Optional[float] = Field(None, ge=0)
#     currency: Optional[str] = None
#     max_users: Optional[int] = Field(None, ge=1)
#     max_products: Optional[int] = Field(None, ge=0)
#     max_warehouses: Optional[int] = Field(None, ge=0)
#     storage_quota_mb: Optional[int] = Field(None, ge=0)
#     features: Optional[List[str]] = None
#     is_active: Optional[bool] = None
#     is_default: Optional[bool] = None
#     paystack_plan_code_monthly: Optional[str] = None
#     paystack_plan_code_yearly: Optional[str] = None

# class SubscribeRequest(BaseModel):
#     plan_id: str
#     billing_interval: str  # "monthly" or "yearly"
    
#     @field_validator('billing_interval')
#     @classmethod
#     def validate_interval(cls, v):
#         if v not in ('monthly', 'yearly'):
#             raise ValueError('billing_interval must be monthly or yearly')
#         return v

# class InitializePaymentRequest(BaseModel):
#     plan_id: str
#     billing_interval: str
#     callback_url: Optional[str] = None

# class PaymentCallbackResponse(BaseModel):
#     reference: str
#     trxref: Optional[str] = None  # Paystack sends this

# class WebhookPayload(BaseModel):
#     event: str
#     data: dict




# v3
# app/schemas/plan.py
from typing import Optional, List
from pydantic import BaseModel, Field

from app.models.plans import BillingInterval


class PlanCreate(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    price_monthly: float = 0
    price_yearly: float = 0
    currency: str = "NGN"
    max_users: int = 5
    max_products: Optional[int] = None
    max_warehouses: Optional[int] = None
    storage_quota_mb: int = 512
    features: List[str] = Field(default_factory=list)
    is_active: bool = True
    is_default: bool = False
    paystack_plan_code_monthly: Optional[str] = None
    paystack_plan_code_yearly: Optional[str] = None


class PlanUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price_monthly: Optional[float] = None
    price_yearly: Optional[float] = None
    currency: Optional[str] = None
    max_users: Optional[int] = None
    max_products: Optional[int] = None
    max_warehouses: Optional[int] = None
    storage_quota_mb: Optional[int] = None
    features: Optional[List[str]] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    paystack_plan_code_monthly: Optional[str] = None
    paystack_plan_code_yearly: Optional[str] = None


class SubscribeRequest(BaseModel):
    plan_id: str
    billing_interval: BillingInterval = BillingInterval.monthly

