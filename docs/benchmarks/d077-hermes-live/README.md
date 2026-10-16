# D077 Hermes live learning experiment (historical)

`hermes_live_ci.py` is the isolated, synthetic-only GitHub Actions runner previously stored at `tests/d077/hermes_live_ci.py`. It was moved here to avoid a top-level `tests/` directory containing only a one-off evaluation artifact.

The associated workflow is `.github/workflows/d077-hermes-live.yml`. It is **manual (`workflow_dispatch`) only** and its script path has been updated. The script contains a live SiliconFlow provider proxy and references the `SILICONFLOW_D077_KEY` Actions secret: **do not run it without fresh user authorization for provider, request count, budget and synthetic input**, even if the workflow is still available.

The earlier evaluation is historical; current Hermes/D078 deployment, security status and NEXT are recorded in `../../baseline/00-CURRENT.md`, `../../baseline/Environment-Baseline.md` and `../../baseline/Progress-Log.md`. Moving the script does not indicate it has been re-run. Regular Core regression tests stay in `web-app/secondbrain-core/tests/`.
