from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    display_name: str = Field(min_length=2, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str | None = None
    role: str
    organisation_id: str | None = None
    patient_id: str | None = None
    is_active: bool
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserView


class ProvisionUserRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    role: Literal["pharmacy", "pmv", "hospital", "clinician", "hmo"]
    organisation_id: str | None = None
