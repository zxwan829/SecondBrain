import React, { lazy, Suspense, useEffect, useRef, useState } from 'react';
import type { VisualAsset, VisualKind } from './api/notes';

const MindMapEditor = lazy(() => import('./MindMapEditor').then((module) => ({ default: module.MindMapEditor })));
const CanvasEditor = lazy(() => import('./CanvasEditor').then((module) => ({ default: module.CanvasEditor })));

export function VisualAssetDialog({ kind, asset, onSave, onClose, onNavigationRiskChange, canSave = true }: {
  kind: VisualKind;
  asset: VisualAsset;
  onSave: (content: string) => Promise<void>;
  onClose: () => void;
  onNavigationRiskChange?: (risk: boolean) => void;
  canSave?: boolean;
}) {
  const [content, setContent] = useState(asset.content);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const savedContent = useRef(asset.content);
  const dirty = content !== savedContent.current;

  useEffect(() => {
    onNavigationRiskChange?.(dirty || saving);
    return () => onNavigationRiskChange?.(false);
  }, [dirty, onNavigationRiskChange, saving]);

  const close = () => {
    if (dirty && !window.confirm('图形有未保存的修改，仍要关闭吗？')) return;
    onClose();
  };
  const save = async () => {
    setSaving(true); setError('');
    try {
      await onSave(content);
      savedContent.current = content;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '图形保存失败；修改仍保留在编辑器中。');
    } finally { setSaving(false); }
  };

  return <div className="visual-dialog-backdrop">
    <section role="dialog" aria-modal="true" aria-label={kind === 'mindmap' ? '思维导图' : '自由画板'} className="visual-dialog">
      <header className="visual-dialog-header">
        <h2>{kind === 'mindmap' ? '思维导图' : '自由画板'}</h2>
        <span>{asset.filename}</span>
        <button type="button" onClick={close} disabled={saving}>关闭</button>
      </header>
      {error && <p role="alert" className="notes-error">{error}</p>}
      <Suspense fallback={<p role="status">正在加载图形编辑器…</p>}>
        {kind === 'mindmap'
          ? <MindMapEditor content={asset.content} onChange={setContent} />
          : <CanvasEditor content={asset.content} onChange={setContent} />}
      </Suspense>
      <footer className="visual-dialog-footer">
        <span role="status">{saving ? '保存中…' : dirty ? '有未保存修改' : '已保存'}</span>
        <button type="button" onClick={() => void save()} disabled={saving || !dirty || !canSave}>保存图形</button>
      </footer>
    </section>
  </div>;
}
