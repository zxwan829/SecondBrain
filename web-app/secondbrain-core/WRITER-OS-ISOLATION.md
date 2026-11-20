# Restricted Writer OS isolation verification

## Evidence status

**`OS_ISOLATION_NOT_VERIFIED` for production (local environment snapshot: 2026-10-21).** The
available machine is macOS 14.8.9, x86_64, UID 501/GID 20. Python has no
`socket.SO_PEERCRED` on this platform (it exposes `LOCAL_PEERCRED`, which this
Linux-specific Writer entry point does not accept). No Docker, Podman, Colima,
Lima, Multipass, or QEMU executable was found. Existing Writer unit and socket
pair tests use injected peer identity or one OS identity; neither is OS
isolation evidence. No host identity, group, ACL, mount, or permission was
changed to attempt this test. No new Linux container/VM was provisioned.

### 2026-10-21 latest-main revalidation

- Candidate was rebased onto main `7ceec110c6e361ba8661c2ab005ab8906ea2323a`; fixed PR HEAD is recorded in PR #106 and Issue #97.
- On macOS 14.8.9 x86_64 with Python 3.12.14, Writer focused tests reported **24 passed, 1 skipped**. The skipped test is the Linux-only real UID/GID + `SO_PEERCRED` harness; it is **NOT RUN**, not a pass.
- Full Core on this latest-main candidate reported **488 passed, 1 skipped, 28 subtests passed**. The single skip is the same Linux-only kernel isolation test.
- Linux workflow run [39583394667](https://github.com/zxwan829/SecondBrain/actions/runs/39583394667) reports **1 passed** in its dedicated OS isolation step at workflow SHA `accfe3e4b643a8d1ca1402e274255d4e1e94071c`. The Writer implementation and Linux isolation test files are unchanged from that tested SHA through the rebased candidate. The workflow's separate full Core step failed on an atime-ordering fixture; that fixture was corrected later, but the Linux full Core suite has not been rerun. Do not claim latest-main Linux full-suite PASS.
- `git diff --check origin/main...HEAD` and `git merge-tree --write-tree origin/main HEAD` passed on this rebased candidate. The disposable Linux runner is synthetic-only evidence; production identity, service topology, ACL/mount and NAS behavior remain **NOT VERIFIED**.

## Reproducible Linux harness

`tests/test_restricted_knowledge_writer_linux_os_isolation.py` is an opt-in
integration test. It skips unless all of these are true:

- Linux with the real kernel `SO_PEERCRED` interface;
- root **inside an ephemeral, disposable Linux runner/container**;
- `SB_WRITER_OS_ISOLATION=disposable-linux`;
- Python and pytest are already available in the isolated environment.

Run from `web-app/secondbrain-core` in that isolated runner/container:

```sh
SB_WRITER_OS_ISOLATION=disposable-linux PYTHONPATH=. python -m pytest -q -p no:cacheprovider tests/test_restricted_knowledge_writer_linux_os_isolation.py
```

The repository's existing `D077 Core Linux tests` workflow now runs this same
command through `sudo` on its ephemeral `ubuntu-24.04` GitHub-hosted runner,
then runs the complete Core suite as the ordinary runner user. Dispatch that
existing workflow against the PR branch (the workflow file is already present
on `main`):

```sh
gh workflow run d077-core-linux-tests.yml --ref codex/knowledge-writer-minimal-20261020
```

The root process only changes IDs and ownership below its dedicated synthetic
temporary directory. No repository secret is read, no production path is
mounted, and no persistent runner identity or permission is changed. The
workflow run is the only authorized Linux OS evidence for this candidate; a
local macOS skip remains `NOT RUN`.

The test provisions only numeric identities and synthetic paths below a
randomly named `/tmp/secondbrain-writer-os-isolation-*` root (mode `0710`,
Writer owner and Core access group). It starts the actual Writer entry point as UID 31003,
real GID 31004, effective GID 31002; runs Core as UID/GID 31001/31002; and
tries an unauthorized peer UID 31005. It exercises the actual AF_UNIX listener
and default kernel peer-UID reader, checks parent/socket owner, group and mode,
proves Core cannot create or directly overwrite Knowledge, verifies Writer
create-only persistence and receipt ownership, rejects a different peer UID,
and confirms a receipt/target mismatch returns `RecoveryRequired` without a
Writer rewrite. Corruption used for recovery testing is injected by the test
fixture inside its temporary directory.

### Identity boundary in the current candidate

The current socket and Knowledge-directory contract requires the Writer's
effective GID to equal the Core access GID; Knowledge is Writer-owned and
Core-group-readable (`0750`), while the socket parent/socket use that shared
group (`0710`/`0660`). The harness therefore proves distinct Core/Writer UIDs
and distinct real primary GIDs, with the explicitly shared effective access
GID. If acceptance requires *different effective GIDs as well*, the current
contract cannot satisfy that condition. Treat it as a PMO/security design
decision; do not quietly change the IPC or filesystem group contract in this
test-only slice.

## Minimal authorization package if no isolated Linux environment is already provisioned

This machine currently has no supported local Linux container runtime. To run
the harness, provide or explicitly authorize one **ephemeral, local, disposable
Linux container** using a preloaded, trusted Python+pytest image. The run needs
only:

- runner/container-local root capability to `chown`, `setgroups`, `setresgid`, and
  `setresuid` inside pytest's synthetic temporary directory;
- no `--privileged`, host namespace access, host `/etc/passwd` changes, or
  host UID/GID creation;
- network disabled; repository source mounted read-only; test scratch on
  container-local tmpfs; no Vault, NAS, Knowledge, Private, or business paths
  mounted;
- maximum run time 10 minutes, after which the container and scratch data are
  destroyed. No image pull or package install is part of the test command.

If provisioning that container requires installing/enabling a host runtime,
changing OS permissions, or granting host administration, stop and request a
separate authorization naming that exact operation. A macOS `LOCAL_PEERCRED`
probe, mocked credential callback, chmod-only test, or same-UID process is not
a substitute for the Linux result.
