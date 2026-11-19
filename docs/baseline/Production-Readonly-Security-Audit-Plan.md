# Production Read-only Security Audit Plan

Status: **PLAN ONLY — NOT RUN; production authorization required**
Prepared: 2026-10-22 for Issue #96 PMO comments #6333466319 and #6333663799

## Purpose and current evidence

This is an execution checklist for a future, separately authorized metadata-only review. This task made no NAS/production connection and ran no production command. The 2026-10-19 `Environment-Baseline.md` is a dated historical snapshot, not current runtime evidence.

Static governance documents identify `/volume1/docker/secondbrain/`, `/volume1/docker/secondbrain/core-source/`, `/volume1/SecBR/SecondBrain/`, and `/volume1/SecBR/KnowledgeAssets/` as project/data roots. The latest recorded Compose service labels include `hermes` and `secondbrain-app`; exact current host identity, container names/IDs, UIDs, mounts, ACLs, secret names and presence are **UNKNOWN**. The historical dashboard IP is not an approved SSH target. No target is authorized by this plan alone. `/volume1/SecBR/Private` is excluded from file and ACL inspection; only an explicitly approved exact-container mount listing may establish whether a Private mount is declared.

The latest B-line Core audit is Issue #97 comment [#6333624251](https://github.com/zxwan829/SecondBrain/issues/97#issuecomment-6333624251), based on main `563a6fa8e4d6032a34536d879321738c20cf3c24`. It reports no independent restricted Writer in main, same-UID Core Promote execution, and production `SB_PROMOTE_ENABLED` fail-closed behavior. Its 43 tests plus 4 subtests are synthetic Core evidence, not proof of Linux/production isolation. The historical #106 isolated Linux result is SHA-specific and is not evidence for current main or production. No current Writer/Authority OS identities or mount topology are verified.

## Minimum authorization request

Before execution, the owner must fill and approve every field below. A blank or `UNKNOWN` field means stop before connecting.

| Item | Required approval value |
|---|---|
| Host | Exact NAS hostname/IP, SSH port, and confirmation this is the intended production host (`UNKNOWN`; do not infer from old snapshots) |
| Operator | Exact SSH account and its Docker/metadata permissions; note Docker socket access may be root-equivalent (`UNKNOWN`) |
| Window | Start/end time and local timezone (`UNKNOWN`) |
| Containers | Exact current container names/IDs, approved service role, and approved container UID:GID for the narrowly scoped `stat` query (`UNKNOWN`; historical labels are hints only) |
| Host paths | Exact approved set selected from the four documented roots above; no glob, recursion, or expansion (`UNKNOWN`) |
| Secret targets | Exact approved in-container secret mount target names for metadata-only `stat`; values/content excluded (`UNKNOWN`) |
| Evidence | Local secure output directory, retention/deletion time, and approved redacted summary fields (`UNKNOWN`) |
| Commands | Approval of the exact command templates below, including whether Docker `inspect` and narrowly scoped `exec stat` are allowed |

This checklist does not authorize production access. The proposed connection is SSH only, with TTY and forwarding disabled: `ssh -T -p '<APPROVED_PORT>' -o BatchMode=yes '<APPROVED_USER>@<APPROVED_HOST>' '<ONE_APPROVED_COMMAND>'`. No interactive shell, port forwarding, SCP or SFTP. Each remote command must be one literal allowlisted operation; no chaining or command substitution. It intentionally does not request environment-variable values or enumerate environment-variable names. Docker `.Config.Env`, `env`, `printenv`, full `docker inspect`, Compose interpolation output and raw configuration dumps are excluded because values may contain credentials.

## Exact command allowlist for a future approved run

Substitute only individually approved literal targets. Do not discover targets with broad listing commands. No command below has been run for this task.

1. **Container identity and mounts**, only for each approved container name/ID:

   ```sh
   docker inspect --type container --format 'name={{.Name}} image_id={{.Image}} image={{.Config.Image}} configured_user={{.Config.User}} state={{.State.Status}}{{range .Mounts}} mount={{.Source}}=>{{.Destination}}:{{if .RW}}rw{{else}}ro{{end}}{{end}}' '<APPROVED_CONTAINER>'
   ```

   This returns the **configured** user, not proof of the effective UID of every running process. Do not infer runtime identity from this field; if the approved metadata cannot prove effective identity, report it `UNKNOWN` rather than run an unapproved process inspection. It returns only selected image/state/mount metadata, not `.Config.Env`, command arguments, labels or file contents. The approved container's mount sources and destinations are sensitive metadata; capture them only in the approved evidence location. If any unapproved source path appears, stop and redact it before any issue report.

