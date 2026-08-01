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
    no consent row                        -> leave null; that is the accurate state
    external_auth_id with no Clerk user   -> HARD FAILURE (never guess-match)

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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.policy_versions import PRIVACY_POLICY_VERSION, TERMS_OF_SERVICE_VERSION
from models.user import User
from models.user_consent import UserConsent

CLERK_PAGE_SIZE = 500
RATE_LIMIT_MAX_ATTEMPTS = 6

# Clerk's API is asymmetric on this field: it *returns* epoch milliseconds
# (int) and *accepts* an RFC3339 string. Both directions are exercised here, so
# comparisons happen on datetimes and only the write is formatted.
#
# Agreement is judged at whole-second granularity: a value this script wrote
# round-trips through RFC3339 and back, and holding sub-second equality would
# make the idempotent re-run report spurious differences.
AGREEMENT_TOLERANCE_SECONDS = 1


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
        """True when both records name the same instant (to the second)."""
        delta = abs((self.clerk_accepted_at - self.consented_at).total_seconds())
        return delta <= AGREEMENT_TOLERANCE_SECONDS


@dataclass
class BackfillPlan:
    """The full intended set of writes, plus everything that must stop the run."""

    writes: list[WriteAction] = field(default_factory=list)
    populated: list[AlreadyPopulated] = field(default_factory=list)
    no_consent_row: list[str] = field(default_factory=list)  # db user ids
    stale_version_rows: list[str] = field(default_factory=list)  # db user ids, subset of writes
    failures: list[str] = field(default_factory=list)
    total_users: int = 0

    @property
    def is_clean(self) -> bool:
        """True when nothing blocks execution."""
        return not self.failures


def to_rfc3339(moment: datetime) -> str:
    """
    Format a timestamp the way Clerk's updateUser expects (e.g. 2012-10-20T07:15:20.902Z).

    A naive datetime is treated as UTC rather than rejected: the column is
    timezone-aware, so this only guards against a driver returning naive values.
    """
    aware = moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    return aware.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


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

        if row.external_auth_id not in clerk_accepted:
            plan.failures.append(
                f"users.id={row.user_id} has external_auth_id={row.external_auth_id}, "
                "but no such user exists on the target Clerk instance. Wrong instance "
                "or stale row.",
            )
            continue

        if not row.has_consent:
            plan.no_consent_row.append(row.user_id)
            continue

        assert row.consented_at is not None
        if not row.names_current_versions:
            plan.stale_version_rows.append(row.user_id)

        destination = clerk_accepted[row.external_auth_id]
        if destination is None:
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
                    clerk_accepted_at=from_clerk_millis(destination),
                ),
            )

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

    lines.append("")
    lines.append("Cohorts that have never accepted the current documents:")
    lines.append(f"  no user_consents row at all:   {len(plan.no_consent_row)}")
    lines.append(f"  row names STALE versions:      {len(plan.stale_version_rows)}")
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

    accounted = len(plan.writes) + len(plan.populated) + len(plan.no_consent_row)
    reconciled = accounted + len(plan.failures) == plan.total_users
    lines.append("")
    lines.append(
        f"Reconciliation: {len(plan.writes)} writes + {len(plan.populated)} populated + "
        f"{len(plan.no_consent_row)} no-row + {len(plan.failures)} failed == "
        f"{plan.total_users} users: {'OK' if reconciled else 'MISMATCH'}",
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


async def fetch_db_rows(session_factory: async_sessionmaker) -> list[DbRow]:
    """Read every user with its consent row, if any (outer join — users without one count)."""
    async with session_factory() as session:
        result = await session.execute(
            select(
                User.id,
                User.external_auth_id,
                UserConsent.consented_at,
                UserConsent.privacy_policy_version,
                UserConsent.terms_of_service_version,
            ).outerjoin(UserConsent, UserConsent.user_id == User.id),
        )
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


async def execute_plan(plan: BackfillPlan, clerk: Clerk) -> int:
    """
    Apply the planned writes, verifying each by reading the user back.

    Read-back rather than trusting the call's result: the M6a experience was
    that an ambiguous write failure costs far more debugging time than one
    extra GET per user. Returns the number of writes confirmed landed.
    """
    confirmed = 0
    for action in plan.writes:
        stamp = to_rfc3339(action.consented_at)
        await _call_with_backoff(
            partial(
                clerk.users.update_async,
                user_id=action.clerk_user_id,
                legal_accepted_at=stamp,
            ),
            f"users.update ({action.clerk_user_id})",
        )
        readback = await _call_with_backoff(
            partial(clerk.users.get_async, user_id=action.clerk_user_id),
            f"users.get ({action.clerk_user_id})",
        )
        landed = readback.legal_accepted_at if readback is not None else None
        if landed is None:
            print(f"  ! {action.clerk_user_id}: write did not land (read back null)")
            continue
        drift = abs((from_clerk_millis(landed) - action.consented_at).total_seconds())
        if drift > AGREEMENT_TOLERANCE_SECONDS:
            print(
                f"  ! {action.clerk_user_id}: read back {to_rfc3339(from_clerk_millis(landed))}, "
                f"expected {stamp}",
            )
            continue
        print(f"  {action.clerk_user_id} <- {stamp} (verified)")
        confirmed += 1
    return confirmed


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
            clerk_accepted = await fetch_clerk_accepted(clerk)
            db_rows = await fetch_db_rows(session_factory)
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
            confirmed = await execute_plan(plan, clerk)
            print(f"\nConfirmed {confirmed} of {len(plan.writes)} writes.")
            if confirmed != len(plan.writes):
                print("VERIFICATION FAILED — investigate before proceeding.")
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
