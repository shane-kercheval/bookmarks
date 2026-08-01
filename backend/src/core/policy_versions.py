"""Policy version constants for consent enforcement."""

# Update these when policies change
# 2026-08-01: factual reconciliation of both documents against the shipped
# product (consent-simplification M0). Both had described Tiddly as
# bookmark-only and the AI features as "not yet implemented" while five /ai/*
# suggestion endpoints were live against three providers. Both documents now
# name OpenAI, Anthropic, and Google as processors, describe notes and prompt
# templates as stored content, and disclose that a suggestion request sends
# related data (tag vocabulary, candidate-item excerpts, template bodies) and
# not only the item itself. This is the first bump under the notice-not-
# enforcement model: the blocking re-consent gate is removed in the same
# change, so nobody is prompted to re-accept — the email notice is the whole
# mechanism.
#
# 2026-07-31: both documents' identity-processor disclosures changed from
# Auth0 to Clerk (M6b decommission) — a substantive third-party-processor
# change, so both versions advance and every user re-consents once.
PRIVACY_POLICY_VERSION = "2026-08-01"
TERMS_OF_SERVICE_VERSION = "2026-08-01"