2. **POSIX metadata**, one non-recursive query per approved exact host path:

   ```sh
   stat -c '%a %u:%g %n' -- '<APPROVED_EXACT_PATH>'
   ```

3. **Synology ACL metadata**, only if explicitly approved and the binary/path are confirmed by the operator without probing outside the allowlist:

   ```sh
   /usr/syno/bin/synoacltool -get '<APPROVED_EXACT_PATH>'
   ```

   Output includes principal names and ACL entries; treat as privileged metadata and redact principal identifiers from the Issue. Never recurse into children.

4. **Secret file presence/mode/owner**, only after explicit approval of this exact form, exact container, UID:GID and each exact target. It starts a short-lived container process but does not open the file:

   ```sh
   docker exec --user '<APPROVED_UID:GID>' '<APPROVED_CONTAINER>' stat -c '%a %u:%g %n' -- '/run/secrets/<APPROVED_SECRET_NAME>'
   ```

   Do not use a shell, wildcard, `cat`, `head`, `sha256sum`, copy, or directory walk. If `stat` is unavailable or permission is denied, stop; do not switch identity or use `sudo`.

Capture approved output locally under a directory created with `umask 077` and mode `0700`; restrict files to `0600`. Do not commit or paste raw output. The Issue report may include only approved redacted container role, configured UID:GID, image digest, mount RO/RW classification, approved-root POSIX/ACL result, secret target basename/presence/mode, timestamp and pass/block reason. Do not include Secret values, business content, Private contents, session data, or unredacted private host paths.

## Stop conditions and recovery

Stop if host, account, window, container or path differs from the approval; any command would expand scope, recurse, read contents, expose a credential, or mutate persistent state; Docker/ACL metadata is not available as approved; permission would require elevation; an unexpected RW mount or Private mount is found; or output contains unapproved data. Do not use `sudo`, restart services, edit Compose, change UID/GID/ACL/mounts, probe writes, or try another host. Preserve only approved metadata evidence and report the exact stop category.

This audit has no production rollback because it is read-only. The `docker exec stat` process exits after each query; if it does not, stop using the approved process-management route, not an invented cleanup command. Any unexpected persistent mutation is an incident: stop and escalate; do not attempt an unapproved fix.

## Separate Hermes role-isolation validation boundary

The offline test uses the existing Core BFF `httpx.MockTransport`, temporary synthetic roots, and D078 Guard unit-test seam only. It does not start Hermes, use a real model, access external networks or use credentials. It tests Chat-session-bound citation access (session A vs. session B), Knowledge permission denial and revocation before source/citation I/O, fail-closed D078 access to Hermes session/private paths, and absence of synthetic source markers in denial receipts/log records. This proves only the exercised code/test seam; it does **not** establish a running Hermes hook, production container/OS UID isolation, actual NAS ACL/mount safety, or production readiness.

## Writer/Promote OS isolation design — proposed, not implemented

This is a review design only. Names below are logical roles; numeric UID:GID values, group membership, socket paths, kernel support, and production mounts remain **UNKNOWN**. Do not map these roles onto the dated Environment-Baseline snapshot as current facts.

| Role / boundary | Proposed identity and access | Explicitly denied |
|---|---|---|
| Hermes / untrusted Agent | Separate runtime identity; no Knowledge mount, no approval key, no Writer socket access | Knowledge writes, approval issuance, Private access |
| Core / Raw admission | Dedicated `sb-core` UID:GID. RW only to its private state and the existing narrow Raw/Capture roots; Review/Knowledge read-only where required by current contracts | Knowledge writes, Writer socket access, Authority signing key, Private mount |
| Approval Authority | Dedicated `sb-authority` UID:GID and private durable approval ledger/key. It validates the authenticated human approval, exact Review/source revision and target policy, then issues a short-lived, single-use capability | Knowledge writes, arbitrary target paths, Private mount; no trust in Agent text, client `approved=true`, or a Core-supplied bare boolean |
| Restricted Writer | Dedicated `sb-writer` UID:GID, separate process and mount namespace; no Core/Hermes shared UID. Accepts requests only over one Unix socket and publishes only a capability-bound create-only target | Approval creation, arbitrary paths, overwrite/delete/rename, shell/model/network access, Private mount |

