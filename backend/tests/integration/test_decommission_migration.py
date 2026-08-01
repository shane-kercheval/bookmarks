"""
Data-handling tests for the M6b decommission migration (867f3d604c7c).

The migration's schema half is covered by test_alembic_schema_compat.py; this
module covers its DATA contract (run sheet Ii, amended across the M6b review
rounds) — the pre-migration database states:

- clean (Clerk-keyed rows only) → migrates;
- legacy dev sentinel only (auth0_id-keyed dev row, external NULL) →
  backfilled, content preserved;
- DUPLICATED dev sentinel (legacy row + new external-keyed row) → the
  migration must FAIL LOUDLY with instructions, never silently delete a row
  whose cascade would destroy a developer's local content;
- any other NULL external_auth_id row → fail loudly (impossible in
  production, verified pre-migration);
- an auth0-only TOMBSTONE row → fail loudly (the deleted_identities preflight
  guards its own irreversible column drop);
- a normal Clerk tombstone → survives the migration intact;
- sentinel backfill followed by a LATER preflight failure → the backfill is
  rolled back with everything else (proves the migration is one transaction —
  the property that makes "aborts touching nothing" true after partial
  progress, not just before it).

Each case gets its own database (CREATE DATABASE on a shared container),
built to the PRE-decommission revision, seeded, then upgraded via the real
alembic entry point (subprocess — same mechanism the deploy uses). Upgrades
target THIS revision explicitly, not head, so later migrations never smear
into these assertions (test_alembic_schema_compat.py owns head).

NOTE: app modules are imported inside tests/fixtures where needed — module-level
imports trigger Settings validation at collection time, before DATABASE_URL
exists (the rule test_auth_clerk.py documents).
"""
import os
import subprocess
import uuid
from pathlib import Path

import asyncpg
import pytest
from testcontainers.postgres import PostgresContainer

_REPO_ROOT = Path(__file__).parents[3]
_PRE_DECOMMISSION_REV = "64e3641d3441"
_DECOMMISSION_REV = "867f3d604c7c"
_SENTINEL = "dev|local-development-user"


@pytest.fixture(scope="module")
def migration_container() -> PostgresContainer:
    """One Postgres container shared by all cases (one database per case)."""
    with PostgresContainer("pgvector/pgvector:pg17", driver="asyncpg") as postgres:
        os.environ.setdefault("DATABASE_URL", postgres.get_connection_url())
        yield postgres


def _pg_url(container: PostgresContainer, dbname: str) -> str:
    """Plain postgres URL for direct asyncpg seeding/inspection."""
    host = container.get_container_host_ip()
    port = container.get_exposed_port(5432)
    return f"postgresql://{container.username}:{container.password}@{host}:{port}/{dbname}"


def _async_url(container: PostgresContainer, dbname: str) -> str:
    """Asyncpg URL for the alembic env."""
    host = container.get_container_host_ip()
    port = container.get_exposed_port(5432)
    return f"postgresql+asyncpg://{container.username}:{container.password}@{host}:{port}/{dbname}"


def _alembic(url: str, target: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    env["VITE_DEV_MODE"] = "true"
    env["PYTHONPATH"] = str(_REPO_ROOT / "backend" / "src")
    return subprocess.run(
        ["uv", "run", "alembic", "upgrade", target],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


@pytest.fixture
async def case_db(migration_container: PostgresContainer) -> tuple[str, str]:
    """A fresh database at the pre-decommission revision."""
    dbname = f"case_{uuid.uuid4().hex[:12]}"
    conn = await asyncpg.connect(_pg_url(migration_container, migration_container.dbname))
    try:
        await conn.execute(f'CREATE DATABASE "{dbname}"')
    finally:
        await conn.close()
    result = _alembic(_async_url(migration_container, dbname), _PRE_DECOMMISSION_REV)
    assert result.returncode == 0, f"setup upgrade failed: {result.stderr}"
    return dbname, _pg_url(migration_container, dbname)


async def _seed_user(pg_url: str, *, auth0_id: str | None, external_auth_id: str | None) -> str:
    user_id = str(uuid.uuid4())
    conn = await asyncpg.connect(pg_url)
    try:
        await conn.execute(
            "INSERT INTO users (id, auth0_id, external_auth_id, email) "
            "VALUES ($1, $2, $3, $4)",
            uuid.UUID(user_id), auth0_id, external_auth_id, f"{user_id[:8]}@test.local",
        )
    finally:
        await conn.close()
    return user_id


async def test__clean_database__migrates(
    migration_container: PostgresContainer, case_db: tuple[str, str],
) -> None:
    dbname, pg_url = case_db
    await _seed_user(pg_url, auth0_id=None, external_auth_id="user_clean")

    result = _alembic(_async_url(migration_container, dbname), _DECOMMISSION_REV)

    assert result.returncode == 0, result.stderr
    conn = await asyncpg.connect(pg_url)
    try:
        cols = await conn.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'auth0_id'",
        )
    finally:
        await conn.close()
    assert cols == []


async def test__legacy_dev_sentinel__backfilled_and_content_preserved(
    migration_container: PostgresContainer, case_db: tuple[str, str],
) -> None:
    dbname, pg_url = case_db
    user_id = await _seed_user(pg_url, auth0_id=_SENTINEL, external_auth_id=None)
    conn = await asyncpg.connect(pg_url)
    try:
        await conn.execute(
            "INSERT INTO bookmarks (id, user_id, url, title) VALUES ($1, $2, $3, $4)",
            uuid.uuid4(), uuid.UUID(user_id), "https://example.com/", "kept",
        )
    finally:
        await conn.close()

    result = _alembic(_async_url(migration_container, dbname), _DECOMMISSION_REV)

    assert result.returncode == 0, result.stderr
    conn = await asyncpg.connect(pg_url)
    try:
        row = await conn.fetchrow("SELECT id, external_auth_id FROM users")
        assert (row["id"], row["external_auth_id"]) == (uuid.UUID(user_id), _SENTINEL)
        bookmarks = await conn.fetch("SELECT title FROM bookmarks")
        assert [b["title"] for b in bookmarks] == ["kept"]
    finally:
        await conn.close()


async def test__duplicated_dev_sentinel__fails_loudly_deletes_nothing(
    migration_container: PostgresContainer, case_db: tuple[str, str],
) -> None:
    dbname, pg_url = case_db
    await _seed_user(pg_url, auth0_id=_SENTINEL, external_auth_id=None)
    await _seed_user(pg_url, auth0_id=None, external_auth_id=_SENTINEL)

    result = _alembic(_async_url(migration_container, dbname), _DECOMMISSION_REV)

    assert result.returncode != 0
    assert "Duplicated dev sentinel" in result.stderr
    conn = await asyncpg.connect(pg_url)
    try:
        count = await conn.fetchval("SELECT count(*) FROM users")
        cols = await conn.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'auth0_id'",
        )
    finally:
        await conn.close()
    assert count == 2  # nothing deleted
    assert cols != []  # nothing dropped — the migration aborted whole


