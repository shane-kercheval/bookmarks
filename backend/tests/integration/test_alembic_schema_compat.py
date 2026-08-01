"""
Schema compatibility: the identity write surface against the ALEMBIC schema.

The main test suite builds its database from ORM metadata
(Base.metadata.create_all); production's schema comes from the Alembic chain.
This module keeps the two honest against each other for the identity tables
(the gap a review round caught during the M6b staged decommission: the suite
was only ever testing the metadata-built schema). It builds a dedicated
database from `alembic upgrade head` (subprocess, so the app's cached Settings
are untouched) and exercises JIT creation, email sync, and
deletion + tombstoning through the real code paths.

Updated with the M6b decommission migration (867f3d604c7c): the transitional
auth0_id columns and identity CHECK constraints are now asserted ABSENT at
head, and external_auth_id NOT NULL in both tables — the finalized
Clerk-only schema.
"""
import os
import subprocess
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

# NOTE: core.auth / services.user_service are imported inside the tests —
# importing them here triggers Settings validation at collection time, before
# the fixtures set DATABASE_URL (the same rule test_auth_clerk.py documents).

_REPO_ROOT = Path(__file__).parents[3]


@pytest.fixture(scope="module")
def alembic_head_url() -> str:
    """A dedicated Postgres with the schema built by `alembic upgrade head`."""
    with PostgresContainer("pgvector/pgvector:pg17", driver="asyncpg") as postgres:
        url = postgres.get_connection_url()
        # The in-test app imports instantiate Settings (module-level engine in
        # db.session); in a standalone run nothing else has set DATABASE_URL
        # yet. setdefault keeps the full-suite value when it exists.
        os.environ.setdefault("DATABASE_URL", url)
        env = os.environ.copy()
        env["DATABASE_URL"] = url
        env["VITE_DEV_MODE"] = "true"  # Settings: local container DB passes the guard
        env["PYTHONPATH"] = str(_REPO_ROOT / "backend" / "src")
        result = subprocess.run(
            ["uv", "run", "alembic", "upgrade", "head"],
            cwd=_REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        assert result.returncode == 0, (
            f"alembic upgrade head failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        yield url


@pytest.fixture
async def head_session(alembic_head_url: str) -> AsyncGenerator[AsyncSession]:
    """Session against the Alembic-head database."""
    engine = create_async_engine(alembic_head_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def test__alembic_head__is_the_finalized_clerk_only_schema(
    head_session: AsyncSession,
) -> None:
    """
    The decommission migration completed the contract: no auth0_id columns,
    no transitional CHECKs, and external_auth_id NOT NULL in both tables.
    """
    cols = (await head_session.execute(text(
        """
        SELECT table_name FROM information_schema.columns
        WHERE column_name = 'auth0_id' AND table_name IN ('users', 'deleted_identities')
        """,
    ))).scalars().all()
    assert cols == []

    checks = (await head_session.execute(text(
        """
        SELECT conname FROM pg_constraint
        WHERE conname IN ('ck_user_has_identity', 'ck_deleted_identity_has_identity')
        """,
    ))).scalars().all()
    assert checks == []

    nullable = (await head_session.execute(text(
        """
        SELECT table_name, is_nullable FROM information_schema.columns
        WHERE column_name = 'external_auth_id'
          AND table_name IN ('users', 'deleted_identities')
        ORDER BY table_name
        """,
    ))).all()
    assert [(r.table_name, r.is_nullable) for r in nullable] == [
        ("deleted_identities", "NO"), ("users", "NO"),
    ]


async def test__clerk_only_writes_succeed_against_alembic_schema(
    head_session: AsyncSession,
) -> None:
    """
    JIT creation, email sync, and deletion + tombstone — the full identity
    write surface — exercised against the Alembic-built schema (not the
    metadata-built one the rest of the suite uses).
    """
    from core.auth import get_or_create_user  # noqa: PLC0415
    from services.user_service import delete_user_by_external_auth_id  # noqa: PLC0415

    sub = "user_premigration_compat"

    # JIT create (first-ever request shape)
    user = await get_or_create_user(
        head_session, external_auth_id=sub, email="compat@test.com",
    )
    await head_session.commit()
    assert user.external_auth_id == sub

    # Email sync on an existing row (the consent/IdP-update shape)
    user = await get_or_create_user(
        head_session, external_auth_id=sub, email="compat-updated@test.com",
    )
    await head_session.commit()
    assert user.email == "compat-updated@test.com"

    # Deletion: cascade + Clerk-keyed tombstone against the old CHECK
    result = await delete_user_by_external_auth_id(head_session, sub)
    await head_session.commit()
    assert result.deleted is True

    row = (await head_session.execute(text(
        "SELECT external_auth_id FROM deleted_identities "
        "WHERE external_auth_id = :sub",
    ), {"sub": sub})).one()
    assert row.external_auth_id == sub

    # And the user row is gone.
    remaining = (await head_session.execute(text(
        "SELECT count(*) FROM users WHERE external_auth_id = :sub",
    ), {"sub": sub})).scalar_one()
    assert remaining == 0