The Authority's human-approval proof is an unresolved contract gate: it must independently validate an attested approval bound to the authenticated user, Review hash/revision and exact intent. A bare assertion forwarded by Core is insufficient. Do not treat this proposal as solving the D073 single-login/anti-Agent-impersonation requirement; until an approved proof source exists, Authority must refuse to issue capabilities and Promote remains off.

The Authority-to-Writer Unix socket is owned by the Writer UID and a dedicated Authority peer group, with only the Authority UID in that group. The socket parent is traversable only by the intended service identities. The Writer checks Linux `SO_PEERCRED` on every accepted connection and requires the exact Authority UID (and configured GID if used); group membership alone, PID, HTTP headers, Hermes Session, or client fields are not identity proof. Core and Hermes must fail to connect. If peer credentials are unavailable or mismatch, reject before reading a request body and produce no write-side effect. Socket mode/owner and namespace boundaries are separately checked in the disposable Linux experiment. Use `no_new_privs`, drop all ambient/capability sets, and do not grant `CAP_DAC_READ_SEARCH` without a separate security review.

Knowledge stays read-only for Core and absent from Hermes. The Writer receives no Private mount. Its only writable view is a narrowly scoped Knowledge destination. A signed capability binds one operation/approval ID, source reference and revision/hash, one server-selected target identifier, `create_only`, byte limit, expiry and one-use nonce. The caller supplies no filesystem path. The Writer revalidates the capability, enforces an allowlisted target mapping, uses directory-relative no-symlink operations and exclusive creation, and rejects existing targets. An unnamed `O_TMPFILE` plus a no-replace link is a candidate atomic publication pattern, not yet selected: Linux `linkat(AT_EMPTY_PATH)` may require `CAP_DAC_READ_SEARCH`, which must not be granted by default. The lab must prove a no-added-capability publication method on the selected kernel/filesystem (including any `/proc/self/fd` alternative); if none is available, the design stays blocked. Linux filesystem policy (prefer Landlock where supported) must permit only required create/write/link operations and deny removal, rename and truncation rights; Landlock ABI v3 or newer is needed to control truncation. The disposable VM must prove the exact rights. Do not silently fall back to ordinary rename. A read-write directory permission alone is not create-only because POSIX directory write can also permit unlink/rename.

| Path class | Core | Authority | Writer | Hermes / Agent |
|---|---|---|---|---|
| Core private state and approval ledger | Core state RW; no Authority key | Authority ledger RW; Core has no direct write path | No mount | No mount |
| Raw/Capture and Review source | Narrow Raw create/read per capture contract; Review read/verified write per existing flow | Review/source read-only only as required for hash/revision validation | No source-root mount; receives bounded content/hash only after capability validation | Existing narrow capture roots only; no Knowledge access |
| Knowledge root | RO | RO only if needed for exact target/version check | No broad root RW; exact destination scope only | No mount |
| Private | No mount | No mount | No mount | No mount |
| Temporary staging | No mount | No mount | Prefer unnamed `O_TMPFILE` in exact destination dir; no shared staging tree | No mount |

**Filesystem action contract:** Raw/Review files retain their existing no-overwrite and source-preservation rules. Knowledge publication is create-only: no overwrite, unlink, or rename of an existing Knowledge item. No process gets general write access to the Knowledge root. Directory ACLs/mount flags must be reviewed with the actual kernel and filesystem; application checks are not a substitute. If the filesystem cannot enforce the required remove/rename denial, the design must use an independently constrained commit boundary or remain blocked; do not weaken create-only semantics.

**Crash/recovery contract:** persist an operation claim and one-use nonce before Writer dispatch. Snapshot only the approved bounded source bytes, verify source identity/revision/hash and byte limit, write the unnamed temporary inode, verify hash, fsync it, then publish using atomic no-replace `linkat`; persist/reconcile the result by operation ID. After restart: if final target is absent, resume only the same still-valid operation after source/version revalidation; if final target hash matches, reconcile success without a second write; if a mismatched target exists, mark `recovery_required`, preserve it, and require explicit review. A crash before publication leaves no directory entry; a crash after publication but before audit/result persistence is reconciled by exact operation ID and hash. Never overwrite or auto-delete an existing target as rollback. Rollback is a separately approved compensating action; this design's default recovery is stop-and-reconcile, not destructive reversal. Source rename/replacement before capability issuance must fail the source identity/revision/hash recheck; the Writer receives only the already bounded and approved snapshot, not a Raw path. The exact atomic sequence and Landlock rights remain to be proven in the Linux lab before implementation.

## Linux isolation experiment — plan only, no real data mounts

