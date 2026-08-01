# Content Versioning System Specification

## Overview

The content versioning system tracks all changes to bookmarks, notes, and prompts. It enables users to view history, see what changed, understand who/what initiated changes, and restore previous versions.

### Design Goals

1. **Complete audit trail** — Every create, update, delete, undelete, restore, archive, and unarchive is recorded
2. **Efficient storage** — Use diffs instead of full snapshots where possible
3. **Source attribution** — Track whether changes came from web UI, API, or MCP servers
4. **Tier-based retention** — Different user tiers get different history retention limits
5. **Simple cleanup** — Pruning old history should be straightforward without orphaning data

---

## Core Concepts

### Reverse Diffs

The system uses **reverse diffs** — each diff record stores how to transform the current version's content into the previous version's content (going backwards in time).

**Why reverse diffs:**
- Cleanup is trivial: delete old records freely (when deleting from the oldest end of the chain), reconstruction always anchors on current content
- No need to preserve old snapshots for correctness
- Standard pattern used by backup systems

**How reconstruction works:**
1. Start with the entity's current content (from the entity table, e.g., `Note.content`)
2. Get all history records from the latest version down to the target version
3. Apply each reverse diff sequentially to walk backwards through time
4. The result is the content at the target version

### Content Storage and Change Types

The change type for a history record is derived from its content columns and action, not a separate field:

| Scenario | `content_snapshot` | `content_diff` | How to Identify |
|----------|-------------------|----------------|-----------------|
| CREATE | Full content | None | `action = 'create'` |
| Content change (normal) | None | Diff to previous | `content_diff IS NOT NULL` |
| Content change (periodic) | Full content | Diff to previous | Every Nth version (default: 10) |
| Metadata only (normal) | None | None | Version present, `content_diff IS NULL`, action is not `create` |
| Metadata only (periodic) | Full content | None | Every Nth version — guarantees bounded reconstruction |
| Audit | None | None | `version IS NULL` |

**Note:** Metadata is stored as a full snapshot in content action records. Audit actions (DELETE, UNDELETE, ARCHIVE, UNARCHIVE) store only identifying metadata (title/name, URL for bookmarks).

**Why dual storage for periodic snapshots?**

With reverse diffs, each record must provide a way to get to the previous version. If a snapshot only stored full content (no diff), the reconstruction chain would break at that point—there would be no way to traverse backwards through the snapshot.

By storing both `content_snapshot` (for starting reconstruction) and `content_diff` (for chain continuity), periodic content-change snapshots serve as efficient starting points without breaking the chain.

**Metadata-only snapshots at modulo-10 versions** store `content_snapshot` to guarantee reconstruction never traverses more than 10 versions to find an anchor point.

**Storage impact:** Minimal (~5% increase). For every 10 versions with ~10KB content, dual storage adds only ~1KB (one extra diff per snapshot interval).

### Snapshots

Snapshots serve as:
1. **Error recovery points** — If a diff is corrupted, snapshots provide known-good content
2. **Interval markers** — Force full content capture periodically (default: every 10 versions)

Snapshots are **not required for reconstruction correctness** — the entity's current content is always the anchor. However, they provide resilience against diff corruption.

---

## Data Model

### History Record Fields

Each history record contains:

| Field | Description |
|-------|-------------|
| `id` | Unique identifier (UUIDv7) |
| `user_id` | Owner of the content |
| `entity_type` | "bookmark", "note", or "prompt" |
| `entity_id` | ID of the bookmark/note/prompt |
| `action` | What happened (see Actions below) |
| `version` | Sequential version number per entity (1, 2, 3, ...) or NULL for audit actions |
| `content_snapshot` | Full content text (set for CREATE, periodic snapshots, and modulo-10 metadata-only changes) |
| `content_diff` | Diff-match-patch delta string to previous version (set when content changed; None for CREATE, metadata-only, audit) |
| `metadata_snapshot` | JSON object of non-content fields at this version |
| `source` | Request origin (see Source Tracking) |
| `auth_type` | Authentication method used |
| `token_prefix` | First 15 chars of PAT if used (for audit trail) |
| `created_at` | When this version was created |

### Metadata Snapshot Contents

The `metadata_snapshot` captures non-content fields at each version:

**All entity types:**
- `title`
- `description`
- `tags` (list of tag names)

**Bookmarks additionally:**
- `url`

**Prompts additionally:**
- `name`
- `arguments`

---

## Actions Tracked

