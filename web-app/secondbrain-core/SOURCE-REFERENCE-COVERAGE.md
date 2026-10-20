# Core source reference coverage

This matrix records what the local Core readers can verify from configured,
bounded, read-only stores. `verified` is reserved for an exact authoritative ID
and a version that Core recomputes from the same source bytes.

| Kind | Stable ID authority | Version authority | Permission check | Read bound | Outcome |
|---|---|---|---|---|---|
| `project` | `ProjectsSourceReadStore` exact document `id` | SHA-256 of exact JSON bytes read from the configured project root | App `projects.read`; Brief also requires `daily_brief.read` | 200 entries, 64 KiB/file, 2 MiB total | `verified`, `stale`, `missing`, or `unavailable`; incomplete snapshots never prove absence |
| `task` | TaskStore issues durable `id` | No published canonical source version/hash contract | App `daily_brief.read` only; no per-record owner ACL contract | Existing projection is capped at 2 MiB, but no source adapter is enabled | `unsupported`; Brief content withheld |
| `note` | Notes API reads by collection/path; no authoritative opaque ID-to-path index | No published stable version contract for source refs | App `daily_brief.read` only; no source adapter is enabled | Notes path read is available, but scanning/path guessing is not used | `unsupported`; Brief content withheld; project `linked_notes` suppressed |
| `capture` | No exact-ID read adapter in this projection | No compatible source-ref version contract | Not checked by this projection | Not read | `unsupported`; Brief content withheld |
| `review` | No exact-ID read adapter in this projection | No compatible source-ref version contract | Not checked by this projection | Not read | `unsupported`; Brief content withheld |
| `journal` | Date-file storage has no published opaque source-ref ID adapter | No compatible source-ref version contract | Not checked by this projection | Not read | `unsupported`; Brief content withheld |

Projects currently accept `linked_notes` references in their input schema, but
Core does not publish them until a stable Notes ID/version authority exists.
`recent_activity` contains only kind and timestamp, so Core does not join it to
Tasks or Journal by time. A `linked_tasks` field is not part of the current
project schema and is not inferred. These limits preserve the frozen public
Projects and Daily Brief response envelopes and avoid inventing IDs or versions.

The app has one authenticated session boundary rather than per-record ACLs.
This matrix does not claim fine-grained record ownership. No source lookup reads
Raw, Private, Hermes history, or arbitrary caller-supplied paths.
