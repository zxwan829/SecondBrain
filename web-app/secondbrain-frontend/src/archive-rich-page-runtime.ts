/** Native-resource UX from BlockSuite-Editor@b25a75d9. No storage or mock backend. */
import { getInternalStoreExtensions } from '@blocksuite/affine/extensions/store';
import { getInternalViewExtensions } from '@blocksuite/affine/extensions/view';
import { StoreExtensionManager, ViewExtensionManager } from '@blocksuite/affine-ext-loader';
import type { BlockStdScope } from '@blocksuite/std';
import type { ViewScope } from '@blocksuite/affine-ext-loader';
import { ChineseSlashEmojiExtension } from './chinese-slash-emoji';
import { DesktopPageLeadingPlusExtension } from './desktop-page-plus';
import { CanvasRefPlusExtension, CanvasRefSlashExtension } from './canvas-ref-commands';
import { CanvasRefStoreExtension, CanvasRefViewExtension, CANVAS_REF_CREATE_EVENT, CANVAS_REF_OPEN_EVENT,
  CANVAS_REF_COPY_EVENT, CANVAS_REF_DELETE_EVENT, CANVAS_REF_RESIZE_EVENT, CANVAS_REF_FLAVOUR } from './canvas-ref-block';
import { cropReferencedFramesToContent } from './canvas-commands';
import { expandTableAreaToMergeClosure, type TableArea } from './table-commands';
import { weightedCellOffset } from './table-pointer-geometry';
import { getVisibleTableRowResizeTarget } from './table-row-boundary';
import './archive-rich-page.css';
import './archive-canvas-cards.css';

// Foundation's provider owns effects. Never call std effects independently.
// The same imported provider classes retain their official static once flags
// when the plain-Markdown subset manager is also used in the application.
export const archiveStoreManager = new StoreExtensionManager([...getInternalStoreExtensions(), CanvasRefStoreExtension]);
export const archiveViewManager = new ViewExtensionManager([...getInternalViewExtensions(), CanvasRefViewExtension]);
const archiveViewCache = new Map<ViewScope, readonly unknown[]>();
export function archiveViewExtensions(scope: ViewScope) {
  let extensions = archiveViewCache.get(scope);
  if (!extensions) {
    const base = archiveViewManager.get(scope);
    extensions = scope === 'page'
      ? [...base, ChineseSlashEmojiExtension, CanvasRefSlashExtension, CanvasRefPlusExtension, DesktopPageLeadingPlusExtension]
      : [...base];
    archiveViewCache.set(scope, extensions);
  }
  return [...extensions] as ReturnType<typeof archiveViewManager.get>;
}
export function archiveManagers() { return { stores: archiveStoreManager, views: { get: archiveViewExtensions } }; }

export type ArchiveCanvasEvent = { blockId: string; resourceId?: string; docId?: string; title?: string; width?: number; height?: number };
export type ArchiveTableSelection = { tableId: string; rows: string[]; columns: string[]; area: TableArea; label: string };
export type ArchiveSurfaceCallbacks = {
  onStatus?: (message: string) => void;
  onTableSelection?: (selection: ArchiveTableSelection | null, table: any) => void;
  onEmoji?: (modelId: string) => void;
  onCanvasCreate?: (detail: ArchiveCanvasEvent) => void | Promise<void>;
  onCanvasOpen?: (detail: ArchiveCanvasEvent) => void | Promise<void>;
  onCanvasCopy?: (detail: ArchiveCanvasEvent) => void | Promise<void>;
  onCanvasRemoveReference?: (detail: ArchiveCanvasEvent) => void | Promise<void>;
  onCanvasResize?: (detail: ArchiveCanvasEvent) => void | Promise<void>;
  onEmbeddedCanvasOpen?: (frameId: string) => void;
};

