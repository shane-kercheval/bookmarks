"""drop auth0_id and finalize clerk-only identity

The M6b decommission migration (run sheet step Ii) — the schema half of the
staged contract: the previous deploy removed every code reference to these
columns, so no running instance maps them when this drops them.

Preconditions (all verified on production before this ships; enforced here so
the migration fails loudly instead of half-applying anywhere else):
- Every `users` row and every `deleted_identities` row carries a non-null
  `external_auth_id`.
- The one tolerated exception is a pre-M6b LOCAL dev database whose dev
  sentinel row is still keyed by `auth0_id` — handled explicitly below
  (backfilled when unambiguous; the migration aborts with instructions when a
  duplicate sentinel exists, rather than silently deleting a row whose cascade
  would destroy local content).

Downgrade restores the schema shape only — the dropped auth0_id VALUES are
not recoverable (by decommission design; the pre-migration DB snapshot is the
durable record).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '867f3d604c7c'
down_revision: Union[str, Sequence[str], None] = '64e3641d3441'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEV_SENTINEL = 'dev|local-development-user'


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()

    # --- Dev-sentinel handling (local databases only; production has no dev
    # rows — the H1 preflight proved zero NULL external_auth_id rows).
    legacy_sentinel = conn.execute(sa.text(
        "SELECT id FROM users WHERE auth0_id = :s AND external_auth_id IS NULL",
    ), {"s": DEV_SENTINEL}).scalar_one_or_none()
    if legacy_sentinel is not None:
        duplicate = conn.execute(sa.text(
            "SELECT id FROM users WHERE external_auth_id = :s",
        ), {"s": DEV_SENTINEL}).scalar_one_or_none()
        if duplicate is not None:
            raise RuntimeError(
                "Duplicated dev sentinel: this database has BOTH a legacy dev "
                f"user (auth0_id='{DEV_SENTINEL}', id={legacy_sentinel}) and a "
                f"new dev user (external_auth_id='{DEV_SENTINEL}', id={duplicate}). "
                "Refusing to guess which to keep — deleting either cascades its "
                "content. Either reset the local database (make db-reset / "
                "recreate the stack) or manually merge: move any content you "
                "want to keep onto one row, delete the other, then rerun "
                "migrations.",
            )
        conn.execute(sa.text(
            "UPDATE users SET external_auth_id = :s "
            "WHERE id = :id AND external_auth_id IS NULL",
        ), {"s": DEV_SENTINEL, "id": legacy_sentinel})

    # --- Preflights: fail loudly on any row the NOT NULL below would reject.
    for table in ("users", "deleted_identities"):
        null_count = conn.execute(sa.text(
            f"SELECT count(*) FROM {table} WHERE external_auth_id IS NULL",  # noqa: S608
        )).scalar_one()
        if null_count:
            raise RuntimeError(
                f"{table} has {null_count} row(s) with external_auth_id IS NULL. "
                "Production was verified clean pre-migration, so this is a "
                "local/dev database in an unexpected state — investigate or "
                "reset it; do not weaken this check.",
            )

    # --- users: drop the transitional identity machinery, finalize Clerk-only.
    op.drop_constraint('ck_user_has_identity', 'users', type_='check')
    op.drop_index(op.f('ix_users_auth0_id'), table_name='users')
    op.drop_column('users', 'auth0_id')
    op.alter_column('users', 'external_auth_id', nullable=False)

    # --- deleted_identities: same treatment (tombstones are Clerk-keyed only).
    op.drop_constraint(
        'ck_deleted_identity_has_identity', 'deleted_identities', type_='check',
    )
    op.drop_index(
        op.f('ix_deleted_identities_auth0_id'), table_name='deleted_identities',
    )
    op.drop_column('deleted_identities', 'auth0_id')
    op.alter_column('deleted_identities', 'external_auth_id', nullable=False)


def downgrade() -> None:
    """Downgrade schema (shape only — dropped auth0_id values are gone)."""
    op.alter_column('deleted_identities', 'external_auth_id', nullable=True)
    op.add_column('deleted_identities', sa.Column(
        'auth0_id', sa.VARCHAR(length=255), autoincrement=False, nullable=True,
        comment="Auth0 'sub' of the deleted user - blocks the Auth0/iOS JIT path",
    ))
    op.create_index(
        op.f('ix_deleted_identities_auth0_id'), 'deleted_identities',
        ['auth0_id'], unique=True,
    )
    op.create_check_constraint(
        'ck_deleted_identity_has_identity', 'deleted_identities',
        '(auth0_id IS NOT NULL) OR (external_auth_id IS NOT NULL)',
    )

    op.alter_column('users', 'external_auth_id', nullable=True)
    op.add_column('users', sa.Column(
        'auth0_id', sa.VARCHAR(length=255), autoincrement=False, nullable=True,
        comment="Auth0 'sub' claim - NULL for users created via Clerk (dropped in M6b)",
    ))
    op.create_index(op.f('ix_users_auth0_id'), 'users', ['auth0_id'], unique=True)
    op.create_check_constraint(
        'ck_user_has_identity', 'users',
        '(auth0_id IS NOT NULL) OR (external_auth_id IS NOT NULL)',
    )
