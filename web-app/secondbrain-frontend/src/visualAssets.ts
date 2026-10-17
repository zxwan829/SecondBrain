import type { VisualKind } from './api/notes';

export const defaultMindMap = () => JSON.stringify({
  data: { text: '中心主题' },
  children: [],
  layout: 'mindMap',
  theme: 'default',
}, null, 2);

export const defaultExcalidraw = () => JSON.stringify({
  type: 'excalidraw',
  version: 2,
  source: 'secondbrain',
  elements: [],
  appState: { viewBackgroundColor: '#ffffff', gridSize: null },
}, null, 2);

export function visualKindFromFilename(filename: string): VisualKind | null {
  if (/^[0-9a-f]{32}\.mindmap\.json$/.test(filename)) return 'mindmap';
  if (/^[0-9a-f]{32}\.excalidraw\.json$/.test(filename)) return 'excalidraw';
  return null;
}

export const visualLink = (kind: VisualKind, filename: string) =>
  `[${kind === 'mindmap' ? '思维导图' : '自由画板'}](attachments/${filename})`;
