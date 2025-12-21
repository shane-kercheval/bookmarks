"""User consent endpoints for privacy policy and terms of service tracking."""
from datetime import datetime, UTC

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_async_session, get_current_user_without_consent
from core.policy_versions import PRIVACY_POLICY_VERSION, TERMS_OF_SERVICE_VERSION
from models.user import User
from models.user_consent import UserConsent
from schemas.user_consent import ConsentCreate, ConsentResponse, ConsentStatus

router = APIRouter(prefix="/consent", tags=["consent"])


def get_client_ip(request: Request) -> str | None:
    """
    Extract client IP address from request headers.

    Checks forwarded headers first (for proxy/load balancer scenarios),
    then falls back to direct client IP.

    Args:
        request: FastAPI request object

    Returns:
        Client IP address or None if unable to determine
    """
    # Check X-Forwarded-For header (proxy/load balancer)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For can be comma-separated list, take first (client IP)
        return forwarded_for.split(",")[0].strip()

    # Check X-Real-IP header (alternative proxy header)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    # Fall back to direct client IP
    if request.client:
        return request.client.host

    return None


@router.get("/status", response_model=ConsentStatus)
async def check_consent_status(
    current_user: User = Depends(get_current_user_without_consent),
    session: AsyncSession = Depends(get_async_session),
) -> ConsentStatus:
    """
    Check if user needs to consent (or re-consent).

    Returns consent status without throwing 404 errors.
    This is the recommended endpoint for checking consent requirements.

    Returns:
        - needs_consent=True if user has never consented or versions don't match
        - needs_consent=False if user has valid consent with current versions
        - current_consent includes the existing record (if any)
    """
    # Query for fresh consent data (joinedload on User may be stale in some contexts)
    result = await session.execute(
        select(UserConsent).where(UserConsent.user_id == current_user.id),
    )
    consent = result.scalar_one_or_none()

    if not consent:
        return ConsentStatus(
            needs_consent=True,
            current_consent=None,
            current_privacy_version=PRIVACY_POLICY_VERSION,
            current_terms_version=TERMS_OF_SERVICE_VERSION,
        )

    # Check if versions match current policy versions
    needs_consent = (
        consent.privacy_policy_version != PRIVACY_POLICY_VERSION
        or consent.terms_of_service_version != TERMS_OF_SERVICE_VERSION
    )

    return ConsentStatus(
        needs_consent=needs_consent,
        current_consent=consent,
        current_privacy_version=PRIVACY_POLICY_VERSION,
        current_terms_version=TERMS_OF_SERVICE_VERSION,
    )


@router.post("/me", response_model=ConsentResponse, status_code=status.HTTP_201_CREATED)
async def record_my_consent(
    consent_data: ConsentCreate,
    request: Request,
    current_user: User = Depends(get_current_user_without_consent),
    session: AsyncSession = Depends(get_async_session),
) -> UserConsent:
    """
    Record or update the current user's consent.

    Creates a new consent record if none exists, or updates the existing one
    if the user is re-consenting (e.g., after policy updates).

    Captures IP address and user agent for legal proof of consent (GDPR).
    """
    # Query for fresh consent data to check if updating or creating
    result = await session.execute(
        select(UserConsent).where(UserConsent.user_id == current_user.id),
    )
    existing_consent = result.scalar_one_or_none()

    # Extract IP and user agent for legal proof
    ip_address = get_client_ip(request)
    user_agent = request.headers.get("User-Agent")

    if existing_consent:
        # Update existing consent (user re-consenting)
        existing_consent.consented_at = datetime.now(UTC)
        existing_consent.privacy_policy_version = consent_data.privacy_policy_version
        existing_consent.terms_of_service_version = consent_data.terms_of_service_version
        existing_consent.ip_address = ip_address
        existing_consent.user_agent = user_agent
        consent = existing_consent
    else:
        # Create new consent record
        consent = UserConsent(
            user_id=current_user.id,
            consented_at=datetime.now(UTC),
            privacy_policy_version=consent_data.privacy_policy_version,
            terms_of_service_version=consent_data.terms_of_service_version,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        session.add(consent)

    await session.commit()
    await session.refresh(consent)

    return consent
