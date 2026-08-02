r"""
Backfill Clerk's ``legal_accepted_at`` from Tiddly's ``user_consents`` rows.

One-time record-keeping for the consent simplification (see
docs/implementation_plans/2026-08-01-consent-simplification.md). Clerk began
capturing policy acceptance at sign-up when legal consent was enabled on the
instance; without this backfill its field would mean "signed up after we
flipped the toggle" rather than "has accepted the terms".

Source is ``user_consents.consented_at`` — the *latest* acceptance Tiddly
recorded, NOT the original. The table holds exactly one row per user and
re-consent overwrote it in place, so no per-version history exists to carry
over. Destination is ``legal_accepted_at`` on the Clerk user. The join key is
``users.external_auth_id``, which since the M6b decommission migration *is* the
Clerk user ID (non-nullable).

**Writes only where the destination is null.** Once legal consent is live a
user can hold a genuine Clerk sign-up timestamp, and Tiddly's row is the later,
worse record — copying over it would destroy the better one. A populated
destination is classified and reported (agreeing or differing), never
overwritten. There is deliberately no --force: resolving a differing pair is an
operator decision, not something this script should be able to paper over.

The recorded timestamp is preserved rather than stamped with `now`; writing the
backfill date would destroy the only record of when acceptance happened and
make the field actively misleading.

**There is no undo.** Passing ``legal_accepted_at=None`` through the SDK means
"field not provided", not "set to null" (confirmed in the dev rehearsal — the
value survived the call untouched), so a write cannot be reverted with this
tooling. Run the dry-run and read the report before using --execute.

Dry-run is the default; nothing is written without --execute, and no write
happens unless preflight classification is completely clean:

    consent row + null destination        -> write (RFC3339, preserved instant)
    consent row + destination agrees      -> report, no write (the idempotent re-run)
    consent row + destination differs     -> report, no write (operator decision)
    no consent row + populated destination-> accepted via Clerk; nothing to backfill
    no consent row + null destination     -> no acceptance anywhere; leave null
    external_auth_id with no Clerk user   -> HARD FAILURE (never guess-match)

The last two "no consent row" cases are deliberately distinct. Conflating them
inflates the never-accepted cohort — the number the operator uses to decide
whether removing the gate is acceptable — with users who did accept, through
Clerk's checkbox. That is the shape every sign-up takes after the merge, which
is when this runs.

Inputs:
    --database-url   explicit asyncpg URL — deliberately a required flag rather than
                     read from .env, so the script can never write against whatever
                     database the local environment happens to point at
    CLERK_SECRET_KEY (env) — the target Clerk instance's secret key; never logged

Usage:
    PYTHONPATH=backend/src uv run python backend/scripts/clerk_legal_backfill.py \
        --database-url postgresql+asyncpg://user:pass@localhost:5435/dbname [--execute]
"""
import argparse
import asyncio
import os
import sys
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial

from clerk_backend_api import Clerk
from clerk_backend_api import models as clerk_models
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.policy_versions import PRIVACY_POLICY_VERSION, TERMS_OF_SERVICE_VERSION

CLERK_PAGE_SIZE = 500
RATE_LIMIT_MAX_ATTEMPTS = 6

# Clerk's API is asymmetric on this field: it *returns* epoch milliseconds
# (int) and *accepts* an RFC3339 string. `to_rfc3339` truncates to milliseconds
# while `user_consents.consented_at` carries microseconds, so a value this
# script writes reads back up to 999µs earlier than the row it came from.
#
# Comparisons therefore happen on truncated epoch milliseconds, exactly — both
# sides put through the same truncation first. There is deliberately no
# tolerance window: an earlier version allowed one second, which was ~2300x the
# real drift (measured: 0.437ms) and wide enough to silently classify a genuine
# Clerk sign-up timestamp as "the same as" a Tiddly consent row recorded within
# a second of it. That is precisely the difference this script exists to
# surface rather than paper over.
#
# INVARIANT: `to_epoch_millis` and `to_rfc3339` must truncate identically.
# Nothing in the type system enforces that, and with no tolerance left to
# absorb divergence, a change to either (rounding instead of truncating, a
# different `timespec`) reappears as spurious DIFFERING rows in a production
# report. `test__truncation_parity__rfc3339_and_epoch_millis_agree` pins it.
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass
class DbRow:
    """One Tiddly user, with its consent row if it has one."""

    user_id: str
    external_auth_id: str
    consented_at: datetime | None
    privacy_policy_version: str | None
    terms_of_service_version: str | None

    @property
    def has_consent(self) -> bool:
        """True when the user has a `user_consents` row."""
        return self.consented_at is not None

    @property
    def names_current_versions(self) -> bool:
        """True when the consent row names both currently published versions."""
        return (
            self.privacy_policy_version == PRIVACY_POLICY_VERSION
            and self.terms_of_service_version == TERMS_OF_SERVICE_VERSION
        )


