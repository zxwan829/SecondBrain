# BlockSuite archive dependency preparation

This is an explicit, isolated preparation checkpoint. `npm postinstall` still runs only the existing Zod security compatibility patch. Nothing here enables archived UI by default, changes Core persistence, or authorizes a release.

Source: `zxwan829/BlockSuite-Editor@b25a75d9a3c474614c79f24ac5396c317e02bf8f`. `archive-manifest.json` records the original and adapted SHA-256 for all 22 scripts.

Run `npm run prepare:archive-ux` only in an isolated integration checkout. It first checks BlockSuite 0.22.4 package versions, runs the existing Zod 4.6.6 compatibility fix, verifies the 29 data-view source overlays and patch payload hashes, and applies all 22 scripts. All data-view changes target the single installed package; no second vendored runtime module is introduced.

Compatibility adaptations:

- Database vendor targets are redirected to the installed `@blocksuite/data-view`; the archive source deltas are retained as hash-checked overlay payloads.
- Existing Zod union-optional security compatibility replaces the identical archived adjustment; its version remains 4.6.6.
- The standalone `src/main.tsx` duplicate-mount rewrite is not applied to SecondBrain: integrated editors render and append hosts without that standalone `std.mount()` sequence. The viewport hit-test correction is retained.
- Text-align patch checks its already-applied replacement before searching insertion anchors, fixing a repeated `textAlign` insertion on replay.
- Four pure helper modules retain their archive names because dependency imports use those stable paths.

## Required contract before activation

Alignment, row geometry and table merge metadata do not have a lossless ordinary Markdown representation in the current Notes contract. Do not connect or publish those editing affordances before the rich-page persistence decision recorded in Issue #46 comment 6693536344 and the full UI parity matrix are resolved. No sidecar, HTML authority, data migration, Core change or UI integration is included here.

## Included archive scripts

| # | Script | Evidence |
|---|---|---|
| 1 | `patches/apply-text-align.mjs` | Original and adapted digests in `archive-manifest.json` |
| 2 | `patches/apply-table-merge-regions.mjs` | Original and adapted digests in `archive-manifest.json` |
| 3 | `patches/apply-table-unified-menu.mjs` | Original and adapted digests in `archive-manifest.json` |
| 4 | `patches/apply-table-row-resize.mjs` | Original and adapted digests in `archive-manifest.json` |
| 5 | `patches/apply-slash-localization.mjs` | Original and adapted digests in `archive-manifest.json` |
| 6 | `patches/apply-mindmap-tab-edit.mjs` | Original and adapted digests in `archive-manifest.json` |
| 7 | `patches/apply-mindmap-hit-test.mjs` | Original and adapted digests in `archive-manifest.json` |
| 8 | `patches/apply-table-zh-labels.mjs` | Original and adapted digests in `archive-manifest.json` |
| 9 | `patches/apply-inline-toolbar-zh.mjs` | Original and adapted digests in `archive-manifest.json` |
| 10 | `patches/apply-paragraph-align-toolbar.mjs` | Original and adapted digests in `archive-manifest.json` |
| 11 | `patches/apply-selection-toolbar-zh.mjs` | Original and adapted digests in `archive-manifest.json` |
| 12 | `patches/apply-paragraph-placeholder-zh.mjs` | Original and adapted digests in `archive-manifest.json` |
| 13 | `patches/apply-paragraph-placeholder-alignment.mjs` | Original and adapted digests in `archive-manifest.json` |
| 14 | `patches/apply-database-localization.mjs` | Original and adapted digests in `archive-manifest.json` |
| 15 | `patches/apply-export-safety.mjs` | Original and adapted digests in `archive-manifest.json` |
| 16 | `patches/apply-database-cell-close-guard.mjs` | Original and adapted digests in `archive-manifest.json` |
| 17 | `patches/apply-canvas-template-search.mjs` | Original and adapted digests in `archive-manifest.json` |
| 18 | `patches/apply-database-toolbar-tooltips.mjs` | Original and adapted digests in `archive-manifest.json` |
| 19 | `patches/apply-database-menu-zh.mjs` | Original and adapted digests in `archive-manifest.json` |
| 20 | `patches/apply-heading-toggle-spacing.mjs` | Original and adapted digests in `archive-manifest.json` |
| 21 | `patches/apply-heading-list-prefix-guard.mjs` | Original and adapted digests in `archive-manifest.json` |
| 22 | `patches/apply-database-ux-localization.mjs` | Original and adapted digests in `archive-manifest.json` |

## Checkpoint validation

- Isolated install and explicit preparation: PASS.
- Replay after the text-align idempotence fix: PASS, zero modified installed BlockSuite TS/JS files.
- Frontend typecheck after preparation: PASS.
- Production build, full archived UX interactions, Linux Chromium, independent review and release eligibility: NOT RUN for this checkpoint.
- No NAS, real Vault, model calls or production data used.
