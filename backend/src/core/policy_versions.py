"""
Policy version constants — the public "Last Updated" date for /privacy and /terms.

Nothing enforces these anymore. The blocking consent gate was retired on
2026-08-01 (docs/implementation_plans/2026-08-01-consent-simplification.md);
initial acceptance is captured by Clerk at sign-up, and policy *changes* go out
by notice. These constants drive the "Last Updated" date the public pages
display (via GET /consent/versions) and nothing else.
"""

# =============================================================================
# VERSION-BUMP RUNBOOK — bumping a constant below obligates ALL of these steps.
#
# 0. FIRST, judge the change. If it is materially adverse — arbitration
#    terms, a change in how user data is used, training on user content —
#    notice alone is NOT the mechanism. Stop and treat it as a feature, not a
#    bump: the consent-simplification plan (*The trade* / *Known
#    limitations*) records the decision that a blocking web-only
#    acknowledgement gets designed fresh at that time. This runbook covers
#    ordinary changes only.
#
# 1. Edit the policy prose in frontend/src/content/prose/ (privacy.md /
#    terms.md) — the markdown is the single source; the .tsx pages are thin
#    renderers.
# 2. Bump the constant(s) below, with a dated comment following the entries
#    beneath — what changed and why. The bump is what advances the public
#    "Last Updated" date.
# 3. Deploy BOTH services and verify live before any notice goes out:
#    /privacy and /terms show the new date and wording, /prose/privacy.md and
#    /prose/terms.md serve the updated markdown, and GET /consent/versions
#    returns the new constants. The frontend and api deploy independently —
#    a notice sent early links users to the old wording.
# 4. Export current user email addresses FROM CLERK (e.g. `clerk api` or the
#    dashboard), not from the local `users.email` column — Clerk requires an
#    email identifier so its list is complete; the local column is nullable.
# 5. Email the notice to those addresses. Frame it as a service message about
#    the terms governing the account: what changed, when it takes effect, and
#    a link to the updated document. Both documents' change-of-terms sections
#    (terms.md "Changes to Terms", privacy.md "Changes to This Policy")
#    promise this notice — sending it is what keeps that promise true.
#
# There is no automated mechanism behind any of this — a deliberate
# scale-matched choice (no transactional-email capability exists in the
# backend), not an oversight.
# =============================================================================

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
