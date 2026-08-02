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

import clerk_legal_backfill
import pytest
from clerk_backend_api import models as clerk_models
from clerk_legal_backfill import (
    AlreadyPopulated,
    BackfillPlan,
    DbRow,
    ExecutionResult,
    WriteAction,
    _call_with_backoff,
    build_plan,
    execute_plan,
    fetch_clerk_accepted,
    format_report,
    from_clerk_millis,
    to_epoch_millis,
    to_rfc3339,
)

from core.policy_versions import PRIVACY_POLICY_VERSION, TERMS_OF_SERVICE_VERSION

CONSENTED = datetime(2026, 3, 14, 9, 30, 0, tzinfo=UTC)
# The shape 100% of production rows have: consented_at comes from
# datetime.now(UTC) into a timestamptz column, so it carries microseconds.
CONSENTED_REAL = datetime(2026, 3, 14, 9, 30, 0, 902437, tzinfo=UTC)


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


def _named_user(user_id: str, legal_accepted_at: int | None) -> object:
    return type("U", (), {"id": user_id, "legal_accepted_at": legal_accepted_at})()


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

    def test__to_rfc3339__rejects_naive_rather_than_assuming_utc(self) -> None:
        """Naive is impossible from a timestamptz column, so guessing an offset is wrong."""
        with pytest.raises(ValueError, match="naive datetime"):
            to_rfc3339(datetime(2026, 3, 14, 9, 30, 0))

    def test__to_epoch_millis__rejects_naive(self) -> None:
        with pytest.raises(ValueError, match="naive datetime"):
            to_epoch_millis(datetime(2026, 3, 14, 9, 30, 0))

    def test__from_clerk_millis__round_trips(self) -> None:
        assert from_clerk_millis(_millis(CONSENTED)) == CONSENTED

    def test__truncation_parity__rfc3339_and_epoch_millis_agree(self) -> None:
        """
        The load-bearing invariant: both must truncate identically.

        With the tolerance window gone nothing absorbs divergence, so a change
        to either function (rounding instead of truncating, a different
        timespec) would surface as spurious DIFFERING rows in a production
        report. Assert it directly rather than inferring it from behavior.
        """
        for microsecond in (0, 1, 499, 500, 999, 1000, 902437, 999999):
            moment = CONSENTED.replace(microsecond=microsecond)
            from_string = from_clerk_millis(
                int(
                    datetime.fromisoformat(
                        to_rfc3339(moment).replace("Z", "+00:00"),
                    ).timestamp() * 1000,
                ),
            )
            assert to_epoch_millis(from_string) == to_epoch_millis(moment), (
                f"divergence at {microsecond}µs"
            )

    def test__microsecond_row_round_trips_to_agreeing(self) -> None:
        """
        Production rows carry microseconds; the write truncates to milliseconds.

        Without this the suite only ever exercised whole-second fixtures, which
        is the one shape that never occurs — and the drift it hides (~0.4ms) was
        what the old one-second tolerance was silently absorbing.
        """
        written_back = from_clerk_millis(to_epoch_millis(CONSENTED_REAL))
        populated = AlreadyPopulated(
            clerk_user_id="user_clerk1",
            db_user_id="u1",
            consented_at=CONSENTED_REAL,
            clerk_accepted_at=written_back,
        )
        assert populated.agrees
        assert written_back != CONSENTED_REAL  # truncation really happened


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

    def test__one_millisecond_apart__counts_as_differing(self) -> None:
        """
        Hardcoded, not derived from a constant.

        The old tests computed their inputs from the tolerance, so they passed
        for any value it held — including one wide enough to hide a genuine
        Clerk sign-up timestamp recorded a second from the Tiddly row.
        """
        plan = build_plan([_row()], {"user_clerk1": _millis(CONSENTED) + 1})

        assert not plan.populated[0].agrees

    def test__one_second_apart__counts_as_differing(self) -> None:
        """The exact case the previous one-second tolerance silently swallowed."""
        plan = build_plan([_row()], {"user_clerk1": _millis(CONSENTED) + 1000})

        assert not plan.populated[0].agrees

    def test__sub_millisecond_truncation__counts_as_agreeing(self) -> None:
        """The only difference that should be forgiven is the write's own truncation."""
        plan = build_plan(
            [_row(consented_at=CONSENTED_REAL)],
            {"user_clerk1": to_epoch_millis(CONSENTED_REAL)},
        )

        assert plan.populated[0].agrees


