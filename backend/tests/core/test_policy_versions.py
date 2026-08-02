"""
Contract tests for the published policy version constants.

These constants outlived the consent gate: `GET /consent/versions` serves them
and the public Privacy Policy / Terms pages render them as the "Last Updated"
date (`frontend/src/hooks/usePolicyVersions.ts` does
`new Date(version + 'T00:00:00')`). A malformed value passes silently on the
backend and surfaces as "Invalid Date" on a published legal page.

This lived in `test_consent.py` until 2026-08-01 and was deleted along with it
when the gate was retired — collateral damage, since the contract has nothing
to do with enforcement. It sits next to the module it guards now so its
lifetime matches what it protects.
"""
from datetime import date

import pytest

from core.policy_versions import PRIVACY_POLICY_VERSION, TERMS_OF_SERVICE_VERSION


@pytest.mark.parametrize(
    ("name", "version"),
    [
        ("PRIVACY_POLICY_VERSION", PRIVACY_POLICY_VERSION),
        ("TERMS_OF_SERVICE_VERSION", TERMS_OF_SERVICE_VERSION),
    ],
)
def test__version__is_a_real_calendar_date_in_iso_form(name: str, version: str) -> None:
    """
    Round-trip through `date.fromisoformat` rather than matching a pattern.

    Stronger than the regex this replaces in two ways: it rejects impossible
    dates like 2026-02-30, and the `.isoformat()` comparison rejects the compact
    `20260801` form that bare `fromisoformat` accepts on Python 3.11+ but which
    the frontend's `new Date(v + 'T00:00:00')` cannot parse.
    """
    assert date.fromisoformat(version).isoformat() == version, (
        f"{name} ({version!r}) must be an ISO YYYY-MM-DD calendar date — it is "
        "rendered as the 'Last Updated' date on the public legal pages."
    )
