import { getInternalStoreExtensions } from '@blocksuite/affine/extensions/store';
import { StoreExtensionManager } from '@blocksuite/affine-ext-loader';
import { Text } from '@blocksuite/store';
import * as Y from 'yjs';
import type { BlockSuiteResourceWrite } from './api/notes';
import { TransientMarkdownWorkspace } from './transient-blocksuite-workspace';

const richPagePropertiesMap = 'secondbrain-rich-page-properties';
const storeManager = new StoreExtensionManager(getInternalStoreExtensions());
const base64 = (bytes: Uint8Array) => {
  let raw = '';
  for (const byte of bytes) raw += String.fromCharCode(byte);
  return btoa(raw);
};

/**
 * Build the real, minimal Page Yjs/snapshot payload without importing the
 * editor view, its canvas UI, or its CSS. The full editor can load while Core
 * persists this already-valid resource.
 */
export function createRichPageResourcePayload(): Omit<BlockSuiteResourceWrite, 'resourceId'> {
  const workspace = new TransientMarkdownWorkspace();
  try {
    workspace.storeExtensions = storeManager.get('store');
    workspace.meta.initialize();
    const docId = crypto.randomUUID();
    const doc = workspace.createDoc(docId).load();
    const store = doc.getStore();
    const root = store.addBlock('affine:page', {}, null);
    store.addBlock('affine:surface', {}, root, 0);
    store.spaceDoc.getMap(richPagePropertiesMap).set('docMode', 'page');
    const note = store.addBlock('affine:note', {}, root);
    store.addBlock('affine:paragraph', { type: 'h1', text: new Text('新建笔记') }, note);
    store.addBlock('affine:paragraph', { text: new Text('') }, note);

    const rawSnapshot = store.getTransformer().docToSnapshot(store);
    if (!rawSnapshot || typeof rawSnapshot !== 'object') throw new Error('BlockSuite 未能导出初始快照');
    const snapshot = JSON.parse(JSON.stringify(rawSnapshot)) as Record<string, unknown>;
    const properties = store.spaceDoc.getMap(richPagePropertiesMap).toJSON();
    if (Object.keys(properties).length) snapshot.secondbrainRichPage = { properties };
    return { schemaVersion: 1, resourceKind: 'rich-page', docId,
      updateB64: base64(Y.encodeStateAsUpdate(doc.spaceDoc)), snapshot };
  } finally {
    workspace.dispose();
  }
}
