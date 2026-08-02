"""
Public policy-version endpoint.

The consent *enforcement* system (a blocking 451 gate plus accept/status
endpoints) was retired on 2026-08-01 — see
docs/implementation_plans/2026-08-01-consent-simplification.md. Initial
acceptance is now captured by Clerk at sign-up; changes go out by notice, per
the runbook in core/policy_versions.py.

What survives is this one public endpoint: the Privacy Policy and Terms of
Service pages read it to display their "Last Updated" date. The route prefix is
unchanged so those pages keep working.
"""
from fastapi import APIRouter

from core.policy_versions import PRIVACY_POLICY_VERSION, TERMS_OF_SERVICE_VERSION
from schemas.user_consent import PolicyVersions

router = APIRouter(prefix="/consent", tags=["consent"])


@router.get("/versions", response_model=PolicyVersions)
async def get_policy_versions() -> PolicyVersions:
    """
    Get current policy versions (public endpoint, no authentication required).

    Used by the public Privacy Policy and Terms of Service pages to display the
    current version dates.
    """
    return PolicyVersions(
        privacy_policy_version=PRIVACY_POLICY_VERSION,
        terms_of_service_version=TERMS_OF_SERVICE_VERSION,
    )
