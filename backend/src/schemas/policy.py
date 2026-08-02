"""
Pydantic schema for the public policy-versions endpoint.

All that remains of the consent module. The create/response/status schemas went
with the consent gate, and the `user_consents` table itself was dropped, on
2026-08-01 — see docs/implementation_plans/2026-08-01-consent-simplification.md.
This file outlives them because the published Privacy Policy and Terms pages
still read their "Last Updated" date from `GET /consent/versions`.
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
