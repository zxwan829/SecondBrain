import { NoopLogger } from '@blocksuite/global/utils';
import { BlobEngine, MemoryBlobSource, type BlobSource } from '@blocksuite/sync';
import { AwarenessStore, StoreContainer } from '@blocksuite/store';
import { Awareness } from 'y-protocols/awareness.js';
import { Subject } from 'rxjs';
import * as Y from 'yjs';

/**
 * Minimal in-memory Workspace adapter for BlockSuite's Page view. It deliberately
 * has no DocSource, IndexedDB source, remote sync, or snapshot persistence. The
 * parent component serializes every edit back to Core Notes Markdown.
 */
export class TransientMarkdownWorkspace {
  readonly id = `sb-markdown-${crypto.randomUUID()}`;
  readonly doc = new Y.Doc({ guid: this.id });
  readonly idGenerator = () => crypto.randomUUID();
  readonly blobSync: BlobEngine;
  storeExtensions: any[] = [];
  readonly slots = { docListUpdated: new Subject<void>() };
  readonly docs = new Map<string, TransientMarkdownDoc>();
  readonly meta: any;

  constructor(blobSource?: BlobSource) {
    const workspace = this;
    const blobs = blobSource ?? new MemoryBlobSource();
    // Markdown projection workspaces never persist blobs. Resource workspaces
    // may inject a note-scoped Core BlobSource with immutable SHA-256 keys.
    if (!blobSource) blobs.readonly = true;
    this.blobSync = new BlobEngine(blobs, [], new NoopLogger());
    this.meta = {
      docMetaAdded: new Subject<string>(), docMetaRemoved: new Subject<string>(), docMetaUpdated: new Subject<void>(),
      properties: { tags: { options: [] } },
      get docMetas() { return [...workspace.docs.values()].map((doc) => ({ id: doc.id, title: '', tags: [], createDate: 0 })); },
      get docs() { return [...workspace.docs.values()].map((doc) => ({ id: doc.id })); },
      initialize() {},
      addDocMeta(meta: { id: string }) { workspace.meta.docMetaAdded.next(meta.id); workspace.meta.docMetaUpdated.next(); },
      getDocMeta(id: string) { return workspace.docs.has(id) ? { id, title: '', tags: [], createDate: 0 } : undefined; },
      setDocMeta() {},
      removeDocMeta(id: string) { workspace.meta.docMetaRemoved.next(id); workspace.meta.docMetaUpdated.next(); },
      setProperties() {},
    };
  }

  start() {}
  waitForSynced() { return Promise.resolve(); }
  forceStop() {}

  createDoc(id: string = this.idGenerator()) {
    if (this.docs.has(id)) throw new Error('Transient BlockSuite document already exists');
    const doc = new TransientMarkdownDoc(id, this);
    this.docs.set(id, doc);
    this.meta.docMetaAdded.next(id);
    this.meta.docMetaUpdated.next();
    return doc;
  }

  getDoc(id: string) { return this.docs.get(id) ?? null; }

  removeDoc(id: string) {
    const doc = this.docs.get(id);
    if (!doc) return;
    this.docs.delete(id);
    doc.dispose();
    this.meta.docMetaRemoved.next(id);
    this.meta.docMetaUpdated.next();
  }

  dispose() {
    for (const doc of [...this.docs.values()]) doc.dispose();
    this.docs.clear();
    this.blobSync.stop();
    this.doc.destroy();
  }
}

export class TransientMarkdownDoc {
  readonly rootDoc: Y.Doc;
  readonly spaceDoc: Y.Doc;
  readonly yBlocks: Y.Map<unknown>;
  readonly awarenessStore: AwarenessStore;
  private readonly stores = new Set<{ dispose: () => void }>();
  private readonly container: StoreContainer;
  private isLoaded = false;

  constructor(readonly id: string, readonly workspace: TransientMarkdownWorkspace) {
    this.rootDoc = workspace.doc;
    this.spaceDoc = new Y.Doc({ guid: id });
    this.rootDoc.getMap<Y.Doc>('spaces').set(id, this.spaceDoc);
    this.yBlocks = this.spaceDoc.getMap('blocks');
    this.awarenessStore = new AwarenessStore(new Awareness(this.spaceDoc));
    this.container = new StoreContainer(this as any);
  }

  get meta() { return this.workspace.meta.getDocMeta(this.id); }
  get ready() { return this.isLoaded; }
  get loaded() { return this.isLoaded; }

  load(init?: () => void) {
    if (!this.isLoaded) {
      this.spaceDoc.load();
      init?.();
      this.isLoaded = true;
    }
    return this;
  }

  getStore(options: any = {}) {
    const store = this.container.getStore({
      ...options,
      extensions: [...this.workspace.storeExtensions, ...(options.extensions ?? [])],
    });
    this.stores.add(store);
    return store;
  }

  removeStore(options: any) { this.container.removeStore(options); }
  clear() { this.yBlocks.clear(); }

  dispose() {
    for (const store of this.stores) store.dispose();
    this.stores.clear();
    this.awarenessStore.destroy();
    this.rootDoc.getMap('spaces').delete(this.id);
    this.spaceDoc.destroy();
    this.isLoaded = false;
  }

  remove() { this.workspace.removeDoc(this.id); }
}
