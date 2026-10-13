# Promote prototype (legacy compatibility and test fixtures)

The implementation has moved into `../secondbrain-core/secondbrain_core/modules/review_promote/` as an internal Core module. New integration must use `PromoteService` and the Core router factory; it performs trusted approval persistence and promotion in the same Core process. The old polling runner and cross-container approval queue are not the target architecture and must not be deployed.

The existing files in this directory remain as compatibility imports and regression fixtures while callers migrate. Run the 26-test legacy regression suite with the Core package on `PYTHONPATH`:

```sh
PYTHONPATH=../secondbrain-core python -m unittest -v \
  test_promote_worker.py test_dashboard_approval.py \
  test_http_approval.py test_runner_integration.py
```

`production-compose.patch` and `production-plugin-route.patch` are historical Security-1D candidates only. They describe the superseded separate Worker/container and cross-container queue design; neither was applied. Do not use them for deployment.

The Core HTTP tests simulate Hermes' verified `request.state.session` contract. They do not prove that the production Hermes plugin receives the same trusted context or that filesystem permissions isolate Core approval state from ordinary Hermes tools. Production integration remains BLOCKED until those host boundaries are evidenced.
