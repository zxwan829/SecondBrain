# D085-C1 — Local Notes navigation integration

## Scope and gates

D085-C1 connects the existing Notes page to the Web App sidebar, `/notes` route, refresh/deep-link handling, and the existing responsive mobile navigation. It does not change the Notes API or Core authorization policy.

Notes navigation is disabled unless the frontend build receives `VITE_ENABLE_NOTES=true`. The example configuration keeps it off by default. When enabled, the app first requests `GET /api/notes` with same-origin credentials; Core must authorize `notes.read` and return the configured collection list before navigation is shown. A denied or unavailable Core response keeps the item hidden and redirects a Notes deep link to `/`. Note reads and writes continue to use Core's existing `notes.read` and `notes.write` authorization checks. The frontend gate is a visibility and routing control, not an authorization boundary.

NotesPage and its editor dependencies are lazy-loaded so the normal route does not eagerly load the Notes editing bundle. Mobile navigation uses the existing shared sidebar, so it observes the same feature and Core gates.

Before the app shell changes pages or the browser history leaves `/notes`, NotesPage supplies a navigation guard to the shell. It blocks while any Notes write is in flight and asks before discarding unsaved Markdown or visual-asset edits. A declined browser back restores the Notes history entry. Core remains the authority for all read/write operations.

## Markdown and visual-asset boundary

Markdown remains the authoritative note body. Frontmatter, Obsidian wikilinks/embeds, and other unsupported syntax must remain protected by the editor's existing round-trip safeguards; this navigation integration does not reinterpret or migrate note content. Mindmap and Excalidraw JSON assets can be edited and reopened inside SecondBrain according to D085-B. Obsidian does not natively edit those JSON assets without a compatible plugin.

## Synthetic validation

Run from `web-app/secondbrain-frontend`:

```sh
npm ci
npm test -- src/App.navigation.test.tsx src/NotesPage.test.tsx src/MindMapEditor.test.tsx
npm run typecheck
npm run build
```

The navigation tests use mocked session and Notes API responses. They cover the default-off flag, Core 403/503 denial, successful desktop navigation, refresh/deep-link restoration, and opening Notes from the mobile menu. Existing Notes and mindmap tests cover the local synthetic editor/data flows. No real notes are read or written.

## Rollback and release state

Rollback is a source revert of the D085-C1 PR. The feature is default-off in the example configuration; production configuration is not changed by this work. C1 source/PR review does not imply deployment, runtime verification, or user acceptance. C2 is outside this change and remains unauthorized.
