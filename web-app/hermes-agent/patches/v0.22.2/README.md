# Hermes v0.22.2 fail-closed and bounded Weixin overlay

This overlay targets the exact upstream source commit `d923a5eb487a17c0a68801bba9ef0f56c81040a8` used for Hermes v0.22.2. It carries two source patches:

- `pre-tool-hook-fail-closed.patch` changes only `agent/tool_executor.py::_pre_tool_block` and adds a focused regression test.
- `weixin-media-download-budget.patch` adds a streaming 128 MiB bound to Weixin downloads and regression tests for exact-limit, declared-oversize, and streamed-oversize bodies. It rejects an oversized or malformed Content-Length before consuming the body, and still enforces the cap when the header is absent or inaccurate. The failure path returns no partial attachment to the cache.

The Weixin cap matches the SecondBrain Core inbound media budget. It bounds each individual response body in memory; it does not claim to provide aggregate concurrent-download budgeting or durable Inbox replay semantics. Source pins, DM/group policy and Core identity authorization remain separate configuration/contract concerns.

When hook dispatch succeeds, existing behavior is preserved: normal calls continue with the original or hook-modified arguments, and a hook denial stays a denial. If importing or dispatching the pre-tool hook raises an ordinary `Exception`, the function now returns the fixed `PRE_TOOL_CALL_HOOK_UNAVAILABLE` block result. The tool executor consumes that result before guardrails or the real tool callback, so the tool is not executed. The failure response and log do not include exception text or tool arguments.

## Reproduction

From a clean Hermes source checkout at the exact commit above:

```sh
git apply --unidiff-zero --check /path/to/pre-tool-hook-fail-closed.patch
git apply --unidiff-zero /path/to/pre-tool-hook-fail-closed.patch
python -m pytest -q tests/agent/test_tool_executor_pre_tool_dispatch.py
```

The test covers successful File and Skills dispatch, preservation of a sensitive-path hook denial, and execution blocking for both dispatcher `ImportError` and runtime exceptions.

The Weixin download tests run from the same pinned source checkout after applying both patches:

```sh
git apply --unidiff-zero --check /path/to/pre-tool-hook-fail-closed.patch
git apply --unidiff-zero /path/to/pre-tool-hook-fail-closed.patch
git apply --check /path/to/weixin-media-download-budget.patch
git apply /path/to/weixin-media-download-budget.patch
python -m pytest -q tests/gateway/test_weixin.py tests/gateway/test_weixin_secret_scope.py tests/gateway/test_weixin_typing.py
```

This source patch is pinned to the source commit and official base image below. The NAS deployment and runtime verification record is maintained in `docs/baseline/Environment-Baseline.md`; API Terminal remains disabled.

## Minimal fixed-base image

`Dockerfile` derives from the exact official v0.22.2 digest and replaces only `/opt/hermes/agent/tool_executor.py` with the patched file. It does not rebuild dependencies or change the entrypoint, profile, toolset, or `/opt/data` state. `build-fixed-image.sh` verifies a clean source checkout at the pinned commit, applies this patch to an archive of that commit, and builds a `linux/amd64` image with network disabled, CPUs pinned to cores 0-1, and 2 GiB memory. The `cpuset` limit is used because DSM's Docker 24 legacy builder does not support `--cpus`:

```sh
web-app/hermes-agent/patches/v0.22.2/build-fixed-image.sh /path/to/hermes-agent secondbrain-hermes:v0.22.2-failclosed
```

The local image tag is supplied by the operator; record the resulting image ID, patch SHA-256, and source commit with each deployment. The image is derived from the official digest and its one-file patch overlay, not claimed to be byte-for-byte reproducible across Docker builders.