async def test__stray_null_external_auth_id__fails_loudly(
    migration_container: PostgresContainer, case_db: tuple[str, str],
) -> None:
    dbname, pg_url = case_db
    await _seed_user(pg_url, auth0_id="auth0|not-the-sentinel", external_auth_id=None)

    result = _alembic(_async_url(migration_container, dbname), _DECOMMISSION_REV)

    assert result.returncode != 0
    assert "external_auth_id IS NULL" in result.stderr


async def _seed_tombstone(pg_url: str, *, auth0_id: str | None, external_auth_id: str | None) -> None:
    conn = await asyncpg.connect(pg_url)
    try:
        await conn.execute(
            "INSERT INTO deleted_identities (id, auth0_id, external_auth_id) "
            "VALUES ($1, $2, $3)",
            uuid.uuid4(), auth0_id, external_auth_id,
        )
    finally:
        await conn.close()


async def test__auth0_only_tombstone__fails_loudly(
    migration_container: PostgresContainer, case_db: tuple[str, str],
) -> None:
    """The deleted_identities preflight guards its own irreversible drop."""
    dbname, pg_url = case_db
    await _seed_tombstone(pg_url, auth0_id="legacy|window-era-tombstone", external_auth_id=None)

    result = _alembic(_async_url(migration_container, dbname), _DECOMMISSION_REV)

    assert result.returncode != 0
    assert "deleted_identities" in result.stderr
    assert "external_auth_id IS NULL" in result.stderr
    conn = await asyncpg.connect(pg_url)
    try:
        cols = await conn.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'deleted_identities' AND column_name = 'auth0_id'",
        )
    finally:
        await conn.close()
    assert cols != []  # aborted before any drop


async def test__clerk_tombstone__survives_migration(
    migration_container: PostgresContainer, case_db: tuple[str, str],
) -> None:
    """A normal Clerk-keyed tombstone passes the preflight and is preserved."""
    dbname, pg_url = case_db
    await _seed_tombstone(pg_url, auth0_id=None, external_auth_id="user_tombstoned_ok")

    result = _alembic(_async_url(migration_container, dbname), _DECOMMISSION_REV)

    assert result.returncode == 0, result.stderr
    conn = await asyncpg.connect(pg_url)
    try:
        rows = await conn.fetch("SELECT external_auth_id FROM deleted_identities")
    finally:
        await conn.close()
    assert [r["external_auth_id"] for r in rows] == ["user_tombstoned_ok"]


async def test__failure_after_sentinel_backfill__rolls_the_backfill_back(
    migration_container: PostgresContainer, case_db: tuple[str, str],
) -> None:
    """
    The one-transaction proof: the sentinel backfill UPDATE executes before
    the generic NULL preflight, so a legacy sentinel plus an unrelated stray
    NULL row means the migration mutates a row and THEN aborts. The abort
    must undo the mutation — this is the test that catches anyone splitting
    the migration across transactions or adding an early commit later.
    """
    dbname, pg_url = case_db
    sentinel_id = await _seed_user(pg_url, auth0_id=_SENTINEL, external_auth_id=None)
    await _seed_user(pg_url, auth0_id="legacy|stray-null", external_auth_id=None)

    result = _alembic(_async_url(migration_container, dbname), _DECOMMISSION_REV)

    assert result.returncode != 0
    assert "external_auth_id IS NULL" in result.stderr
    conn = await asyncpg.connect(pg_url)
    try:
        sentinel_external = await conn.fetchval(
            "SELECT external_auth_id FROM users WHERE id = $1", uuid.UUID(sentinel_id),
        )
        cols = await conn.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'auth0_id'",
        )
    finally:
        await conn.close()
    assert sentinel_external is None  # the backfill UPDATE was rolled back
    assert cols != []  # and no DDL survived the abort
