from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
PHONE_PATTERN = r"^\+?\d{10,15}$"


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(pattern=PHONE_PATTERN)
    email: str = Field(pattern=EMAIL_PATTERN, max_length=255)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("email")
    @classmethod
    def _lower_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("phone")
    @classmethod
    def _clean_phone(cls, v: str) -> str:
        return v.replace(" ", "").replace("-", "")


class LoginIn(BaseModel):
    email: str | None = None
    phone: str | None = None
    password: str = Field(min_length=1)

    @model_validator(mode="after")
    def _identifier_required(self) -> "LoginIn":
        if not (self.email or self.phone):
            raise ValueError("email or phone is required")
        if self.email:
            self.email = self.email.strip().lower()
        if self.phone:
            self.phone = self.phone.replace(" ", "").replace("-", "")
        return self


class UserOut(BaseModel):
    id: int
    name: str
    phone: str
    # Nullable — pure guests created via guest checkout have no email.
    email: str | None = None
    role: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class MeResponse(BaseModel):
    user: UserOut


class VerifyPaymentIn(BaseModel):
    razorpay_order_id: str = Field(min_length=1)
    razorpay_payment_id: str = Field(min_length=1)
    razorpay_signature: str = Field(min_length=1)