| Action | Trigger | Has Version? | Content Stored |
|--------|---------|--------------|----------------|
| `CREATE` | New entity created | Yes | Full content (`content_snapshot`) |
| `UPDATE` | Entity modified | Yes | Diff or snapshot depending on interval and whether content changed |
| `RESTORE` | Restored to previous version | Yes | Same as UPDATE |
| `DELETE` | Soft delete | No (NULL) | None — only identifying metadata |
| `UNDELETE` | Soft delete reversed | No (NULL) | None — only identifying metadata |
| `ARCHIVE` | Entity archived | No (NULL) | None — only identifying metadata |
| `UNARCHIVE` | Archive reversed | No (NULL) | None — only identifying metadata |

### Audit Actions (DELETE, UNDELETE, ARCHIVE, UNARCHIVE)

These are **lifecycle state transitions** — they change the entity's status but not its content. They have **no version number** (NULL), no content snapshot, and no content diff.

The metadata snapshot for audit actions contains only identifying fields (title/name, URL for bookmarks) rather than a full metadata snapshot, since the entity's content and metadata are unchanged.

**Why no content storage?** Soft delete only sets `deleted_at`; archive only sets `archived_at`. The entity's content remains in the entity table, unchanged. Storing content would be redundant.

**Why no version number?** These are not content versions — they're state transitions. Excluding them from the version sequence keeps version numbers meaningful (each version represents a distinct content state).

**Hard deletes**: When an entity is permanently removed, all associated history records are cascade-deleted at the application level. No history survives a hard delete — this supports GDPR "right to erasure" requirements.

### No-Op Updates

If an update request results in no actual changes (identical content and metadata), **no history record is created**. This prevents cluttering history with meaningless entries.

---

## Source Tracking

Every history record captures where the change originated.

### Request Source

Determined by the `X-Request-Source` header. Any value is accepted, trimmed, lowercased, and truncated to a maximum length; a missing or blank header defaults to `unknown`. See [`architecture.md` § Request source](architecture.md#request-source) for the canonical description and the current first-party client values (`web`, `cli`, `chrome-extension`, `mcp-content`, `mcp-prompt`, `ios`).

### Authentication Type

| Auth Type | Description |
|-----------|-------------|
| `SESSION` | IdP session/OAuth JWT (provider-neutral; rows from before the rename persisted the historical value `auth0` and are never backfilled) |
| `PAT` | Personal Access Token |
| `DEV` | Development mode |

### Token Prefix

For PAT authentication, the first 15 characters of the token are stored (e.g., `bm_a3f8...`). This allows auditing which token made changes without exposing the full token.

### MCP Server Restrictions

MCP servers explicitly block delete operations. Attempts to delete via MCP return a descriptive error: "Delete operations are only available via the web UI for safety."

---

## Version Numbering

- Versions are sequential integers starting at 1 for each entity
- Version numbers are monotonic — they never reset, even after pruning
- **Audit actions (DELETE, UNDELETE, ARCHIVE, UNARCHIVE) have NULL versions** — they are not content versions
- Concurrent writes to the same entity use a retry mechanism with database savepoints to allocate unique versions
- The unique constraint on `(user_id, entity_type, entity_id, version)` prevents duplicates (NULL versions are exempt from this constraint)

---

## Reconstruction Algorithm

To reconstruct content at a specific version:

1. **Validate target** — Return not found if version doesn't exist or exceeds latest
2. **Get current content** — Fetch from entity table (including soft-deleted entities) as fallback anchor
3. **Get history chain** — Fetch all records from latest version down to target version (ordered by version descending). Records with NULL versions (audit actions) are naturally excluded since they have no version number to match.
4. **Find nearest snapshot** — Scan fetched records for the nearest record with `content_snapshot IS NOT NULL` (lowest version number in the set). This includes periodic content-change snapshots and modulo-10 metadata-only snapshots. This avoids applying unnecessary diffs.
5. **Choose starting point:**
   - If snapshot found: start from that record's `content_snapshot`
   - If no snapshot found: start from entity's current content
6. **Apply reverse diffs** — Starting from the chosen anchor, iterate through records from the snapshot (or start) down to target:
   - If `content_diff` is present: apply the delta to get the previous version's content
   - If `content_diff` is None (CREATE, metadata-only, audit): skip — content unchanged at this version
7. **Return result** — Content at target version, plus any warnings

### Why Find the Nearest Snapshot?

Records are fetched from latest to target (e.g., v50 down to v25). If a snapshot exists at v30, starting from entity content would require applying 20 diffs (v50→v49→...→v30→...→v25). By finding the nearest snapshot first, we start from v30's `content_snapshot` and apply only 5 diffs (including v30's own `content_diff`). This optimization avoids wasted computation, especially as snapshot intervals increase.

**Note:** Metadata is stored as a full snapshot in every record, so only content reconstruction uses this algorithm. The target version's metadata is retrieved directly from its history record.

### Partial Patch Failures

