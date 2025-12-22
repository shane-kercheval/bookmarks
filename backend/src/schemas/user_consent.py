"""Pydantic schemas for user consent endpoints."""
from datetime import datetime

from pydantic import BaseModel, Field


class ConsentCreate(BaseModel):
    """Schema for creating or updating user consent."""

    privacy_policy_version: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Version of privacy policy being accepted (e.g., '2024-12-20')",
        examples=["2024-12-20"],
    )
    terms_of_service_version: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Version of terms of service being accepted (e.g., '2024-12-20')",
        examples=["2024-12-20"],
    )


class ConsentResponse(BaseModel):
    """Schema for consent response."""

    id: int
    user_id: int
    consented_at: datetime
    privacy_policy_version: str
    terms_of_service_version: str
    ip_address: str | None
    user_agent: str | None

    model_config = {"from_attributes": True}


class ConsentStatus(BaseModel):
    """Schema for checking if user needs to consent."""

    needs_consent: bool = Field(
        ...,
        description="Whether user needs to accept/re-accept terms",
    )
    current_consent: ConsentResponse | None = Field(
        default=None,
        description="Current consent record if it exists",
    )
    current_privacy_version: str = Field(
        ...,
        description="Current privacy policy version that should be accepted",
    )
    current_terms_version: str = Field(
        ...,
        description="Current terms of service version that should be accepted",
    )


class PolicyVersions(BaseModel):
    """Schema for public policy versions endpoint."""

    privacy_policy_version: str = Field(
        ...,
        description="Current privacy policy version",
        examples=["2025-12-20"],
    )
    terms_of_service_version: str = Field(
        ...,
        description="Current terms of service version",
        examples=["2025-12-20"],
    )
