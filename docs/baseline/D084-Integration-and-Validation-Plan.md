---
created: 2026-10-17
updated: 2026-10-17
status: historical-reviewed-plan
type: integration-plan
---
# D084 — Integration and unified validation plan

**Historical plan (as of 2026-10-17):** The NEXT steps and branch/PR statuses below describe the D084 pre-integration audit, **not the current project's next action or main state**. The D081–D083 slices and the reviewed PR #37 changes were later integrated through PR #45, and M1 has since completed a user-approved limited acceptance (Issue #66). Current sole NEXT is in [`00-CURRENT.md`](00-CURRENT.md), with M2 planning in [Issue #76](https://github.com/zxwan829/SecondBrain/issues/76). Do not rerun the old instructions or use them as production authorization.

This reviewed plan is a sequencing and acceptance document, not implementation or deployment authorization. PR #39 completed the document-review gate; this file is not permission to start engineering integration. Current state is maintained in [`00-CURRENT.md`](00-CURRENT.md); production evidence remains in [`Environment-Baseline.md`](Environment-Baseline.md). Source audit was performed against main `628bec895e8d95646b5cc583e8ffea8f7e877e10`, parallel development branch `dev/parallel-v1-next-20261017` at `e5f5c72b72511e14a4a1ee403b31cafbdd50fa69`, and PR #37 at `e5332f6fa175d0742cacbaec2fbab40ded4781a4`.

## 1. Integration order and branch safety

1. **DONE:** Documentation PR #39 has been reviewed and merged into main. Later documentation-only governance PRs #40/#41 are also merged. No feature PR was merged as part of D084.
2. **NEXT, pending explicit authorization:** Create one integration branch from the then-current GitHub `main` (never assume the historic audit SHA is still HEAD). Preserve the main-only D082 `personal_learning.py` and regression fix; at the D084 audit baseline main had one unique commit while the parallel branch had three; documentation-only merges since then mean commit counts must be rechecked before integration.
3. Bring the audited D081 Journal Core/API and D082 Chat Journal / D083 Task slices from `dev/parallel-v1-next-20261017` into that integration branch. Resolve, review, and test conflicts; do not reset or replace main with the parallel branch.
4. Adapt PR #37's one-time file-write approval changes onto the integrated branch after checking the actual combined Guard/Core/BFF/UI contract. PR #37 is still open and unmerged. Its review approval is not runtime evidence.
5. Run the focused unified synthetic checks in Section 3. Publish per-scenario `PASS`, `FAIL`, or `BLOCKED` with evidence and stop after development validation. Any NAS operation, production data-root provisioning, real-model request, or real-user-data egress needs its own explicit authorization. Do not merge the integration PR or deploy merely because local tests pass.

## 2. Known integration seams and status

| Area | Development contract | Current integration concern |
|---|---|---|
| Personal Learning | D082 memory extraction/recall fix is already on main `628bec8…`; Core JSONL remains the only personal-memory authority. | Preserve main's fix when bringing in the older-base parallel branch. Production re-verification of natural cross-session recall is not complete. |
| Journal | Core `GET /api/journal/{day}` and `POST /api/journal/entries`; separate `SB_JOURNAL_ROOT`; action checks `journal.read` / `journal.append`; date-partitioned append-only JSONL. | Parallel-branch code only. Production root/ownership/mode and deployment are not configured or evidenced. Chat routes only explicit Journal intent to the API. |
| Task | Core `GET/POST /api/tasks` and `PATCH /api/tasks/{task_id}`; separate `SB_TASK_ROOT`; action checks `task.read` / `task.write`; persistent task state and update history. | Parallel-branch code only. Production root/ownership/mode and deployment are not configured or evidenced. Reminder delivery is **NOT IMPLEMENTED**. Chat routes explicit Task commands only. |
| File write approval | PR #37 Guard/Core/UI binds supported `write_file` and single-target replace `patch` to one authenticated Run decision; unsupported mutation tools and ambiguous V4A multi-file patch are denied. | PR #37 is open, not on main, and not deployed. Validate its behavior against the integrated versions of `App.tsx`, Core `app.py`/BFF, `test_web_app_bff.py`, approval registry and actual Hermes Run/SSE event contract. |
| Capture / Knowledge | Keep existing Capture API and Raw→Review behavior; Knowledge writes remain Core Promote-only. | Ensure Chat explicit-intent routing does not steal ordinary Chat/Capture input, and that integration adds no generic path or Knowledge write permission. |

Shared conflict/review files to inspect explicitly: `web-app/secondbrain-frontend/src/App.tsx`, `web-app/secondbrain-core/secondbrain_core/app.py`, `web-app/secondbrain-core/tests/test_web_app_bff.py`, `docs/baseline/00-CURRENT.md`, and `docs/baseline/Progress-Log.md`. Also inspect Journal/Task stores, Chat intent parsers, approval registry/UI, and Core configuration examples if changed.

## 3. Unified synthetic validation matrix