class TestRowSelection:
    """Which users get written, counted, or failed."""

    def test__no_row_and_null_destination__is_no_acceptance_anywhere(self) -> None:
        plan = build_plan([_row(consented_at=None, privacy=None, terms=None)], {"user_clerk1": None})

        assert plan.writes == []
        assert plan.no_acceptance_anywhere == ["u1"]
        assert plan.clerk_only == []

    def test__no_row_but_populated_destination__is_clerk_only_not_never_accepted(self) -> None:
        """
        This user DID accept — via Clerk's checkbox — and must not inflate the
        never-accepted cohort, which is the number the gate-removal decision
        rests on. It is the shape every post-merge sign-up takes.
        """
        plan = build_plan(
            [_row(consented_at=None, privacy=None, terms=None)],
            {"user_clerk1": _millis(CONSENTED)},
        )

        assert plan.writes == []
        assert plan.no_acceptance_anywhere == []
        assert [c.db_user_id for c in plan.clerk_only] == ["u1"]
        assert plan.clerk_only[0].clerk_accepted_at == CONSENTED

    def test__report_separates_clerk_only_from_never_accepted(self) -> None:
        rows = [
            _row("u1", "user_a", consented_at=None, privacy=None, terms=None),
            _row("u2", "user_b", consented_at=None, privacy=None, terms=None),
        ]
        plan = build_plan(rows, {"user_a": None, "user_b": _millis(CONSENTED)})
        report = format_report(plan, rows, executed=False)

        assert "no acceptance anywhere:        1" in report
        assert "Accepted via Clerk only:         1" in report

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
        assert plan.no_acceptance_anywhere == ["u2"]
        assert [p.db_user_id for p in plan.populated] == ["u3"]
        assert plan.total_users == 3

    def test__every_user_lands_in_exactly_one_exclusive_bucket(self) -> None:
        """
        The five exclusive buckets must partition the user set.

        `stale_version_rows` is deliberately EXCLUDED from this check: it is a
        cross-cutting tag on the Tiddly row, appended before the destination is
        examined, so a stale row legitimately also appears in `writes` or
        `populated`. Asserting no-double-bucketing across it would fail on
        correct behavior and invite someone to "fix" the code.
        """
        rows = [
            _row("u1", "user_a"),
            _row("u2", "user_b", consented_at=None, privacy=None, terms=None),
            _row("u3", "user_c"),
            _row("u4", "user_d", consented_at=None, privacy=None, terms=None),
            _row("u5", "user_ghost"),
            _row("u6", "user_e", privacy="2025-12-20", terms="2025-12-20"),
        ]
        plan = build_plan(
            rows,
            {
                "user_a": None,
                "user_b": None,
                "user_c": _millis(CONSENTED),
                "user_d": _millis(CONSENTED),
                "user_e": None,
            },
        )

        buckets = [
            {w.db_user_id for w in plan.writes},
            {p.db_user_id for p in plan.populated},
            {c.db_user_id for c in plan.clerk_only},
            set(plan.no_acceptance_anywhere),
            {"u5"},  # the failure
        ]
        seen: set[str] = set()
        for bucket in buckets:
            assert not (seen & bucket), f"user in two buckets: {seen & bucket}"
            seen |= bucket
        assert seen == {"u1", "u2", "u3", "u4", "u5", "u6"}
        # The cross-cutting tag overlaps by design.
        assert plan.stale_version_rows == ["u6"]
        assert "u6" in {w.db_user_id for w in plan.writes}

    def test__a_branch_that_loses_a_user_raises(self) -> None:
        """The accounting assertion must block, not print a warning and proceed."""
        plan = BackfillPlan(total_users=3)
        plan.writes.append(WriteAction("user_a", "u1", CONSENTED))

        with pytest.raises(AssertionError, match="lost or double-counted"):
            plan.assert_every_user_accounted()


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

        assert plan.no_acceptance_anywhere == []
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

        assert "no acceptance anywhere:        1" in report
        assert "row names STALE versions:      1" in report

    def test__shows_the_arithmetic_behind_the_cohort_counts(self) -> None:
        """
        The accounting line exists so the operator can check the cohort numbers
        add up. It cannot fail here — `build_plan` raises first — so this
        asserts the breakdown is shown, not that a check passed.
        """
        rows = [
            _row("u1", "user_a"),
            _row("u2", "user_b", consented_at=None),
            _row("u3", "user_c"),
        ]
        plan = build_plan(rows, {"user_a": None, "user_b": None, "user_c": _millis(CONSENTED)})

        assert (
            "Accounted: 1 writes + 1 populated + 0 clerk-only + 1 none + 0 failed == 3 users"
            in format_report(plan, rows, executed=False)
        )

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