If a diff fails to apply cleanly (some hunks fail), the system:
- Continues with the partial result
- Logs a warning server-side
- Returns the content with a `warnings` array in the response

**For viewing history:** Partial content with a warning is better than blocking access entirely.

**For restoring:** The warnings are included in the response so the frontend can inform the user before or after the restoration.

### Reconstruction of Deleted Entities

Soft-deleted entities retain their content in the entity table (only `deleted_at` is set). Reconstruction works normally — anchor on `entity.content`, apply diffs.

Hard-deleted entities have no content to anchor on and no history (cascade-deleted). Reconstruction returns not found.

---

## Retention and Cleanup

### Tier-Based Limits

Each user tier defines:
- `history_retention_days` — How long to keep history records
- `max_history_per_entity` — Maximum versions to retain per entity

### Count-Based Pruning (Inline)

Enforced at write time using modulo-based checking:

1. After recording a history entry, check if `version % 10 == 0`
2. If so, count history records for this entity (excluding audit events)
3. If count exceeds `max_history_per_entity`, delete oldest records to reach the limit

**Behavior:**
- Only the oldest records are deleted
- With reverse diffs, no special snapshot preservation is needed
- Check runs every 10 writes to avoid per-write overhead
- **Audit events (NULL version) are not subject to count-based pruning** — they have no version number, so the modulo check never triggers. They are only cleaned up by time-based pruning.

### Time-Based Pruning (Scheduled)

A nightly cron job:
1. Groups users by tier
2. Deletes history records older than each tier's `history_retention_days`
3. Also permanently deletes soft-deleted entities older than 30 days (with their history)

**Preservation rule:** The most recent versioned history record per entity is always retained, regardless of age. Audit records (DELETE/UNDELETE/ARCHIVE/UNARCHIVE) are not exempted. This guarantees that diff and restore remain functional after long idle periods.

### Hard Delete Cascade

When an entity is permanently deleted:
1. All history records for that entity are deleted first (application-level cascade)
2. Then the entity is deleted
3. No history record is created for the hard delete itself

This supports GDPR "right to erasure" — permanent deletion is truly permanent.

---

## API Operations

### View All User History

Returns paginated history across all user's content, optionally filtered by entity type.

### View Entity History

Returns paginated history for a specific entity. Returns empty list (not 404) if entity doesn't exist or was hard-deleted.

### View Content at Version

Reconstructs and returns the content at a specific version. Returns the content and any reconstruction warnings.

### Restore to Version

Restores an entity to a previous version's content and metadata:

1. Reconstruct content at target version
2. Update entity with reconstructed content and metadata
3. A new RESTORE history record is created (distinct from UPDATE)
4. Response includes any reconstruction warnings

**Restrictions:**
- Soft-deleted entities must be undeleted first — restore returns 404 for deleted entities
- Audit versions (DELETE, UNDELETE, ARCHIVE, UNARCHIVE) cannot be restored to — they are state transitions, not content versions
- Cannot restore to the current version (no-op)

**Conflict handling:**
- If restored URL conflicts with another bookmark: 409 error
- If restored prompt name conflicts: 409 error

**Tag handling:**
- Tags are restored by name
- Missing tags are created automatically
- This matches existing tag behavior throughout the application

---

## Edge Cases and Behaviors

### Schema Evolution

When restoring to an old version:
- **Removed fields**: If the old metadata contains fields that no longer exist in the current schema, they are ignored
- **New fields**: If the old metadata is missing fields that were added after that version was created, the entity retains its current values for those fields

### Metadata-Only Changes

When only metadata changes (tags, title, description) but content is identical:
- `content_diff` is None (no content change to store)
- At modulo-10 versions, `content_snapshot` is set to guarantee bounded reconstruction distance
- Reconstruction skips these records (content same as next newer version)

### Archived Entity Restore

Restoring an archived entity:
- Content and metadata are restored to the target version
- Archive status is preserved (entity remains archived)

### Concurrent Edits

The system uses last-write-wins for entity content. If two users edit simultaneously:
- User A saves → creates version N
- User B saves → creates version N+1
- User A's changes are preserved in version N's history
- No data is lost, but User A's changes are not in the current content

Optimistic concurrency control (ETags/If-Match) is a separate feature that may be added independently.

### Inactive Entities and Time-Based Cleanup

If an entity hasn't been edited for longer than `history_retention_days`:
- All history records **except the most recent versioned record** may be deleted by time-based cleanup. The retained record serves as the anchor for diff and restore on the next edit.
- Audit records (DELETE/UNDELETE/ARCHIVE/UNARCHIVE) are not exempted and remain fully subject to time-based pruning.
- The entity itself remains (with current content)

---
