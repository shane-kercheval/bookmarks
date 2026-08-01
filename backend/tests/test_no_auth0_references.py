"""
Tripwire: no Auth0 reference re-enters the tree outside the explicit allowlist.

The M6b decommission's grep gate, made mechanical (the same discipline as the
auth-dependency invariant guard and the Alembic-compat tests: "checked once"
becomes "checked every run"). Every git-tracked text file is scanned for
case-insensitive `auth0`; a hit is legal only if its file is in the allowlist
below or under a wholesale-excluded historical record.

Adding a new Auth0 reference legitimately requires adding an allowlist entry
with a rationale — that review moment is the point of this test. Entries with
an `expiry` are deleted when their named event executes (the run sheet's J6
step deletes the README_DEPLOY entry).
"""
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).parents[2]

# Historical records of the migration itself — their Auth0 mentions are the
# content, wholesale-excluded rather than enumerated.
_HISTORICAL_PREFIXES = (
    "docs/implementation_plans/",
    "docs/security/",
    "backend/src/db/migrations/versions/",
)
_HISTORICAL_FILES = {
    "docs/auth0-clerk-ledger.md",
    "docs/ios-clerk-migration-guide.md",
}

# path -> (rationale, expiry-or-None). Keep entries narrow and justified;
# an entry whose file no longer contains a hit should be removed.
_ALLOWLIST: dict[str, tuple[str, str | None]] = {
    "backend/tests/test_no_auth0_references.py": ("this gate", None),
    # Reintroduction guards — they must name what they ban.
    "backend/tests/core/test_auth_clerk.py": (
        "old-issuer rejection test (TEST_AUTH0_ISSUER)", None),
    "frontend/eslint.config.js": ("@auth0/auth0-react import ban", None),
    # Migration state/schema tests exercise the dropped columns by name.
    "backend/tests/integration/test_decommission_migration.py": (
        "decommission-migration state tests", None),
    "backend/tests/integration/test_alembic_schema_compat.py": (
        "asserts the auth0_id columns are ABSENT at head", None),
    # Persisted historical audit value: old content_history rows carry
    # auth_type='auth0' forever (see core/request_context.py).
    "frontend/src/components/HistorySidebar.test.tsx": (
        "historical auth_type value", None),
    "frontend/src/pages/settings/SettingsVersionHistory.test.tsx": (
        "historical auth_type value", None),
    # Historical/explanatory comments naming the migration they explain.
    "backend/src/core/auth.py": ("decommission provenance comments", None),
    "backend/src/core/auth_cache.py": ("cache-version history comments", None),
    "backend/src/core/policy_versions.py": ("2026-07-31 bump rationale", None),
    "backend/src/core/request_context.py": ("historical auth_type note", None),
    "backend/src/models/user.py": ("dropped-column provenance", None),
    "backend/src/models/deleted_identity.py": ("dropped-column provenance", None),
    "backend/src/services/user_service.py": ("retired lock-namespace note", None),
    "backend/src/tasks/cleanup.py": ("tombstone-retention rationale", None),
    "cli/internal/auth/pkce_flow.go": ("replaced-device-flow note", None),
    "frontend/src/pages/settings/SettingsAccount.tsx": (
        "previous-provider gap note", None),
    "clerk/README.md": ("migration framing", None),
    "docs/architecture.md": ("decommission history in current-state doc", None),
    "docs/content-versioning.md": ("historical auth_type value", None),
    "docs/custom-domain-setup.md": ("Auth0-era setup record (headered)", None),
    # Operational references to the not-yet-deleted tenants.
    "README_DEPLOY.md": ("tenant references until deletion", "J6"),
}

_TEXT_SUFFIXES = {
    ".py", ".go", ".ts", ".tsx", ".js", ".mjs", ".json", ".yaml", ".yml",
    ".toml", ".md", ".txt", ".css", ".html", ".sh", ".sql", ".example",
    ".template", ".cfg", ".ini", ".env",
}


def _is_scannable(path: str) -> bool:
    if any(path.startswith(p) for p in _HISTORICAL_PREFIXES):
        return False
    if path in _HISTORICAL_FILES:
        return False
    p = Path(path)
    return p.suffix.lower() in _TEXT_SUFFIXES or p.name in {
        "Makefile", ".env.example", ".gitignore", "alembic.ini",
    }


def test__no_auth0_references_outside_allowlist() -> None:
    """Case-insensitive scan of every tracked text file."""
    tracked = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()

    violations: list[str] = []
    hit_files: set[str] = set()
    for rel in tracked:
        if not _is_scannable(rel):
            continue
        try:
            content = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        if "auth0" not in content.lower():
            continue
        hit_files.add(rel)
        if rel not in _ALLOWLIST:
            for i, line in enumerate(content.splitlines(), 1):
                if "auth0" in line.lower():
                    violations.append(f"{rel}:{i}: {line.strip()[:100]}")

    assert not violations, (
        "Auth0 references outside the allowlist (add an allowlist entry with "
        "a rationale if deliberate):\n" + "\n".join(violations)
    )

    stale_entries = set(_ALLOWLIST) - hit_files - {"backend/tests/test_no_auth0_references.py"}
    assert not stale_entries, (
        f"Allowlist entries whose files no longer contain hits — remove them: {sorted(stale_entries)}"
    )