@dataclass
class WriteAction:
    """Destination is null — copy Tiddly's recorded acceptance into Clerk."""

    clerk_user_id: str
    db_user_id: str
    consented_at: datetime


@dataclass
class AlreadyPopulated:
    """Destination is non-null — reported, never overwritten."""

    clerk_user_id: str
    db_user_id: str
    consented_at: datetime
    clerk_accepted_at: datetime

    @property
    def agrees(self) -> bool:
        """
        True when both records name the same instant, to the millisecond.

        Exact equality on truncated milliseconds: a value this script wrote
        agrees by construction (same truncation both ways), and anything else is
        a genuinely different acceptance the operator should see.
        """
        return to_epoch_millis(self.clerk_accepted_at) == to_epoch_millis(self.consented_at)


@dataclass
class ClerkOnlyAcceptance:
    """No Tiddly consent row, but Clerk holds an acceptance — nothing to backfill."""

    clerk_user_id: str
    db_user_id: str
    clerk_accepted_at: datetime


@dataclass
class BackfillPlan:
    """The full intended set of writes, plus everything that must stop the run."""

    # The five buckets below are mutually exclusive — every user lands in
    # exactly one, which `assert_every_user_accounted` enforces.
    writes: list[WriteAction] = field(default_factory=list)
    populated: list[AlreadyPopulated] = field(default_factory=list)
    clerk_only: list[ClerkOnlyAcceptance] = field(default_factory=list)
    no_acceptance_anywhere: list[str] = field(default_factory=list)  # db user ids
    failures: list[str] = field(default_factory=list)

    # Deliberately NOT mutually exclusive with the above: staleness is a property
    # of the Tiddly row, tagged before the destination is examined, so a stale
    # row also appears in `writes` or `populated`. Excluded from the accounting
    # assertion for that reason.
    stale_version_rows: list[str] = field(default_factory=list)  # db user ids

    total_users: int = 0

    @property
    def is_clean(self) -> bool:
        """True when nothing blocks execution."""
        return not self.failures

    def assert_every_user_accounted(self) -> None:
        """
        Enforce that the five exclusive buckets partition the user set.

        True by construction today — every branch in `build_plan` appends once
        and returns. It is asserted rather than printed because the buckets are
        exactly what changes when someone adds a classification: a new branch
        that forgets to bucket, or one that falls through into two, silently
        corrupts the cohort counts the operator decides from. Raising here makes
        that a failed run instead of a wrong report.
        """
        accounted = (
            len(self.writes)
            + len(self.populated)
            + len(self.clerk_only)
            + len(self.no_acceptance_anywhere)
            + len(self.failures)
        )
        if accounted != self.total_users:
            raise AssertionError(
                f"Classification lost or double-counted users: {accounted} bucketed "
                f"vs {self.total_users} selected. A branch in build_plan is missing "
                "an append, returning early, or falling through into two buckets.",
            )


def _require_aware(moment: datetime) -> datetime:
    """
    Reject a naive datetime rather than assuming UTC.

    `user_consents.consented_at` is `DateTime(timezone=True)`, so naive values
    cannot occur today — which is exactly why guessing at one is wrong. If a
    driver change or a future caller ever produces one, the offset is unknown
    and assuming UTC would write a possibly-wrong instant that cannot be undone.
    """
    if moment.tzinfo is None:
        raise ValueError(
            f"Refusing to interpret naive datetime {moment!r}: consented_at is "
            "timezone-aware, so a naive value means something upstream changed. "
            "Assuming UTC could write the wrong instant, and there is no undo.",
        )
    return moment


