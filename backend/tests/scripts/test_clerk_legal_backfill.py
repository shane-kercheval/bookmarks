"""
Unit tests for the Clerk legal_accepted_at backfill script's decision logic.

The classification is what carries data risk — a wrong call either overwrites a
better record with a worse one or silently skips a user — so it is tested
exhaustively here. The thin API-calling shell is exercised in the dev-instance
rehearsal, not unit-tested, except for the read-back verification path (which
exists precisely because an ambiguous write failure is expensive).
"""
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from clerk_legal_backfill import (
    AGREEMENT_TOLERANCE_SECONDS,
    AlreadyPopulated,
    BackfillPlan,
    DbRow,
    WriteAction,
    build_plan,
    execute_plan,
    format_report,
    from_clerk_millis,
    to_rfc3339,
)

from core.policy_versions import PRIVACY_POLICY_VERSION, TERMS_OF_SERVICE_VERSION

CONSENTED = datetime(2026, 3, 14, 9, 30, 0, tzinfo=UTC)


def _row(
    user_id: str = "u1",
    external_auth_id: str = "user_clerk1",
    consented_at: datetime | None = CONSENTED,
    privacy: str | None = PRIVACY_POLICY_VERSION,
    terms: str | None = TERMS_OF_SERVICE_VERSION,
) -> DbRow:
    return DbRow(
        user_id=user_id,
        external_auth_id=external_auth_id,
        consented_at=consented_at,
        privacy_policy_version=privacy,
        terms_of_service_version=terms,
    )


