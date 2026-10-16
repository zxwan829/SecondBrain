# Hermes v0.22.2 `pre_tool_call` fail-closed patch

This patch targets the exact upstream source commit `d923a5eb487a17c0a68801bba9ef0f56c81040a8` used for Hermes v0.22.2. It changes only `agent/tool_executor.py::_pre_tool_block` and adds a focused regression test.

When hook dispatch succeeds, existing behavior is preserved: normal calls continue with the original or hook-modified arguments, and a hook denial stays a denial. If importing or dispatching the pre-tool hook raises an ordinary `Exception`, the function now returns the fixed `PRE_TOOL_CALL_HOOK_UNAVAILABLE` block result. The tool executor consumes that result before guardrails or the real tool callback, so the tool is not executed. The failure response and log do not include exception text or tool arguments.

## Reproduction

From a clean Hermes source checkout at the exact commit above:

```sh
git apply --unidiff-zero --check /path/to/pre-tool-hook-fail-closed.patch
git apply --unidiff-zero /path/to/pre-tool-hook-fail-closed.patch
python -m pytest -q tests/agent/test_tool_executor_pre_tool_dispatch.py
```

The test covers successful File and Skills dispatch, preservation of a sensitive-path hook denial, and execution blocking for both dispatcher `ImportError` and runtime exceptions.

This source patch is not part of the currently deployed Hermes image and does not change NAS configuration. A future deployment requires a separately reviewed, reproducible image build pinned to the source commit and official base image, then separate deployment authorization and runtime verification. Keep API Terminal disabled until that work is approved and verified.