def _user(legal_accepted_at: int | None) -> object:
    return type("U", (), {"legal_accepted_at": legal_accepted_at})()


def _one_write_plan() -> BackfillPlan:
    return BackfillPlan(writes=[WriteAction("user_clerk1", "u1", CONSENTED)], total_users=1)


class TestExecuteReadBack:
    """Writes are confirmed by reading the user back, not by trusting the call."""

    async def test__confirms_a_write_that_landed(self) -> None:
        clerk = AsyncMock()
        # Pre-write re-read (null), then post-write read-back (landed).
        clerk.users.get_async.side_effect = [_user(None), _user(_millis(CONSENTED))]

        result = await execute_plan(_one_write_plan(), clerk)

        assert result.confirmed == ["user_clerk1"]
        assert result.is_complete
        clerk.users.update_async.assert_awaited_once_with(
            user_id="user_clerk1",
            legal_accepted_at="2026-03-14T09:30:00.000Z",
        )

    async def test__skips_and_stops_when_destination_populated_since_planning(self) -> None:
        """The never-overwrite guarantee must hold at the moment of the write."""
        clerk = AsyncMock()
        clerk.users.get_async.return_value = _user(_millis(CONSENTED))

        result = await execute_plan(_one_write_plan(), clerk)

        clerk.users.update_async.assert_not_awaited()
        assert result.late_populated == ["user_clerk1"]
        assert not result.is_complete

    async def test__does_not_confirm_when_read_back_is_null(self) -> None:
        """The update call 'succeeding' is not evidence the field landed."""
        clerk = AsyncMock()
        clerk.users.get_async.side_effect = [_user(None), _user(None)]

        result = await execute_plan(_one_write_plan(), clerk)

        assert result.failed == ["user_clerk1"]
        assert not result.is_complete

    async def test__does_not_confirm_when_read_back_differs(self) -> None:
        clerk = AsyncMock()
        wrong = _millis(datetime(2020, 1, 1, tzinfo=UTC))
        clerk.users.get_async.side_effect = [_user(None), _user(wrong)]

        result = await execute_plan(_one_write_plan(), clerk)

        assert result.failed == ["user_clerk1"]

    async def test__resolves_by_read_back_when_the_update_raises(self) -> None:
        """An exception doesn't prove nothing landed — the read-back decides."""
        clerk = AsyncMock()
        clerk.users.update_async.side_effect = RuntimeError("connection reset")
        clerk.users.get_async.side_effect = [_user(None), _user(_millis(CONSENTED))]

        result = await execute_plan(_one_write_plan(), clerk)

        assert result.confirmed == ["user_clerk1"]

    async def test__stops_at_the_first_unverified_write(self) -> None:
        """
        A systemic cause would otherwise corrupt every remaining user, with no
        undo. Re-running is safe, so stopping early costs nothing.
        """
        plan = BackfillPlan(
            writes=[
                WriteAction("user_a", "u1", CONSENTED),
                WriteAction("user_b", "u2", CONSENTED),
                WriteAction("user_c", "u3", CONSENTED),
            ],
            total_users=3,
        )
        clerk = AsyncMock()
        clerk.users.get_async.side_effect = [
            _user(None), _user(_millis(CONSENTED)),   # user_a confirms
            _user(None), _user(None),                 # user_b fails verification
        ]

        result = await execute_plan(plan, clerk)

        assert result.confirmed == ["user_a"]
        assert result.failed == ["user_b"]
        assert result.not_attempted == ["user_c"]
        assert clerk.users.update_async.await_count == 2

    async def test__accumulates_into_a_caller_held_result_so_a_crash_still_reports(self) -> None:
        """A mid-loop exception must not make landed writes look un-attempted."""
        plan = BackfillPlan(
            writes=[
                WriteAction("user_a", "u1", CONSENTED),
                WriteAction("user_b", "u2", CONSENTED),
            ],
            total_users=2,
        )
        clerk = AsyncMock()
        clerk.users.get_async.side_effect = [
            _user(None), _user(_millis(CONSENTED)),   # user_a confirms
            RuntimeError("clerk unreachable"),        # user_b: pre-read explodes
        ]
        result = ExecutionResult()

        with pytest.raises(RuntimeError):
            await execute_plan(plan, clerk, result)

        assert result.confirmed == ["user_a"]
        assert result.not_attempted == []  # user_b was attempted, not skipped

    async def test__preserves_the_recorded_instant_rather_than_now(self) -> None:
        """Writing `now` would destroy the only record of when acceptance happened."""
        clerk = AsyncMock()
        clerk.users.get_async.side_effect = [_user(None), _user(_millis(CONSENTED))]

        await execute_plan(_one_write_plan(), clerk)

        assert (
            clerk.users.update_async.await_args.kwargs["legal_accepted_at"]
            == "2026-03-14T09:30:00.000Z"
        )


