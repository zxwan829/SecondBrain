# BlockSuite archive dependency preparation

This is an explicit, isolated preparation checkpoint. `npm postinstall` still runs only the existing Zod security compatibility patch. Nothing here enables archived UI by default, changes Core persistence, or authorizes a release.

Source: `zxwan829/BlockSuite-Editor@b25a75d9a3c474614c79f24ac5396c317e02bf8f`. `archive-manifest.json` records the original and adapted SHA-256 for all 22 scripts.

Run `npm run prepare:archive-ux` only in an isolated integration checkout. It first checks BlockSuite 0.22.4 package versions, runs the existing Zod 4.6.6 compatibility fix, verifies the 29 data-view source overlays and patch payload hashes, and applies all 22 scripts. All data-view changes target the single installed package; no second vendored runtime module is introduced.

Compatibility adaptations:

- Database vendor targets are redirected to the installed `@blocksuite/data-view`; the archive source deltas are retained as hash-checked overlay payloads.
- Existing Zod union-optional security compatibility replaces the identical archived adjustment; its version remains 4.6.6.
- The standalone `src/main.tsx` duplicate-mount rewrite is not applied to SecondBrain: integrated editors render and append hosts without that standalone `std.mount()` sequence. The viewport hit-test correction is retained.
- Text-align patch checks its already-applied replacement before searching insertion anchors, fixing a repeated `textAlign` insertion on replay.
- Native keyboard Slash menus inherit a resource modal layer above its backdrop; the plus-widget route already did this.
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

## Native Slash menu Chromium diagnosis (2026-11-08)

- Independent standalone Linux Chromium probe [Actions #42450850978](https://github.com/zxwan829/SecondBrain/actions/runs/42450850978), source SHA `104342a625106199b01264ca8f391ee57cd2f06c`, confirmed the actual keyboard `/` route on a rich paragraph: Y.Text ended in `/` (length 46), logical inline range was collapsed at index 46, native selection stayed inside the inline editor, and the browser Range measured 17px high. The resource backdrop was z-index 12000; the native popover inherited 12001 and its panel measured 280×390 at x=568.5/y=476.1.
- The emoji command existed in the scrollable menu but its initial item box was at y=1484, outside the panel viewport. Scrolling the command into view moved its box to y=649 with size 264×44. The formal E2E now performs that scroll before asserting visibility, then retains the keyboard-triggered picker/search/insertion assertions. This was an E2E visibility assumption, alongside the real native-route modal stacking-layer defect; the native plus route is not used as a substitute.
- This diagnostic used an isolated Core/Vite fixture and standalone Playwright, did not invoke the synthetic CI runner, and did not produce formal acceptance artifacts. Formal archive UX Chromium gate on the final candidate: pending.

## Checkpoint validation

- Isolated install and explicit preparation: PASS.
- Replay after the text-align idempotence fix: PASS, zero modified installed BlockSuite TS/JS files.
- Frontend typecheck after preparation: PASS.
- Production build: PASS after archive preparation/typecheck/build on the source candidate before the standalone DOM probes. Full archived UX interactions, formal Linux Chromium acceptance on the final candidate, independent review and release eligibility: pending.
- No NAS, real Vault, model calls or production data used.