def _millis(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


class TestTimestampFormatting:
    """Clerk reads epoch-ms and writes RFC3339 — both directions must be exact."""

    def test__to_rfc3339__emits_zulu_with_milliseconds(self) -> None:
        assert to_rfc3339(datetime(2012, 10, 20, 7, 15, 20, 902000, tzinfo=UTC)) == (
            "2012-10-20T07:15:20.902Z"
        )

    def test__to_rfc3339__converts_non_utc_offset_to_utc(self) -> None:
        from datetime import timedelta, timezone  # noqa: PLC0415 - local to this assertion

        pacific = timezone(timedelta(hours=-8))
        aware = datetime(2026, 3, 14, 1, 30, 0, tzinfo=pacific)
        assert to_rfc3339(aware) == "2026-03-14T09:30:00.000Z"

    def test__to_rfc3339__treats_naive_as_utc(self) -> None:
        assert to_rfc3339(datetime(2026, 3, 14, 9, 30, 0)) == "2026-03-14T09:30:00.000Z"

    def test__from_clerk_millis__round_trips(self) -> None:
        assert from_clerk_millis(_millis(CONSENTED)) == CONSENTED

    def test__round_trip_through_both_directions_is_stable(self) -> None:
        """A value this script writes must read back as agreeing, not differing."""
        populated = AlreadyPopulated(
            clerk_user_id="user_clerk1",
            db_user_id="u1",
            consented_at=CONSENTED,
            clerk_accepted_at=from_clerk_millis(_millis(CONSENTED)),
        )
        assert populated.agrees


class TestDestinationStates:
    """The three destination states the plan enumerates."""

    def test__null_destination__is_written(self) -> None:
        plan = build_plan([_row()], {"user_clerk1": None})

        assert plan.is_clean
        assert plan.writes == [
            WriteAction(clerk_user_id="user_clerk1", db_user_id="u1", consented_at=CONSENTED),
        ]
        assert plan.populated == []

    def test__equal_destination__is_reported_not_written(self) -> None:
        plan = build_plan([_row()], {"user_clerk1": _millis(CONSENTED)})

        assert plan.writes == []
        assert len(plan.populated) == 1
        assert plan.populated[0].agrees

    def test__differing_destination__is_reported_not_written(self) -> None:
        """A genuine Clerk sign-up timestamp must never be replaced by Tiddly's later row."""
        clerk_signup = datetime(2026, 8, 1, 22, 20, 8, tzinfo=UTC)
        plan = build_plan([_row()], {"user_clerk1": _millis(clerk_signup)})

        assert plan.writes == []
        assert len(plan.populated) == 1
        assert not plan.populated[0].agrees
        assert plan.populated[0].clerk_accepted_at == clerk_signup

    def test__difference_within_tolerance__counts_as_agreeing(self) -> None:
        near = CONSENTED.timestamp() * 1000 + (AGREEMENT_TOLERANCE_SECONDS * 1000)
        plan = build_plan([_row()], {"user_clerk1": int(near)})

        assert plan.populated[0].agrees

    def test__difference_beyond_tolerance__counts_as_differing(self) -> None:
        far = CONSENTED.timestamp() * 1000 + (AGREEMENT_TOLERANCE_SECONDS * 1000) + 1000
        plan = build_plan([_row()], {"user_clerk1": int(far)})

        assert not plan.populated[0].agrees


class TestRowSelection:
    """Which users get written, counted, or failed."""

    def test__no_consent_row__is_left_null_and_counted(self) -> None:
        plan = build_plan([_row(consented_at=None, privacy=None, terms=None)], {"user_clerk1": None})

        assert plan.writes == []
        assert plan.no_consent_row == ["u1"]

    def test__stale_versions__still_written_but_counted_separately(self) -> None:
        """Stale rows are real acceptances — they backfill, and the count is surfaced."""
        plan = build_plan([_row(privacy="2025-12-20", terms="2025-12-20")], {"user_clerk1": None})

        assert len(plan.writes) == 1
        assert plan.stale_version_rows == ["u1"]

    def test__current_versions__are_not_counted_as_stale(self) -> None:
        plan = build_plan([_row()], {"user_clerk1": None})

        assert plan.stale_version_rows == []

    def test__one_stale_version_of_two__counts_as_stale(self) -> None:
        plan = build_plan([_row(privacy="2025-12-20")], {"user_clerk1": None})

        assert plan.stale_version_rows == ["u1"]

    def test__mixed_population__classifies_each_independently(self) -> None:
        rows = [
            _row("u1", "user_a"),
            _row("u2", "user_b", consented_at=None, privacy=None, terms=None),
            _row("u3", "user_c"),
        ]
        plan = build_plan(
            rows,
            {"user_a": None, "user_b": None, "user_c": _millis(CONSENTED)},
        )

        assert plan.is_clean
        assert [w.db_user_id for w in plan.writes] == ["u1"]
        assert plan.no_consent_row == ["u2"]
        assert [p.db_user_id for p in plan.populated] == ["u3"]
        assert plan.total_users == 3


class TestUnmatchedRowHardFail:
    """An external_auth_id with no live Clerk user stops the run — never a silent skip."""

    def test__unmatched_row__is_a_failure(self) -> None:
        plan = build_plan([_row(external_auth_id="user_ghost")], {})

        assert not plan.is_clean
        assert len(plan.failures) == 1
        assert "user_ghost" in plan.failures[0]

    def test__unmatched_row__is_not_written(self) -> None:
        plan = build_plan([_row(external_auth_id="user_ghost")], {})

        assert plan.writes == []

    def test__one_unmatched_row__blocks_the_whole_run(self) -> None:
        """Preflight is all-or-nothing: a good row alongside a bad one still stops."""
        rows = [_row("u1", "user_a"), _row("u2", "user_ghost")]
        plan = build_plan(rows, {"user_a": None})

        assert not plan.is_clean
        assert len(plan.writes) == 1  # planned, but is_clean gates execution

    def test__unmatched_row__is_not_miscounted_as_missing_consent(self) -> None:
        plan = build_plan([_row(external_auth_id="user_ghost", consented_at=None)], {})

        assert plan.no_consent_row == []
        assert len(plan.failures) == 1

    def test__missing_identity__fails_with_a_schema_diagnosis_not_a_clerk_one(self) -> None:
        """
        A NULL external_auth_id is impossible post-M6b, so blaming the Clerk
        instance would send the operator hunting in the wrong system.
        """
        plan = build_plan([_row(external_auth_id="")], {"user_clerk1": None})

        assert not plan.is_clean
        assert "no external_auth_id" in plan.failures[0]
        assert "behind head" in plan.failures[0]
        assert "Clerk instance" not in plan.failures[0]


class TestReport:
    """The report is the artifact the operator decides from."""

    def test__reports_both_never_accepted_cohorts(self) -> None:
        rows = [
            _row("u1", "user_a", consented_at=None, privacy=None, terms=None),
            _row("u2", "user_b", privacy="2025-12-20", terms="2025-12-20"),
        ]
        plan = build_plan(rows, {"user_a": None, "user_b": None})
        report = format_report(plan, rows, executed=False)

        assert "no user_consents row at all:   1" in report
        assert "row names STALE versions:      1" in report

    def test__reconciliation_accounts_for_every_user(self) -> None:
        rows = [
            _row("u1", "user_a"),
            _row("u2", "user_b", consented_at=None),
            _row("u3", "user_c"),
        ]
        plan = build_plan(rows, {"user_a": None, "user_b": None, "user_c": _millis(CONSENTED)})

        assert "OK" in format_report(plan, rows, executed=False)

    def test__differing_pairs_are_named_with_both_values(self) -> None:
        clerk_signup = datetime(2026, 8, 1, 22, 20, 8, tzinfo=UTC)
        rows = [_row()]
        plan = build_plan(rows, {"user_clerk1": _millis(clerk_signup)})
        report = format_report(plan, rows, executed=False)

        assert "2026-08-01T22:20:08.000Z" in report
        assert "2026-03-14T09:30:00.000Z" in report
        assert "operator decision" in report

    def test__failures_are_shown_with_nothing_written(self) -> None:
        rows = [_row(external_auth_id="user_ghost")]
        report = format_report(build_plan(rows, {}), rows, executed=False)

        assert "PREFLIGHT FAILURES (1)" in report
        assert "nothing will be written" in report

    def test__distribution_groups_by_month(self) -> None:
        rows = [
            _row("u1", "user_a", consented_at=datetime(2026, 3, 1, tzinfo=UTC)),
            _row("u2", "user_b", consented_at=datetime(2026, 3, 28, tzinfo=UTC)),
            _row("u3", "user_c", consented_at=datetime(2026, 7, 31, tzinfo=UTC)),
        ]
        plan = build_plan(rows, {"user_a": None, "user_b": None, "user_c": None})
        report = format_report(plan, rows, executed=False)

        assert "2026-03" in report
        assert "2026-07" in report


class TestExecuteReadBack:
    """Writes are confirmed by reading the user back, not by trusting the call."""

    async def test__confirms_a_write_that_landed(self) -> None:
        plan = BackfillPlan(
            writes=[WriteAction("user_clerk1", "u1", CONSENTED)],
            total_users=1,
        )
        clerk = AsyncMock()
        clerk.users.get_async.return_value = type(
            "U", (), {"legal_accepted_at": _millis(CONSENTED)},
        )()

        assert await execute_plan(plan, clerk) == 1
        clerk.users.update_async.assert_awaited_once_with(
            user_id="user_clerk1",
            legal_accepted_at="2026-03-14T09:30:00.000Z",
        )

    async def test__does_not_confirm_when_read_back_is_null(self) -> None:
        """The update call 'succeeding' is not evidence the field landed."""
        plan = BackfillPlan(writes=[WriteAction("user_clerk1", "u1", CONSENTED)], total_users=1)
        clerk = AsyncMock()
        clerk.users.get_async.return_value = type("U", (), {"legal_accepted_at": None})()

        assert await execute_plan(plan, clerk) == 0

    async def test__does_not_confirm_when_read_back_differs(self) -> None:
        plan = BackfillPlan(writes=[WriteAction("user_clerk1", "u1", CONSENTED)], total_users=1)
        clerk = AsyncMock()
        wrong = _millis(datetime(2020, 1, 1, tzinfo=UTC))
        clerk.users.get_async.return_value = type("U", (), {"legal_accepted_at": wrong})()

        assert await execute_plan(plan, clerk) == 0

    async def test__preserves_the_recorded_instant_rather_than_now(self) -> None:
        """Writing `now` would destroy the only record of when acceptance happened."""
        plan = BackfillPlan(writes=[WriteAction("user_clerk1", "u1", CONSENTED)], total_users=1)
        clerk = AsyncMock()
        clerk.users.get_async.return_value = type(
            "U", (), {"legal_accepted_at": _millis(CONSENTED)},
        )()

        await execute_plan(plan, clerk)

        sent = clerk.users.update_async.await_args.kwargs["legal_accepted_at"]
        assert sent == "2026-03-14T09:30:00.000Z"