Run only after separate authorization in a newly provisioned, disposable Linux VM with an ephemeral disk, network disabled, no shared folders/virtiofs/9p, no Docker socket, no production or host data bind mounts, no Secrets, and only freshly generated synthetic fixtures. Do not use macOS or a mocked peer-credential API as evidence for kernel UID/GID or `SO_PEERCRED`. The VM image, kernel, filesystem and runner are not yet selected (**UNKNOWN**). This task did not create the VM, users, directories, mounts or ACLs and did not run Linux identity tests.

| Case | Minimal experiment | Required result |
|---|---|---|
| Identity and socket | Create only disposable `sb-core`, `sb-authority`, `sb-writer`, and `sb-outsider` users/groups inside the throwaway VM; record numeric IDs. Connect each to the Unix socket and inspect peer creds. | Authority UID accepted; Core, Hermes-equivalent outsider and mismatched GID rejected before body handling; no files changed. |
| Core direct-write denial | Core reads the synthetic Knowledge fixture but attempts create, overwrite, rename and unlink in the Knowledge root. | Reads allowed only where specified; all writes fail at OS boundary; Private path is absent in every mount namespace. |
| Writer create-only | Issue one synthetic signed capability for a fixed target; try exact create, replay, second target, traversal/symlink, overwrite/truncate, unlink and rename. Record Landlock ABI and filesystem support; exercise the configured policy with all capabilities dropped. | First exact create succeeds once; all replay/alternate/overwrite/truncate/delete/rename/traversal attempts fail without side effects. No added capability is needed for publish. Missing kernel/filesystem enforcement or a required privilege is BLOCKED, not a pass. |
| Source race / revocation | Change synthetic source revision/hash or revoke the approval between preview and publish; race a rename/replacement against final validation. | Authority refuses capability or Writer refuses publish; no target or audit success is created. |
| Crash recovery | Inject process termination before staging, after `O_TMPFILE` fsync, after no-replace link, and before final audit/result persistence; restart the isolated services. | Pre-publication temporary inode leaves no visible target; post-publication target reconciles once by operation ID/hash; no duplicate/overwrite; mismatch becomes `recovery_required` and is preserved for review. |
| Logging and side effects | Use unique synthetic markers in source and denial requests; inspect only the test runner's generated logs and output counters. | Logs contain IDs/status only, never source text, secret-like fixture, or Private marker; denied cases produce no filesystem changes. |

The lab report should retain only kernel/filesystem versions, Landlock ABI, logical role-to-UID:GID mapping, socket owner/mode and peer result, mount/LSM/capability policy summary, operation status/hash, and pass/block counts. Do not retain fixture contents or full request bodies. Cleanup may remove only the newly created disposable VM and its synthetic disk after recording redacted results; no host path, shared root, prior image, or user file may be swept. Unknown runner/VM and whether the required filesystem policy is available remain blockers to execution.

Linux primitive references for this proposed test design: [`SO_PEERCRED`](https://man7.org/linux/man-pages/man7/unix.7.html), [`O_TMPFILE` / `linkat`](https://man7.org/linux/man-pages/man2/open.2.html), [`linkat(AT_EMPTY_PATH)` privilege requirement](https://man7.org/linux/man-pages/man2/linkat.2.html), and [Landlock filesystem rights and ABI limitations](https://docs.kernel.org/userspace-api/landlock.html). These references do not establish availability on any project host.

## Authorization checklist

- [ ] Exact production host, SSH port, account, time window and operator identity approved; `-T`, BatchMode and no forwarding accepted. All are currently `UNKNOWN`.
- [ ] Exact container names/IDs and command 1 approved; Docker socket privilege risk accepted.
- [ ] Exact host path list and commands 2–3 approved; Private content excluded.
- [ ] Exact secret mount target names, container UID:GID and command 4 approved separately; omit this query if secret metadata is not required for the approved decision.
- [ ] Local evidence destination, retention and redacted Issue fields approved.
- [ ] Stop conditions and no-write/no-restart/no-elevation boundary accepted.

Until all required fields and checkboxes are approved, `PRODUCTION_READONLY_AUDIT=READY_FOR_TARGETED_AUTHORIZATION`; live production audit remains `NOT_RUN` and runtime metadata remains `UNKNOWN`. The OS design is `OS_ISOLATION_DESIGN=READY_FOR_REVIEW`, not approved/implemented. `LINUX_ISOLATION_TEST=PLAN_ONLY`; VM/runner/kernel and any Linux identity/mount changes require separate authorization. No test plan here authorizes changing production or real data.