class TestCallWithBackoff:
    """Retry logic wrapping every mutating call — a defect here surfaces mid-backfill."""

    def _sdk_error(self, status: int | None) -> clerk_models.SDKError:
        raw = None if status is None else type("R", (), {"status_code": status})()
        error = clerk_models.SDKError.__new__(clerk_models.SDKError)
        error.raw_response = raw
        return error

    async def test__retries_a_429_then_returns(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(clerk_legal_backfill.asyncio, "sleep", AsyncMock())
        calls = [self._sdk_error(429), None]

        async def call() -> str:
            outcome = calls.pop(0)
            if outcome is not None:
                raise outcome
            return "ok"

        assert await _call_with_backoff(call, "test") == "ok"

    async def test__propagates_a_non_429_without_retrying(self) -> None:
        attempts = 0

        async def call() -> str:
            nonlocal attempts
            attempts += 1
            raise self._sdk_error(500)

        with pytest.raises(clerk_models.SDKError):
            await _call_with_backoff(call, "test")
        assert attempts == 1

    async def test__propagates_when_raw_response_is_missing(self) -> None:
        """No raw_response means no status to inspect — treat as non-retryable."""
        async def call() -> str:
            raise self._sdk_error(None)

        with pytest.raises(clerk_models.SDKError):
            await _call_with_backoff(call, "test")

    async def test__exhaustion_reraises_the_sdk_error_not_assertionerror(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The operator must see the rate-limit error, not 'unreachable'."""
        monkeypatch.setattr(clerk_legal_backfill.asyncio, "sleep", AsyncMock())

        async def call() -> str:
            raise self._sdk_error(429)

        with pytest.raises(clerk_models.SDKError):
            await _call_with_backoff(call, "test")


class TestPagination:
    """The fetcher must not miss users — a miss would look like a deleted identity."""

    async def test__collects_every_user_across_a_full_and_partial_page(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(clerk_legal_backfill, "CLERK_PAGE_SIZE", 2)
        pages = [
            [_named_user("user_a", 111), _named_user("user_b", None)],
            [_named_user("user_c", 333)],
        ]
        offsets: list[int] = []

        async def list_async(request: object) -> list:
            offsets.append(request.offset)
            return pages.pop(0) if pages else []

        clerk = AsyncMock()
        clerk.users.list_async.side_effect = list_async

        assert await fetch_clerk_accepted(clerk) == {
            "user_a": 111,
            "user_b": None,
            "user_c": 333,
        }
        assert offsets == [0, 2]