Use existing focused unit/API tests and the existing deterministic Hermes test double or pinned local Hermes integration entrypoint. Do not create a new service or repeat unrelated full suites. Record each scenario separately; a dependent test whose prerequisite failed or was skipped is `BLOCKED`, never a fabricated `PASS`.

| Scenario | Minimum synthetic evidence | Pass condition |
|---|---|---|
| Hermes Chat / Session / Run / SSE | Existing adapter/BFF fake or pinned local API test; cover create/continue Session, Run request, streamed events, completion/error/stop mapping. | Correct Session and Run association; expected instructions and SSE events reach the App; failure remains visible. |
| Memory relevance / correction | Existing `test_personal_memory.py`, `test_personal_learning.py` and BFF coverage on temporary Core roots. | Related active synthetic memory reaches a new Session; unrelated memory is omitted; correction/withdrawal prevents stale value injection and retains source/history. |
| Explicit Journal intent | Existing Chat intent/API, `test_journal.py`, and BFF tests with temporary `SB_JOURNAL_ROOT`. | Explicit prefix appends the exact original text once and can be read by day; ordinary Chat creates no Journal; retry is idempotent; unconfigured root fails closed. |
| Explicit Task intent | Existing intent/UI/API, `test_tasks.py`, and BFF tests with temporary `SB_TASK_ROOT`. | Explicit command creates a task; list, update, complete/reopen persist; retries do not duplicate; stale version is rejected; unconfigured root fails closed. Reminder delivery remains NOT IMPLEMENTED and is not marked PASS. |
| File approval | Guard + Core approval registry/BFF/UI tests. | Supported write shows exact target and args, waits for explicit one-time approval, and rejects denial, replay, owner/Session/Run mismatch and unsupported write operations. Sensitive path and Skills protections remain effective. |
| Capture preservation | Existing Capture API and frontend flow tests. | Existing text/file Capture retains Raw and Review behavior; no automatic Promote; explicit Journal/Task parsing does not hijack Capture mode. |
| Persistence / restart | Close/recreate stores against temporary test roots and re-read synthetic Journal/Task/Memory artifacts. | Only expected state persists; source/version/append semantics remain intact; no production path is used. |

Likely Core test targets already present on the parallel branch: `test_personal_memory.py`, `test_personal_learning.py`, `test_journal.py`, `test_tasks.py`, `test_run_approvals.py`, `test_capture.py`, and `test_web_app_bff.py` (select only those affected by the integration). Existing frontend targets include `JournalPage.test.tsx`, `TaskPage.test.tsx`, `chat-approval.test.ts`, capture-flow tests, and Chat intent/UI tests available in the combined branch. Run typecheck/build only if frontend integration changes warrant them. Existing passing slice tests need not be repeated if their code and shared interfaces are unchanged.

## 4. Gate before any real runtime or model validation

This is a readiness checklist only. No item is authorized by this document.

- Confirm the current NAS snapshot and rollback point before a separately authorized change. Provision distinct `SB_JOURNAL_ROOT` and `SB_TASK_ROOT` under the Core state boundary only, owned by the Core runtime identity with least privilege (target `0700`); keep Hermes unable to write either root. Verify App/Hermes image and Guard/manifest versions against the approved commits.
- Confirm existing D077 JSONL path and data are unchanged; do not migrate or clean it. Keep API Terminal OFF, Private unmounted, Knowledge RO apart from its existing Capture-only inbox mount, Promote OFF, and Scheduler OFF.
- Verify App/Core authentication and action policy for Journal/Task; test that missing roots and unauthorized requests fail closed. Preserve an independently restorable Compose/image/config snapshot and document targeted rollback before deployment.
- Before any external provider request, name provider/model, synthetic vs personal-data scope, maximum Run count, input/output token limits, estimated cost ceiling, stop conditions and credential handling. A local estimate is not a vendor hard spending limit. If real personal-data egress is proposed, request and receive that specific authorization separately.
- Run real browser/production checks only after explicit authorization, then report deployment, runtime test and user acceptance as separate states. Stop before a real-model Run if any security boundary or cost condition is unknown.

## 5. Explicit known gaps

- Natural cross-Session recall previously failed in Issue #28. Main contains the extraction fix, but source/local tests do not establish successful production recall.
- Journal and Task are DEV-TESTED slices on the parallel branch only; neither is integrated into main or production. `SB_JOURNAL_ROOT` / `SB_TASK_ROOT` production provisioning is absent or unverified.
- Task reminder delivery is **NOT IMPLEMENTED**.
- PR #37's approval flow has not been integrated or validated in a real Hermes API Run. Review and unit tests do not prove runtime enforcement.
- No browser user acceptance, NAS verification, real-model test, or real personal-data processing is part of this documentation task.
- Open issues #28/#30 retain unresolved cross-Session recall evidence, and #14/#27 hold earlier phase/budget evidence. Their open state does not automatically authorize retries, deployments or model calls; use the single NEXT in `00-CURRENT.md`.
