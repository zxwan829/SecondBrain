# Core source reference coverage

This matrix records what the local Core readers can verify from configured,
bounded, read-only stores. `verified` is reserved for an exact authoritative ID
and a version that Core recomputes from the same source bytes.

| Reference | Stable ID authority | Version authority | Permission check | Read bound | Outcome |
|---|---|---|---|---|---|
| Brief `project` | Exact document ID from `ProjectsSourceReadStore` | SHA-256 of exact JSON bytes read from configured project root | `daily_brief.read` and `projects.read` | 200 entries, 64 KiB/file, 2 MiB total | Exact unique match verifies; mismatch is stale; incomplete snapshot is unavailable |
| Brief `task` | TaskStore-issued 32-character UUID hex ID | SHA-256 over the documented canonical fields `id,title,due_date,status,created_at,updated_at,source`; excludes session, command, idempotency, and history | `daily_brief.read` and `task.read` | TaskStore projection capped at 2 MiB/request | Only explicit Web App Tasks with valid fields verify; missing, stale, malformed, or unavailable fails closed |
| Brief `journal` | JournalStore row ID plus exact `YYYY-MM-DD` file locator (`date:row-id`) | SHA-256 of the persisted JSONL row bytes | `daily_brief.read` and `journal.read` | 1 MiB/day, 5,000 rows/day, 2 MiB/request | Exact date-bounded unique row verifies; date or array position alone is never an ID |
| Internal Daily Brief Journal source options | Same JournalStore `date:row-id`; only `web_app_explicit_intent` and `inbox_approved_proposal` rows | Revalidated by `SourceReferenceAuthority._verify_journal` against the exact row SHA-256 | Trusted same-origin `Origin`, App session, `daily_brief.read`, and `journal.read` | One exact day; 1 MiB/day, 5,000 rows/day, 2 MiB aggregate read budget; response limit 1-50 (default 20) | Metadata-only `kind,id,date,version`; any source snapshot drift or read-budget/security failure returns `unavailable` with no items |
| Project `linked_notes` | Canonical UUID resolved only by the NotesStore Draft ID mapping | NotesStore ETag (SHA-256 of exact Markdown bytes) | `projects.read` and `notes.read` | 1 MiB/note, 2 MiB/request, 100 references/request | Explicit Draft link verifies; other collections, path/title guesses, malformed IDs, stale versions, or unavailable reads fail closed |
| Project `recent_activity` | No stable event ID in the current Project schema | No event version | `projects.read` | No join/read attempted | Unsupported; timestamps are never joined to Task or Journal records |
| Brief `note`, `capture`, `review`, Chat, external news | Outside D087 Brief source allowlist | Not applicable | Not read | Not read | Unsupported; the whole Brief summary/items are withheld |

Project `linked_notes` is validated only when explicitly present in a Project
document; it is not a standalone Daily Brief source kind. The frozen public
Projects response omits link details, while verification affects its real vs
partial status. `recent_activity` contains no stable event ID/version, so Core
does not join it to Tasks or Journal by time. No implicit `linked_tasks` field
is inferred. Daily Brief only accepts the D087 `task`, `project`, and
`journal` kinds; one unsupported or unverifiable reference withholds the whole
summary/items while preserving the established response envelope.

Journal source reads open only the exact date file with no-follow semantics and
never open or create a lock file. A verified snapshot requires regular-file,
owner, mode, link-count, device/inode, size, mtime, and ctime metadata to match
before and after the bounded read, plus a post-read no-follow stat proving the
date path still names that same inode. Controlled truncation, same-inode rewrite,
and atomic replacement are rejected as unavailable. This detects concurrent
changes during the read through the post-read identity check; changes after
that check are later filesystem state and do not alter the already captured
snapshot. On platforms without `O_NOATIME`, the OS may update source-file atime
on read; tests permit that metadata-only effect and require names, bytes, size,
mtime/ctime, mode, owner, inode, and link count to remain unchanged.

The D087 Journal source-options implementation is currently an internal Core
service only. Its proposed public route is not registered until A freezes the
wire contract. The localhost HTTP regression mounts a test-only endpoint around
the service; it is not evidence that a production Core route exists.

The app has one authenticated session boundary rather than per-record ACLs.
This matrix records the action permissions required by these readers; it does
not claim fine-grained record ownership. No source lookup reads Raw, Private,
Hermes history, or arbitrary caller-supplied paths.
