# app/schemas/auth.py
from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class SigninSchema(BaseModel):
    identifier: str = Field(..., min_length=1, description="Email, username, or phone")
    password: str = Field(..., min_length=1)


class SignupSchema(BaseModel):
    org_name: Optional[str] = Field(None, max_length=120)
    username: str = Field(..., min_length=2, max_length=50)
    email: EmailStr
    names: Optional[str] = Field(None, max_length=120)
    phone: Optional[str] = Field(None, max_length=20)
    password: str = Field(..., min_length=4)


class SignupVerifySchema(BaseModel):
    token: str
    email_code: str = Field(..., min_length=6, max_length=6)


class CreateStaffSchema(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    email: EmailStr
    names: Optional[str] = Field(None, max_length=120)
    phone: Optional[str] = Field(None, max_length=20)
    password: Optional[str] = Field(None, min_length=4)
    role: Optional[str] = Field("staff", pattern="^(staff|cashier|manager)$")


class ChangePasswordSchema(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=4)


class ForgotPasswordSchema(BaseModel):
    email: EmailStr


class ResetPasswordSchema(BaseModel):
    token: str
    email_code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=4)