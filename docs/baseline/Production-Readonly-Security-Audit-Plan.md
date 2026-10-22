# Production Read-only Security Audit Plan

Status: **PLAN ONLY — NOT RUN; production authorization required**
Prepared: 2026-10-22 for Issue #96 PMO comments #6333339018 and #6333466319

## Purpose and current evidence

This is an execution checklist for a future, separately authorized metadata-only review. This task made no NAS/production connection and ran no production command. The 2026-10-19 `Environment-Baseline.md` is a dated historical snapshot, not current runtime evidence.

Static governance documents identify `/volume1/docker/secondbrain/`, `/volume1/docker/secondbrain/core-source/`, `/volume1/SecBR/SecondBrain/`, and `/volume1/SecBR/KnowledgeAssets/` as project/data roots. The latest recorded Compose service labels include `hermes` and `secondbrain-app`; exact current host identity, container names/IDs, UIDs, mounts, ACLs, secret names and presence are **UNKNOWN**. The historical dashboard IP is not an approved SSH target. No target is authorized by this plan alone. `/volume1/SecBR/Private` is excluded from file and ACL inspection; only an explicitly approved exact-container mount listing may establish whether a Private mount is declared.

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

## Authorization checklist

- [ ] Exact production host, SSH port, account, time window and operator identity approved; `-T`, BatchMode and no forwarding accepted.
- [ ] Exact container names/IDs and command 1 approved; Docker socket privilege risk accepted.
- [ ] Exact host path list and commands 2–3 approved; Private content excluded.
- [ ] Exact secret mount target names, container UID:GID and command 4 approved separately.
- [ ] Local evidence destination, retention and redacted Issue fields approved.
- [ ] Stop conditions and no-write/no-restart/no-elevation boundary accepted.

Until all required fields and checkboxes are approved, `PRODUCTION_READONLY_AUDIT_PLAN=READY_PLAN_ONLY`; live production audit remains `NOT_RUN` and runtime metadata remains `UNKNOWN`.
