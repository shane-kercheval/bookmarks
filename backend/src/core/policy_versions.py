"""Policy version constants for consent enforcement."""

# Update these when policies change
# 2026-07-31: both documents' identity-processor disclosures changed from
# Auth0 to Clerk (M6b decommission) — a substantive third-party-processor
# change, so both versions advance and every user re-consents once.
PRIVACY_POLICY_VERSION = "2026-07-31"
TERMS_OF_SERVICE_VERSION = "2026-07-31"
