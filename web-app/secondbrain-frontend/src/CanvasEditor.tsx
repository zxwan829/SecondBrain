import React, { useMemo, useRef } from 'react';
import { Excalidraw, serializeAsJSON } from '@excalidraw/excalidraw';

declare global {
  interface Window { EXCALIDRAW_ASSET_PATH?: string }
}

if (typeof window !== 'undefined') window.EXCALIDRAW_ASSET_PATH = '/assets/excalidraw';

export function CanvasEditor({ content, onChange }: { content: string; onChange: (content: string) => void }) {
  const initialData = useMemo(() => JSON.parse(content), []);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  return <div className="excalidraw-canvas" aria-label="自由画板编辑器">
    <Excalidraw
      initialData={initialData}
      onChange={(elements, appState, files) => {
        onChangeRef.current(serializeAsJSON(elements, appState, files, 'database'));
      }}
    />
  </div>;
}
