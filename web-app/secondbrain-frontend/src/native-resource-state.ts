import * as Y from 'yjs';
import type { BlockSuiteResourceWrite } from './api/notes';
import { archiveManagers } from './archive-rich-page-runtime';
import { TransientMarkdownWorkspace } from './transient-blocksuite-workspace';
import { CANVAS_REF_FLAVOUR } from './canvas-ref-block';

export const richPagePropertiesMap = 'secondbrain-rich-page-properties';
export function nativeResourceSnapshot(store: any): Record<string, unknown> {
  const raw = store.getTransformer().docToSnapshot(store);
  if (!raw || typeof raw !== 'object') throw new Error('原生资源快照导出失败；未继续保存');
  const snapshot = JSON.parse(JSON.stringify(raw));
  const properties = store.spaceDoc.getMap(richPagePropertiesMap).toJSON();
  if (Object.keys(properties).length) snapshot.secondbrainRichPage = { properties };
  return snapshot;
}
export function nativeResourceBase64(bytes: Uint8Array): string {
  let binary = ''; for (const byte of bytes) binary += String.fromCharCode(byte); return btoa(binary);
}
/** Clone in a fresh transient document; never change the editing session in place. */
export function remapNativeResourceReferences(payload: BlockSuiteResourceWrite, mapping: Map<string, string>): BlockSuiteResourceWrite {
  const workspace = new TransientMarkdownWorkspace();
  try {
    workspace.storeExtensions = archiveManagers().stores.get('store');
    workspace.meta.initialize();
    const doc = workspace.createDoc(payload.docId);
    const binary = atob(payload.updateB64);
    Y.applyUpdate(doc.spaceDoc, Uint8Array.from(binary, value => value.charCodeAt(0)));
    doc.load();
    const store = doc.getStore();
    for (const { model } of store.getBlocksByFlavour(CANVAS_REF_FLAVOUR)) {
      const id = (model.props as any).resourceId as string;
      if (!mapping.has(id)) throw new Error('画布深拷贝引用映射不完整；原件未改变');
      store.updateBlock(model, { resourceId: mapping.get(id), revision: '', previewJson: '[]' });
    }
    return { ...payload, snapshot: nativeResourceSnapshot(store), updateB64: nativeResourceBase64(Y.encodeStateAsUpdate(doc.spaceDoc)) };
  } finally { workspace.dispose(); }
}
