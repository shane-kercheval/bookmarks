"""Alembic environment configuration for async SQLAlchemy."""
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from core.config import get_settings
from models.ai_usage import AiUsage  # noqa: F401 - imported for Alembic autogenerate
from models.base import Base
from models.bookmark import Bookmark  # noqa: F401 - imported for Alembic autogenerate
from models.content_filter import ContentFilter  # noqa: F401 - imported for Alembic autogenerate
from models.content_relationship import ContentRelationship  # noqa: F401 - imported for Alembic autogenerate
from models.deleted_identity import DeletedIdentity  # noqa: F401 - imported for Alembic autogenerate
from models.filter_group import FilterGroup  # noqa: F401 - imported for Alembic autogenerate
from models.note import Note  # noqa: F401 - imported for Alembic autogenerate
from models.prompt import Prompt  # noqa: F401 - imported for Alembic autogenerate
from models.user import User  # noqa: F401 - imported for Alembic autogenerate
from models.user_settings import UserSettings  # noqa: F401 - imported for Alembic autogenerate

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the database URL from our settings
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata


# Indexes that exist in the database but are deliberately absent from the ORM.
#
# The three GIN indexes on `search_vector` columns are created by migration
# c07d5e217ca3. The models do not declare them (database triggers keep the
# `search_vector` *columns* current; PostgreSQL maintains the *indexes*), so
# every `--autogenerate` run reports them as removed and proposes dropping
# them. Applying that would not break search — results stay correct — but it
# would remove GIN acceleration and force sequential scans across bookmarks,
# notes, and prompts, with nothing failing loudly enough to trace back to a
# migration weeks later. This has now been caught by hand three times.
#
# Matched by exact name rather than by "any index on a search_vector column",
# and only when `compare_to is None` (i.e. reflected-from-database with no ORM
# counterpart). A future change that genuinely models or alters one of these
# indexes therefore still shows up in autogenerate output.
_UNMODELLED_INDEXES = frozenset({
    "ix_bookmarks_search_vector",
    "ix_notes_search_vector",
    "ix_prompts_search_vector",
})


def include_object(
    obj: object,
    name: str | None,
    type_: str,
    reflected: bool,  # noqa: FBT001 - Alembic's positional callback signature
    compare_to: object | None,
) -> bool:
    """Filter reflected-only objects that the ORM deliberately does not model."""
    if type_ == "index" and reflected and compare_to is None:
        return name not in _UNMODELLED_INDEXES
    return True


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine, though an
    Engine is acceptable here as well.  By skipping the Engine creation we don't
    even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with the given connection."""
    # include_object is wired into BOTH configure sites. Autogenerate uses the
    # online path, but applying it to only one is the obvious half-fix.
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
