# Historical benchmarks and one-off experiments

This directory is for historical, reproducible synthetic evaluation assets, not the live project baseline or ordinary unit-test suite.

| Folder | Scope | Status |
|---|---|---|
| [d076-siliconflow-multimodal](d076-siliconflow-multimodal/README.md) | D076 Organizer / multimodal benchmark, seven synthetic fixtures, reference answers and historical provider results | Historical evaluation; model prices and availability are time-bound |
| [d077-hermes-live](d077-hermes-live/README.md) | One-off D077 Hermes live API / memory-learning evaluation runner | Archived experiment; no automatic execution |

The canonical delivery state and NEXT are in `../baseline/00-CURRENT.md`; approved design and decisions remain under `../baseline/`. Core's maintained automated tests stay under `web-app/secondbrain-core/tests/`; GitHub Actions definitions stay under `.github/workflows/`.

**No test here is permission to call a model.** Never trigger paid or data-egress experiments merely to validate this documentation relocation. Preserve historical conclusions as dated evidence, not current model recommendations.
