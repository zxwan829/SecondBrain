# Daily Brief V1 Core Write

Status: synthetic-only implementation of the A-frozen contract in Issue #97 comment #6286573308. Base main HEAD before this change: `930cd6b266d8aa42819f640b2e233721fcf0a98c` (2026-10-20). No production enablement is implied.

## Implemented

- Adds the frozen `POST /api/daily-brief` contract beside the existing GET: exact request keys, 128 KiB request cap, current `Asia/Shanghai` business day only, approved flag, category/summary/reference budgets, duplicate-key rejection, and no client supplied trusted record fields.
- Requires the registered `daily_brief.write` action. `AppSessionAuth` now keeps an explicit action allowlist and defaults unknown actions to 403. The existing App model is single-owner; this is an explicit action boundary, not a multi-role permission system.
- `manual_generate` accepts only user-approved text. Core verifies each exact `task|project|journal` reference through `SourceReferenceAuthority` before and after commit using separate request-scoped authority snapshots. Missing, stale, forbidden, unsupported, unavailable, mixed and changed-during-commit refs fail closed.
- Persists the strict existing eight-field record through a private, bounded, fsynced, create-only store. A pending operation record is committed first and supports restart recovery; idempotency binds the request fingerprint and authenticated subject. A different payload with the same key or a second key for an occupied day conflicts. The GET reader re-verifies references on every request and withholds stale summaries.
- Writes only allowlisted audit metadata; never summary, source IDs/content, filesystem paths, cookies, session tokens or client subject values. Audit failure returns 503 without a success response.
- `approved_import` validates the frozen `existing_brief` ref shape and returns 501 until an authoritative existing-Brief import adapter exists. It does not pretend an import succeeded.

## Evidence matrix

| Check | Result | Evidence |
|---|---|---|
| Request schema, duplicate JSON keys, body and source budgets | PASS | `test_daily_brief_import.py` |
| Session, Origin and explicit write action; unknown action default deny | PASS | `test_daily_brief_import.py`, `test_app_auth_action_registry.py` |
| Task, Project and Journal trusted refs | PASS | Real localhost Core test `test_source_reference_loopback.py`; all three pass `SourceReferenceAuthority` |
| Atomic create-only, private record, canonical readback | PASS | Synthetic temp-root importer tests and localhost Core POST→GET |
| Same-key replay, body/subject binding, crash recovery, concurrent replay | PASS | `test_daily_brief_import.py` |
| Different key/date collision, stale or unsupported refs | PASS | Targeted importer and HTTP negative tests |
| GET source revalidation and summary withholding after source changes | PASS | Localhost Core test mutates the authoritative Task, GET returns stale with empty items |
| Journal read-only 0500 root / 0400 file; no lock creation on GET | PASS | Localhost Core regression test; actual append is denied with JSON 503 and no file/metadata changes or path/content leakage |
| `approved_import` from existing Brief | NOT IMPLEMENTED; FAIL-CLOSED | HTTP 501; no current authoritative import adapter |
| UI approval flow / desktop, tablet, mobile | NOT RUN | This is a Core-only PR |
| Production data, deployment, scheduler, model, Promote | NOT RUN | Outside authorized scope |

## Targeted verification command

```sh
PYTHONPATH=web-app/secondbrain-core python -m pytest -p no:cacheprovider -q \
  web-app/secondbrain-core/tests/test_app_auth_action_registry.py \
  web-app/secondbrain-core/tests/test_daily_brief_store.py \
  web-app/secondbrain-core/tests/test_daily_brief_import.py \
  web-app/secondbrain-core/tests/test_daily_brief_agent_health.py \
  web-app/secondbrain-core/tests/test_projects_daily_brief_wire.py \
  web-app/secondbrain-core/tests/test_source_reference_loopback.py \
  web-app/secondbrain-core/tests/test_journal_source_snapshot.py \
  web-app/secondbrain-core/tests/test_projects_source_read.py \
  web-app/secondbrain-core/tests/test_tasks.py
```

Latest targeted result: **78 passed**, with one Starlette/httpx deprecation warning. Full Core result: **399 passed, 28 subtests passed**, with 26 existing dependency deprecation warnings. The execution used `/tmp/sb-daily-brief-venv/bin/python` and synthetic temporary roots.

## Next boundary

The A freeze permits synthetic Core-only implementation and review. UI/Edge integration, physical desktop/tablet/mobile validation, deployment and real user data remain separate work. `approved_import` stays unsupported until a canonical existing-Brief source can be verified with a stable ID, version and read permission.
