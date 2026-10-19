import React, { useEffect, useRef, useState } from 'react';
import type { MindMapInstance, MindMapTree } from 'simple-mind-map';
import 'simple-mind-map/dist/simpleMindMap.esm.min.css';

const isRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value);

export function MindMapEditor({ content, onChange }: { content: string; onChange: (content: string) => void }) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MindMapInstance | null>(null);
  const initial = useRef(content);
  const onChangeRef = useRef(onChange);
  const [error, setError] = useState('');
  onChangeRef.current = onChange;

  useEffect(() => {
    let cancelled = false;
    let instance: MindMapInstance | null = null;
    let capture: (() => void) | null = null;
    void Promise.all([import('simple-mind-map'), import('simple-mind-map/src/plugins/Drag.js')]).then(([{ default: MindMap }, { default: Drag }]) => {
      if (cancelled || !container.current) return;
      const parsed = JSON.parse(initial.current) as Record<string, unknown>;
      // getData(true) returns { layout, root, theme, view }; older default
      // assets used the node tree directly. Accept both persisted shapes.
      const root = (parsed.root ?? parsed) as MindMapTree;
      if (!root || typeof root.data?.text !== 'string' || !Array.isArray(root.children)) {
        throw new Error('脑图源文件结构无效。');
      }
      const theme = typeof parsed.theme === 'string'
        ? parsed.theme
        : parsed.theme && typeof parsed.theme === 'object' && 'template' in parsed.theme && typeof parsed.theme.template === 'string'
          ? parsed.theme.template
          : 'default';
      const rawThemeConfig = isRecord(parsed.theme) ? parsed.theme.config : undefined;
      const themeConfig = isRecord(rawThemeConfig) ? rawThemeConfig : undefined;
      MindMap.usePlugin(Drag);
      instance = new MindMap({
        el: container.current,
        data: root,
        layout: typeof parsed.layout === 'string' ? parsed.layout : 'mindMap',
        theme,
        // simple-mind-map 0.14.0-fix.3 deep-merges explicitly supplied
        // undefined over its default `{}` and crashes in Object.keys.
        ...(themeConfig ? { themeConfig } : {}),
        fit: true,
      });
      const view = (instance as MindMapInstance & { view?: { setTransformData: (data: unknown) => void } }).view;
      // Older or partially-written visual assets can contain a truthy but
      // incomplete view object. The library reads view.state with Object.keys;
      // skip optional viewport restoration unless both parts are records.
      if (isRecord(parsed.view) && isRecord(parsed.view.state) && isRecord(parsed.view.transform) && view) {
        view.setTransformData(parsed.view);
      }
      mapRef.current = instance;
      capture = () => {
        if (mapRef.current === instance) onChangeRef.current(JSON.stringify(instance?.getData(true), null, 2));
      };
      // The library's built-in Drag plugin emits node_dragend for both parent
      // changes and sibling reordering; data_change_detail covers text edits.
      instance.on('data_change_detail', capture);
      instance.on('node_dragend', capture);
      setError('');
    }).catch((reason: unknown) => {
      if (instance) {
        if (capture) {
          instance.off('data_change_detail', capture);
          instance.off('node_dragend', capture);
          capture = null;
        }
        instance.destroy();
        if (mapRef.current === instance) mapRef.current = null;
        instance = null;
      }
      if (!cancelled) setError(reason instanceof Error ? reason.message : '脑图组件加载失败。');
    });
    const observer = typeof ResizeObserver === 'undefined' || !container.current ? null : new ResizeObserver(() => mapRef.current?.resize());
    if (container.current) observer?.observe(container.current);
    return () => {
      cancelled = true;
      observer?.disconnect();
      if (instance) {
        if (capture) {
          instance.off('data_change_detail', capture);
          instance.off('node_dragend', capture);
        }
        instance.destroy();
      }
      if (mapRef.current === instance) mapRef.current = null;
    };
  }, []);

  const command = (name: string) => mapRef.current?.execCommand(name);
  return <section className="visual-map-editor" aria-label="思维导图编辑器">
    <div className="visual-toolbar" role="toolbar" aria-label="思维导图工具">
      <button type="button" onClick={() => command('INSERT_CHILD_NODE')}>添加子节点</button>
      <button type="button" onClick={() => command('INSERT_NODE')}>添加同级节点</button>
      <button type="button" onClick={() => command('REMOVE_NODE')}>删除节点</button>
      <button type="button" onClick={() => command('BACK')}>撤销</button>
      <button type="button" onClick={() => command('FORWARD')}>重做</button>
      <span>双击节点编辑文字；拖动节点可调整父子层级或同级顺序。</span>
    </div>
    {error && <p className="notes-error" role="alert">{error}</p>}
    <div ref={container} className="mind-map-canvas" aria-label="脑图画布" />
  </section>;
}