/** Bind only to this native editor's viewport. Returns complete listener cleanup. */
export function bindArchiveSurface(viewport: HTMLElement, std: BlockStdScope, options: ArchiveSurfaceCallbacks = {}) {
  const store: any = std.store;
  const state: { table: any; selection: ArchiveTableSelection | null } = { table: null, selection: null };
  const setSelection = (selection: ArchiveTableSelection | null) => {
    state.selection = selection; options.onTableSelection?.(selection, state.table);
  };
  const cleanups: Array<() => void> = [];
  const listen = (name: string, callback: EventListener, capture = true) => {
    viewport.addEventListener(name, callback, capture);
    cleanups.push(() => viewport.removeEventListener(name, callback, capture));
  };
  const surface = viewport.closest<HTMLElement>('.sb-archive-surface') ?? viewport;
  surface.classList.add('sb-archive-surface');
  const onEmbeddedCanvasDoubleClick = (event: MouseEvent) => {
    const reference = event.composedPath().find((node): node is HTMLElement => node instanceof HTMLElement && node.localName === 'affine-surface-ref');
    const model = reference?.dataset.blockId ? store.getBlock(reference.dataset.blockId)?.model : null;
    if (!model?.props.reference || !options.onEmbeddedCanvasOpen) return;
    event.preventDefault(); event.stopPropagation(); options.onEmbeddedCanvasOpen(model.props.reference);
  };
  listen('dblclick', onEmbeddedCanvasDoubleClick as EventListener);
            const onTab = (event: KeyboardEvent) => {
              if (store.readonly || event.key !== 'Tab' || event.isComposing || event.keyCode === 229) return;
              const target = event.target;
              if (!(target instanceof Element)) return;
              const td = target.closest<HTMLTableCellElement>('td[data-row-id][data-column-id]');
              const table = td?.closest<any>('affine-table'); const manager = table?.dataManager;
              if (!td || !manager) return;
              const rows = manager.rows$.value; const columns = manager.columns$.value;
              const ri = rows.findIndex((r: any)=>r.rowId===td.dataset.rowId); const ci=columns.findIndex((c:any)=>c.columnId===td.dataset.columnId);
              if(ri<0||ci<0)return;let nr=ri,nc=ci+(event.shiftKey?-1:1);if(nc>=columns.length){nc=0;nr++;}if(nc<0){nc=columns.length-1;nr--;}
              event.preventDefault();event.stopImmediatePropagation();if(nr>=rows.length&&!event.shiftKey)manager.addRow(rows.length-1);else if(nr<0)return;
              requestAnimationFrame(()=>{const row=manager.rows$.value[nr];const col=columns[nc];const nextCell=viewport.querySelector<HTMLTableCellElement>(`td[data-row-id="${row?.rowId}"][data-column-id="${col?.columnId}"]`);nextCell?.click();});
            };

            let dragStart:{x:number;y:number;rowId:string;columnId:string;table:any}|undefined;
            let lastDragged:{tableId:string;area:TableArea}|undefined;
            let resizing:{tr:HTMLTableRowElement;rowId:string;table:any;startY:number;startHeight:number;nextHeight:number}|undefined;
            const cellFromEvent=(event:Event)=>event.composedPath().find((node):node is HTMLTableCellElement=>node instanceof HTMLTableCellElement&&node.matches('td[data-row-id][data-column-id]'));
            const tableFromEvent=(event:Event)=>event.composedPath().find((node):node is HTMLElement=>node instanceof HTMLElement&&node.tagName.toLowerCase()==='affine-table') as any;
            // A merged TD exposes only its anchor IDs. Resolve the pointer position
            // within its rendered span back to the covered row/column so a drag can
            // include adjacent or enclosing merge regions without deleting cells.
            const cellAtPoint=(table:any,td:HTMLTableCellElement,x:number,y:number)=>{
              const rows=table.dataManager?.rows$?.value??[],columns=table.dataManager?.columns$?.value??[];
              const rowIndex=rows.findIndex((row:any)=>row.rowId===td.dataset.rowId),columnIndex=columns.findIndex((column:any)=>column.columnId===td.dataset.columnId);
              if(rowIndex<0||columnIndex<0)return undefined;
              const rect=td.getBoundingClientRect(),rowSpan=Math.max(1,td.rowSpan||1),columnSpan=Math.max(1,td.colSpan||1);
              const renderedRows=Array.from(table.querySelectorAll('tr[data-row-id]')) as HTMLTableRowElement[];
              const renderedCells=Array.from(table.querySelectorAll('td[data-column-id]')) as HTMLTableCellElement[];
              const columnWidths=columns.slice(columnIndex,columnIndex+columnSpan).map((column:any)=>{
                const cell=renderedCells.find(item=>item.dataset.columnId===column.columnId&&item.colSpan===1);
                return Math.max(1,cell?.getBoundingClientRect().width??column.width??120);
              });
              const rowHeights=rows.slice(rowIndex,rowIndex+rowSpan).map((row:any)=>{
                const tr=renderedRows.find(item=>item.dataset.rowId===row.rowId);
                return Math.max(1,tr?.getBoundingClientRect().height??row.minHeight??(rect.height/rowSpan));
              });
              const targetRow=rowIndex+weightedCellOffset(y-rect.top,rect.height,rowHeights);
              const targetColumn=columnIndex+weightedCellOffset(x-rect.left,rect.width,columnWidths);
              return {rowId:rows[targetRow]?.rowId,columnId:columns[targetColumn]?.columnId};
            };
            const readSelection=(table:any,forced?:TableArea,focusedCell?:HTMLTableCellElement)=>{
              const tableId=table?.dataset?.blockId as string|undefined;
              if(!tableId)return;
              const rows=table.dataManager?.rows$?.value??[],columns=table.dataManager?.columns$?.value??[];
              let area:TableArea|undefined=forced??table.selectionController?.getSelected?.();
              if(area?.type!=='area'){
                const td=focusedCell??table.querySelector('td[data-row-id][data-column-id]:focus-within');
                const rowIndex=rows.findIndex((row:any)=>row.rowId===td?.dataset.rowId),columnIndex=columns.findIndex((column:any)=>column.columnId===td?.dataset.columnId);
                if(rowIndex<0||columnIndex<0)return;
                area={type:'area',rowStartIndex:rowIndex,rowEndIndex:rowIndex,columnStartIndex:columnIndex,columnEndIndex:columnIndex};
                table.selectionController?.setSelected(area);
              }
              area=expandTableAreaToMergeClosure(area,rows.map((row:any)=>row.rowId),columns.map((column:any)=>column.columnId),table.dataManager?.model?.props?.mergeRegions??{});
              table.selectionController?.setSelected(area);
              const selectedRows=rows.slice(area.rowStartIndex,area.rowEndIndex+1).map((row:any)=>row.rowId);
              const selectedColumns=columns.slice(area.columnStartIndex,area.columnEndIndex+1).map((column:any)=>column.columnId);
              if(!selectedRows.length||!selectedColumns.length)return;
              state.table=table;
              setSelection({tableId,rows:selectedRows,columns:selectedColumns,area,label:`区域 ${selectedRows.length} 行 × ${selectedColumns.length} 列`});
            };
            const pointerDown=(event:Event)=>{
              const e=event as PointerEvent;if(store.readonly || e.button!==0)return;
              const table=tableFromEvent(e),td=cellFromEvent(e);
              // A row/column handle opens the menu for the existing area.
              // Do not discard it before the handle's click is dispatched.
              if(e.composedPath().some(node=>node instanceof Element&&node.matches('[data-testid="drag-row-handle"],[data-testid="drag-column-handle"]')))return;
              if(!td||!table)lastDragged=undefined;
              if(td&&table){
                // A plain click enters the cell for editing. Only a real pointer
                // drag creates an area selection and its context controls.
                setSelection(null);
                const point=cellAtPoint(table,td,e.clientX,e.clientY);lastDragged=undefined;
                if(point?.rowId&&point.columnId)dragStart={x:e.clientX,y:e.clientY,rowId:point.rowId,columnId:point.columnId,table};
              }
              const tr=table&&getVisibleTableRowResizeTarget(table,td,e.clientY);
              if(!tr||!table)return;
              const rect=tr.getBoundingClientRect();
              const rowId=tr.dataset.rowId;if(!rowId)return;
              e.preventDefault();e.stopPropagation();
              dragStart=undefined;
              resizing={tr,rowId,table,startY:e.clientY,startHeight:rect.height,nextHeight:rect.height};
              document.body.style.cursor='row-resize';
              (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
            };
            const pointerMove=(event:Event)=>{
              const e=event as PointerEvent;
              if(resizing){
                const height=Math.max(32,resizing.startHeight+e.clientY-resizing.startY);
                resizing.nextHeight=height;
                resizing.tr.style.height=`${height}px`;
                resizing.tr.querySelectorAll('td').forEach(td=>(td as HTMLElement).style.height=`${height}px`);
                return;
              }
              const table=tableFromEvent(e),td=cellFromEvent(e);
              (viewport as HTMLElement).style.cursor=table&&getVisibleTableRowResizeTarget(table,td,e.clientY)?'row-resize':'';
              if(!dragStart||!table||!td||table!==dragStart.table||!(e.buttons&1)||Math.hypot(e.clientX-dragStart.x,e.clientY-dragStart.y)<4)return;
              const rows=table.dataManager.rows$.value,columns=table.dataManager.columns$.value,endPoint=cellAtPoint(table,td,e.clientX,e.clientY);
              const r0=rows.findIndex((row:any)=>row.rowId===dragStart!.rowId),c0=columns.findIndex((column:any)=>column.columnId===dragStart!.columnId);
              const r1=rows.findIndex((row:any)=>row.rowId===endPoint?.rowId),c1=columns.findIndex((column:any)=>column.columnId===endPoint?.columnId);
              if(r0<0||c0<0||r1<0||c1<0)return;
              const area=expandTableAreaToMergeClosure({type:'area',rowStartIndex:Math.min(r0,r1),rowEndIndex:Math.max(r0,r1),columnStartIndex:Math.min(c0,c1),columnEndIndex:Math.max(c0,c1)},rows.map((row:any)=>row.rowId),columns.map((column:any)=>column.columnId),table.dataManager?.model?.props?.mergeRegions??{});
              table.selectionController?.setSelected(area);
              e.preventDefault();e.stopPropagation();
            };
            const pointerUp=(event:Event)=>{
              const e=event as PointerEvent;
              if(resizing){
                const {tr,rowId,table}=resizing;
                const height=Math.max(32,Math.round(resizing.nextHeight));
                const model=store?.getBlock(table.dataset.blockId)?.model;
                const row=model?.props.rows[rowId];
                if(row){store?.captureSync();store?.transact(()=>{row.minHeight=height;});store?.captureSync();options.onStatus?.(`TABLE ROW · 行边界已调整为 ${height}px；待保存。`);}
                tr.querySelectorAll('td').forEach(td=>(td as HTMLElement).style.removeProperty('height'));
                tr.style.removeProperty('height');resizing=undefined;dragStart=undefined;document.body.style.cursor='';
                return;
              }
              if(e.button!==0)return;
              const start=dragStart;dragStart=undefined;
              const endTable=tableFromEvent(e),end=cellFromEvent(e);
              if(!start||!endTable||!end||endTable.dataset.blockId!==start.table.dataset.blockId)return;
              if(Math.hypot(e.clientX-start.x,e.clientY-start.y)<4){
                const editor=end.querySelector<HTMLElement>('rich-text .inline-editor[contenteditable="true"]');
                if(editor)requestAnimationFrame(()=>{if(editor.isConnected)editor.focus({preventScroll:true});});
                return;
              }
              const table=start.table,rows=table.dataManager.rows$.value,columns=table.dataManager.columns$.value,endPoint=cellAtPoint(table,end,e.clientX,e.clientY);
              const r0=rows.findIndex((row:any)=>row.rowId===start.rowId),c0=columns.findIndex((column:any)=>column.columnId===start.columnId);
              const r1=rows.findIndex((row:any)=>row.rowId===endPoint?.rowId),c1=columns.findIndex((column:any)=>column.columnId===endPoint?.columnId);
              if(r0<0||c0<0||r1<0||c1<0)return;
              const area=expandTableAreaToMergeClosure({type:'area',rowStartIndex:Math.min(r0,r1),rowEndIndex:Math.max(r0,r1),columnStartIndex:Math.min(c0,c1),columnEndIndex:Math.max(c0,c1)},rows.map((row:any)=>row.rowId),columns.map((column:any)=>column.columnId),table.dataManager?.model?.props?.mergeRegions??{});
              const completedDrag={tableId:table.dataset.blockId,area};lastDragged=completedDrag;
              window.setTimeout(()=>{if(!table.isConnected||lastDragged!==completedDrag)return;table.selectionController?.setSelected(area);readSelection(table,area,end);},40);
            };
            const preventNativeMouseSelection=(event:MouseEvent)=>{
              if(dragStart&&(event.buttons&1)&&Math.hypot(event.clientX-dragStart.x,event.clientY-dragStart.y)>=4)event.stopPropagation();
            };
            const pointerCancel=()=>{
              if(resizing){
                resizing.tr.querySelectorAll('td').forEach(td=>(td as HTMLElement).style.removeProperty('height'));
                resizing.tr.style.removeProperty('height');resizing=undefined;document.body.style.cursor='';
              }
              dragStart=undefined;lastDragged=undefined;(viewport as HTMLElement).style.cursor='';
            };
            const restoreDraggedAreaOnContextMenu=(event:Event)=>{
              const table=tableFromEvent(event),td=cellFromEvent(event);
              if(!table||!td||!lastDragged||table.dataset.blockId!==lastDragged.tableId)return;
              const rows=table.dataManager.rows$.value,columns=table.dataManager.columns$.value;
              const ri=rows.findIndex((row:any)=>row.rowId===td.dataset.rowId),ci=columns.findIndex((column:any)=>column.columnId===td.dataset.columnId),area=lastDragged.area;
              if(ri>=area.rowStartIndex&&ri<=area.rowEndIndex&&ci>=area.columnStartIndex&&ci<=area.columnEndIndex){table.selectionController?.setSelected(area);readSelection(table,area,td);}
            };
            const restoreDraggedAreaOnHandle=(event:Event)=>{
              if(event.composedPath().some(node=>node instanceof Element&&node.matches('[data-testid="drag-row-handle"],[data-testid="drag-column-handle"]')))restoreDraggedAreaOnContextMenu(event);
            };
  listen('keydown', onTab as EventListener);
  listen('pointerdown', pointerDown);
  listen('pointerup', pointerUp);
  listen('pointermove', pointerMove);
  listen('mousemove', preventNativeMouseSelection as EventListener);
  listen('pointercancel', pointerCancel);
  listen('contextmenu', restoreDraggedAreaOnContextMenu);
  listen('click', restoreDraggedAreaOnHandle);
  const routeCanvas = (callback: ((detail: ArchiveCanvasEvent) => void | Promise<void>) | undefined) => (event: Event) => {
    const detail = (event as CustomEvent<ArchiveCanvasEvent>).detail;
    const model = detail?.blockId ? store.getBlock(detail.blockId)?.model : null;
    if (!model || model.flavour !== CANVAS_REF_FLAVOUR || !callback) return;
    event.stopPropagation();
    if (store.readonly && callback !== options.onCanvasOpen) return;
    Promise.resolve(callback(detail)).catch(() => options.onStatus?.('画布操作未完成；当前内容仍保留。'));
  };
  listen(CANVAS_REF_CREATE_EVENT, routeCanvas(options.onCanvasCreate));
  listen(CANVAS_REF_OPEN_EVENT, routeCanvas(options.onCanvasOpen));
  listen(CANVAS_REF_COPY_EVENT, routeCanvas(options.onCanvasCopy));
  listen(CANVAS_REF_DELETE_EVENT, routeCanvas(options.onCanvasRemoveReference));
  listen(CANVAS_REF_RESIZE_EVENT, routeCanvas(options.onCanvasResize));
  listen('sb-open-emoji-picker', ((event: CustomEvent<{ modelId: string }>) => {
    if (!store.readonly && store.getBlock(event.detail?.modelId)) options.onEmoji?.(event.detail.modelId);
  }) as EventListener);
  return {
    get tableSelection() { return state.selection; },
    get activeTable() { return state.table; },
    cropEmbeddedFrames() { return cropReferencedFramesToContent(std, store); },
    dispose() { pointerCancel(); cleanups.forEach(cleanup => cleanup()); },
  };
}