def to_rfc3339(moment: datetime) -> str:
    """Format a timestamp the way Clerk's updateUser expects (2012-10-20T07:15:20.902Z)."""
    return (
        _require_aware(moment)
        .astimezone(UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def to_epoch_millis(moment: datetime) -> int:
    """
    Truncate a timestamp to epoch milliseconds — the comparison currency.

    Integer arithmetic rather than `int(dt.timestamp() * 1000)`: the float path
    tested clean over three million microsecond-granularity samples, but it is
    correct by measurement where this is correct by construction, and float64
    resolution degrades as the epoch grows.
    """
    delta = _require_aware(moment).astimezone(UTC) - _EPOCH
    return delta.days * 86_400_000 + delta.seconds * 1_000 + delta.microseconds // 1_000


def from_clerk_millis(millis: int) -> datetime:
    """Convert Clerk's epoch-milliseconds representation to an aware datetime."""
    return datetime.fromtimestamp(millis / 1000, UTC)


def build_plan(db_rows: list[DbRow], clerk_accepted: dict[str, int | None]) -> BackfillPlan:
    """
    Classify every Tiddly user against the Clerk instance.

    `clerk_accepted` maps Clerk user id -> legal_accepted_at (epoch ms or None);
    an id absent from the mapping has no live Clerk user, which is a hard failure
    rather than a skip — it means the two systems disagree about who exists, and
    that needs an operator, not a warning to scroll past.
    """
    plan = BackfillPlan(total_users=len(db_rows))

    for row in db_rows:
        # A row with no identity at all is a different (and worse) finding than one
        # whose identity Clerk doesn't recognise: it cannot be matched by any means,
        # and it should be impossible — external_auth_id is NOT NULL since the M6b
        # decommission migration. Seeing one means the database predates that
        # migration, so say that rather than blaming the Clerk instance.
        if not row.external_auth_id:
            plan.failures.append(
                f"users.id={row.user_id} has no external_auth_id. That column is NOT NULL "
                "as of the M6b decommission migration, so this database is behind head.",
            )
            continue

        # Deliberately no waiver flag. An orphan here is one of three things,
        # each with a real resolution — and the middle one is what
        # docs/architecture.md calls "a privacy-affecting incident, not
        # routine": the user's Tiddly data (and any PATs that still
        # authenticate) outlived their Clerk identity. A generic --allow flag
        # would let this backfill route around that, and skipping would become
        # the path of least resistance.
        if row.external_auth_id not in clerk_accepted:
            plan.failures.append(
                f"users.id={row.user_id} has external_auth_id={row.external_auth_id}, "
                "but no such user exists on the target Clerk instance. Resolve before "
                "re-running — do not skip:\n"
                "      (a) wrong instance — CLERK_SECRET_KEY and --database-url must "
                "name the same environment;\n"
                "      (b) the Clerk identity was deleted but the deletion never "
                "reached Tiddly — replay the user.deleted webhook (README_DEPLOY "
                "Step 6f) so the tombstone, data cascade and PAT revocation happen;\n"
                "      (c) a stale seeded/test row — delete it from that database.",
            )
            continue

        destination_millis = clerk_accepted[row.external_auth_id]

        # No Tiddly row splits two ways, and conflating them inflates the exact
        # number the operator uses to decide whether removing the gate is
        # acceptable. A user who accepted through Clerk's checkbox but has no
        # local row HAS accepted — they are not part of the never-accepted
        # cohort. This is the shape every sign-up takes after the merge removes
        # the gate, which is when this script runs.
        if not row.has_consent:
            if destination_millis is None:
                plan.no_acceptance_anywhere.append(row.user_id)
            else:
                plan.clerk_only.append(
                    ClerkOnlyAcceptance(
                        clerk_user_id=row.external_auth_id,
                        db_user_id=row.user_id,
                        clerk_accepted_at=from_clerk_millis(destination_millis),
                    ),
                )
            continue

        assert row.consented_at is not None
        if not row.names_current_versions:
            plan.stale_version_rows.append(row.user_id)

        if destination_millis is None:
            plan.writes.append(
                WriteAction(
                    clerk_user_id=row.external_auth_id,
                    db_user_id=row.user_id,
                    consented_at=row.consented_at,
                ),
            )
        else:
            plan.populated.append(
                AlreadyPopulated(
                    clerk_user_id=row.external_auth_id,
                    db_user_id=row.user_id,
                    consented_at=row.consented_at,
                    clerk_accepted_at=from_clerk_millis(destination_millis),
                ),
            )

    plan.assert_every_user_accounted()
    return plan


def _consent_distribution(rows: list[DbRow]) -> list[tuple[str, int]]:
    """Count consent rows by year-month, so the cohort's shape is on the record."""
    counter = Counter(
        row.consented_at.astimezone(UTC).strftime("%Y-%m")
        for row in rows
        if row.consented_at is not None
    )
    return sorted(counter.items())


def format_report(plan: BackfillPlan, db_rows: list[DbRow], *, executed: bool) -> str:
    """Render the report the plan requires (counts must net to the user total)."""
    lines: list[str] = []
    mode = "EXECUTE (writes follow below)" if executed else "DRY-RUN (no writes performed)"
    lines.append(f"=== Clerk legal_accepted_at backfill — {mode} ===")
    lines.append(f"Tiddly users selected:           {plan.total_users}")
    lines.append(f"Current policy versions:         {PRIVACY_POLICY_VERSION} / {TERMS_OF_SERVICE_VERSION}")  # noqa: E501
    lines.append("")

    lines.append(f"To write (destination null):     {len(plan.writes)}")
    for w in sorted(plan.writes, key=lambda a: a.consented_at):
        lines.append(f"  + {w.clerk_user_id}  <- {to_rfc3339(w.consented_at)}")

    agreeing = [p for p in plan.populated if p.agrees]
    differing = [p for p in plan.populated if not p.agrees]
    lines.append(f"Already populated (no write):    {len(plan.populated)}")
    lines.append(f"  agreeing:                      {len(agreeing)}")
    lines.append(f"  DIFFERING:                     {len(differing)}")
    for p in differing:
        lines.append(
            f"  ! {p.clerk_user_id}  clerk={to_rfc3339(p.clerk_accepted_at)}  "
            f"tiddly={to_rfc3339(p.consented_at)}  (left as-is — operator decision)",
        )

    lines.append(f"Accepted via Clerk only:         {len(plan.clerk_only)}")
    for c in plan.clerk_only:
        lines.append(
            f"  = {c.clerk_user_id}  ({c.db_user_id})  clerk={to_rfc3339(c.clerk_accepted_at)}  "
            "(no Tiddly row — nothing to backfill)",
        )

    # IDs, not just counts: the moment either number is non-zero the operator's
    # next question is "which users", and the answer is already computed. The
    # plan calls for this disposition to be decided "with the numbers in hand".
    lines.append("")
    lines.append("Cohorts that have never accepted the current documents:")
    lines.append(f"  no acceptance anywhere:        {len(plan.no_acceptance_anywhere)}")
    for user_id in plan.no_acceptance_anywhere:
        lines.append(f"    {user_id}")
    lines.append(f"  row names STALE versions:      {len(plan.stale_version_rows)}")
    for user_id in plan.stale_version_rows:
        lines.append(f"    {user_id}")
    lines.append(
        "  (both are blocked by the consent gate today and get full service once it "
        "is removed; see the plan's Known limitations)",
    )

    distribution = _consent_distribution(db_rows)
    if distribution:
        lines.append("")
        lines.append("Distribution of recorded acceptances (latest per user, by month):")
        for month, count in distribution:
            lines.append(f"  {month}  {'#' * min(count, 40)} {count}")

    # Structural invariant, not a runtime check — `build_plan` raises if it is
    # ever violated, so this line always reads OK. Printed because the operator
    # is entitled to see the arithmetic behind the cohort counts, not because it
    # can fail here.
    lines.append("")
    lines.append(
        f"Accounted: {len(plan.writes)} writes + {len(plan.populated)} populated + "
        f"{len(plan.clerk_only)} clerk-only + {len(plan.no_acceptance_anywhere)} none + "
        f"{len(plan.failures)} failed == {plan.total_users} users",
    )

    if plan.failures:
        lines.append("")
        lines.append(f"PREFLIGHT FAILURES ({len(plan.failures)}) — nothing will be written:")
        for failure in plan.failures:
            lines.append(f"  ! {failure}")
    return "\n".join(lines)


async def _call_with_backoff[T](
    call: Callable[[], Awaitable[T]],
    description: str,
) -> T:
    """Run a Clerk SDK call, backing off on 429s instead of crashing mid-backfill."""
    for attempt in range(RATE_LIMIT_MAX_ATTEMPTS):
        try:
            return await call()
        except clerk_models.SDKError as e:
            status = e.raw_response.status_code if e.raw_response is not None else None
            if status != 429 or attempt == RATE_LIMIT_MAX_ATTEMPTS - 1:
                raise
            delay = min(2 ** attempt, 30)
            print(f"  Clerk rate limit (429) on {description}; retrying in {delay}s...")
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")


async def fetch_clerk_accepted(clerk: Clerk) -> dict[str, int | None]:
    """Map every Clerk user id on the instance to its legal_accepted_at (epoch ms or None)."""
    accepted: dict[str, int | None] = {}
    offset = 0
    while True:
        page = await _call_with_backoff(
            partial(
                clerk.users.list_async,
                request=clerk_models.GetUserListRequest(limit=CLERK_PAGE_SIZE, offset=offset),
            ),
            "users.list",
        )
        if not page:
            break
        for u in page:
            accepted[u.id] = u.legal_accepted_at
        if len(page) < CLERK_PAGE_SIZE:
            break
        offset += CLERK_PAGE_SIZE
    return accepted


# Raw SQL rather than the ORM, deliberately. This script reads `user_consents`,
# which the same change drops — so the model is already gone from the codebase by
# the time an operator runs this. Depending on it would make the script
# unimportable exactly when it is needed. The columns are pinned here instead;
# the table is frozen, so they cannot drift.
_SOURCE_QUERY = text("""
    SELECT u.id,
           u.external_auth_id,
           c.consented_at,
           c.privacy_policy_version,
           c.terms_of_service_version
    FROM users u
    LEFT JOIN user_consents c ON c.user_id = u.id
""")


async def fetch_db_rows(session_factory: async_sessionmaker) -> list[DbRow]:
    """Read every user with its consent row, if any (outer join — users without one count)."""
    async with session_factory() as session:
        result = await session.execute(_SOURCE_QUERY)
        return [
            DbRow(
                user_id=str(row.id),
                external_auth_id=row.external_auth_id,
                consented_at=row.consented_at,
                privacy_policy_version=row.privacy_policy_version,
                terms_of_service_version=row.terms_of_service_version,
            )
            for row in result.all()
        ]


@dataclass
class ExecutionResult:
    """What actually happened, reportable however the run ended."""

    confirmed: list[str] = field(default_factory=list)
    late_populated: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    not_attempted: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        """True when every planned write landed and nothing was left undone."""
        return not self.failed and not self.late_populated and not self.not_attempted


def _readback_millis(user: object | None) -> int | None:
    """Pull legal_accepted_at off a fetched user, tolerating a missing user."""
    return getattr(user, "legal_accepted_at", None) if user is not None else None


async def _read_destination(clerk: Clerk, clerk_user_id: str) -> int | None:
    """Fetch the current legal_accepted_at for one Clerk user."""
    user = await _call_with_backoff(
        partial(clerk.users.get_async, user_id=clerk_user_id),
        f"users.get ({clerk_user_id})",
    )
    return _readback_millis(user)


async def execute_plan(
    plan: BackfillPlan,
    clerk: Clerk,
    result: ExecutionResult | None = None,
) -> ExecutionResult:
    """
    Apply the planned writes, verifying each by reading the user back.

    Read-back rather than trusting the call's result: the M6a experience was
    that an ambiguous write failure costs far more debugging time than one extra
    GET per user. An exception during the update does NOT prove nothing landed,
    so the read-back runs even then.

    Stops at the first write that cannot be positively confirmed. There is no
    undo, so if the cause is systemic — Clerk normalising the value, the SDK
    dropping the field — continuing would write a wrong value to the entire
    population before saying so. Re-running is safe (landed writes reclassify as
    agreeing), which makes stopping early free.

    Also re-reads each destination immediately before writing. Note this guards
    an *unmodeled* path rather than a known race: an existing Clerk user can
    acquire `legal_accepted_at` only by completing sign-up (already done) or via
    this script, so no constructible sequence populates a planned destination
    mid-run. It is defence-in-depth on an irreversible write, and it does cover
    two overlapping runs. Overstating what a check does is the failure mode that
    produced the old tolerance window, so it is stated plainly here.

    `result` is accumulated in place so a caller holding a reference can report
    partial progress even if this raises — an exception must not make landed
    writes look un-attempted.
    """
    if result is None:
        result = ExecutionResult()
    result.not_attempted[:] = [a.clerk_user_id for a in plan.writes]

    for action in plan.writes:
        result.not_attempted.remove(action.clerk_user_id)
        expected = to_epoch_millis(action.consented_at)
        stamp = to_rfc3339(action.consented_at)

        current = await _read_destination(clerk, action.clerk_user_id)
        if current is not None:
            print(
                f"  ! {action.clerk_user_id}: destination became populated since planning "
                f"({to_rfc3339(from_clerk_millis(current))}) — not overwriting. Stopping; "
                "re-run the dry-run to re-approve.",
            )
            result.late_populated.append(action.clerk_user_id)
            return result

        try:
            await _call_with_backoff(
                partial(
                    clerk.users.update_async,
                    user_id=action.clerk_user_id,
                    legal_accepted_at=stamp,
                ),
                f"users.update ({action.clerk_user_id})",
            )
        except Exception as e:
            print(f"  ! {action.clerk_user_id}: update raised ({e!r}); reading back to resolve")

        landed = await _read_destination(clerk, action.clerk_user_id)
        if landed != expected:
            actual = to_rfc3339(from_clerk_millis(landed)) if landed is not None else "null"
            print(
                f"  ! {action.clerk_user_id}: read back {actual}, expected {stamp}. "
                "Stopping — a systemic cause would corrupt every remaining user.",
            )
            result.failed.append(action.clerk_user_id)
            return result

        print(f"  {action.clerk_user_id} <- {stamp} (verified)")
        result.confirmed.append(action.clerk_user_id)

    return result


def format_execution_result(result: ExecutionResult, planned: int) -> str:
    """Render the closing accounting — printed however the run ended."""
    lines = [
        "",
        f"Planned writes:   {planned}",
        f"  confirmed:      {len(result.confirmed)}",
    ]
    for user_id in result.confirmed:
        lines.append(f"    {user_id}")
    if result.late_populated:
        lines.append(f"  late-populated: {len(result.late_populated)} (skipped, not overwritten)")
        for user_id in result.late_populated:
            lines.append(f"    {user_id}")
    if result.failed:
        lines.append(f"  FAILED:         {len(result.failed)}")
        for user_id in result.failed:
            lines.append(f"    {user_id}")
    if result.not_attempted:
        lines.append(f"  not attempted:  {len(result.not_attempted)}")
        for user_id in result.not_attempted:
            lines.append(f"    {user_id}")
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        required=True,
        help="Explicit asyncpg database URL (never read from .env by design)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually write to Clerk (default is dry-run)",
    )
    return parser.parse_args(argv)


async def run(args: argparse.Namespace) -> int:
    """Load inputs, build the plan, report, and (with --execute) apply it."""
    secret_key = os.environ.get("CLERK_SECRET_KEY")
    if not secret_key:
        print("CLERK_SECRET_KEY is not set — export the target instance's secret key.")
        return 1

    engine = create_async_engine(args.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Clerk(bearer_auth=secret_key) as clerk:
            # Order matters: database first, Clerk second. A user who signs up
            # between the two fetches then appears only in the Clerk map, where
            # they are an unused key and harmless. The reverse order puts them
            # in `db_rows` but not the Clerk snapshot, which classifies as
            # "no such user on the instance" — a hard failure that blocks every
            # valid write in the run. This backfill runs right after the merge,
            # which is exactly when sign-ups happen.
            db_rows = await fetch_db_rows(session_factory)
            clerk_accepted = await fetch_clerk_accepted(clerk)
            plan = build_plan(db_rows, clerk_accepted)
            print(format_report(plan, db_rows, executed=args.execute))

            if not plan.is_clean:
                return 1
            if not args.execute:
                print("\nDry-run only. Re-run with --execute to apply this plan.")
                return 0
            if not plan.writes:
                print("\nNothing to write.")
                return 0

            print("\nExecuting...")
            result = ExecutionResult()
            try:
                await execute_plan(plan, clerk, result)
            finally:
                # Accounting prints even if execute_plan raises. After an
                # irreversible partial write the operator must not have to
                # reconstruct state from scrollback.
                print(format_execution_result(result, len(plan.writes)))

            if not result.is_complete:
                print("\nRUN INCOMPLETE — resolve the above before re-running.")
                return 1
            return 0
    finally:
        await engine.dispose()


def main() -> None:
    """CLI entry point."""
    args = parse_args(sys.argv[1:])
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
