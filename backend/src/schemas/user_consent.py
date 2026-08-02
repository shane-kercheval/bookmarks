"""
Pydantic schema for the public policy-versions endpoint.

The consent create/response/status schemas were removed with the consent gate
(2026-08-01). Only the public versions payload remains — see
api/routers/consent.py.
"""
from pydantic import BaseModel, Field


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
