# Production Read-only Security Audit Plan

Status: **PLAN ONLY — NOT RUN; production authorization required**

Prepared: 2026-10-22 for Issue #96 PMO comment #6333339018

## Scope and evidence boundary

This document defines a future metadata-only audit. No NAS/production connection, command, container inspection, filesystem access, or business-data access was performed for this plan. Facts in repository guidance and the dated `Environment-Baseline.md` are historical references, not live evidence.

The documented NAS project root is `/volume1/docker/secondbrain/`, with Core source/build context `/volume1/docker/secondbrain/core-source/`. Documented business roots include `/volume1/SecBR/SecondBrain/` and `/volume1/SecBR/KnowledgeAssets/`; Private is explicitly excluded. These paths and documented container names must be re-confirmed from an approved allowlist before any future inspection. Current host identity, container inventory, image digests, UID/GID, ACLs, mounts, secret references and runtime flags are **UNKNOWN** until a separately authorized live audit.

## Proposed read-only inventory

After explicit authorization naming the host, time window, operator identity and exact allowlisted paths/containers, collect only:

- Host/DSM identity and audit timestamp.
- Container names, state, image reference/digest and configured UID:GID.
- Mount source/destination and read-only/read-write flags for the approved containers.
- POSIX owner/group/mode and ACL metadata for the exact approved directory roots; no recursive traversal.
- Security-relevant environment-variable **names** and feature-flag state where safely obtainable. Never emit environment values, token values, secret contents, or full unfiltered container configuration.
- Secret reference/file names, presence and mode only; do not open, hash, copy or display secret files.

Candidate commands must be reviewed against the approved host and exact targets before use. Examples of metadata-only forms are `docker ps --format` with name/state/image fields; `docker inspect --format` selecting only name, image, configured user, state and mount metadata; and a non-recursive `stat`/ACL query for each allowlisted root. Do not use broad `docker inspect`, `env`, `find`, recursive listing, application APIs that return records, or commands that dump file contents. Secret variable names must be filtered locally before output; no command may print their values.

## Stop conditions and recovery

Stop immediately if target identity or path differs from the approved allowlist; a command would recurse, read content, reveal a secret value, or mutate state; an unexpected read-write mount or identity appears; output includes business content; permissions require elevation beyond the approved read-only identity; or the tool cannot guarantee read-only behavior. Do not use `sudo` as a workaround, edit Compose, change UID/GID/ACL/mounts, restart services, probe writes, or broaden scope. Preserve the captured metadata securely and report the stop reason.

The planned audit has no rollback because it performs no writes. If any unexpected mutation is observed, stop all work, preserve evidence, and escalate; do not attempt an unapproved corrective mutation. Do not inspect Task, Journal, Knowledge, Capture, Private or personal Session contents.

## Separate Hermes role-isolation test proposal

Run only in a disposable local synthetic environment with no live Hermes, real model, external network, production credentials, or user content. Create synthetic sessions A and B and a fake/offline provider. Verify that B cannot read A's context or invoke A's tools; a revoked/untrusted role cannot access protected roots; allowed requests expose only the explicitly granted synthetic fixture; denials are fail-closed; and logs contain neither fixture bodies nor secrets. Record status codes and redacted structural evidence only. This is a separate test authorization from any production metadata audit and must never be represented as a production isolation result.

## Authorization checklist for a future run

- [ ] Explicit authorization for a metadata-only production audit.
- [ ] Exact host, maintenance window, operator/read identity, container names and path allowlist.
- [ ] Confirmation that Private and all business file contents remain excluded.
- [ ] Approved command list and output destination with secret-value suppression.
- [ ] Independent approval for the separate local Hermes role-isolation test, if desired.

Until these are approved and executed, `PRODUCTION_READONLY_AUDIT_PLAN=READY_PLAN_ONLY`, live production audit `NOT_RUN`, and Hermes role-isolation `NOT_RUN`.
