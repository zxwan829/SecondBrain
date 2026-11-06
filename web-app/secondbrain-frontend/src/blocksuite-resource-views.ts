import { ViewExtensionManager } from '@blocksuite/affine-ext-loader';
import { effects as registerStdEffects } from '@blocksuite/std/effects';
import { FoundationViewExtension } from '@blocksuite/affine-foundation/view';
import { RootViewExtension } from '@blocksuite/affine-block-root/view';
import { NoteViewExtension } from '@blocksuite/affine-block-note/view';
import { ParagraphViewExtension } from '@blocksuite/affine-block-paragraph/view';
import { ListViewExtension } from '@blocksuite/affine-block-list/view';
import { CodeBlockViewExtension } from '@blocksuite/affine-block-code/view';
import { TableViewExtension } from '@blocksuite/affine-block-table/view';
import { DividerViewExtension } from '@blocksuite/affine-block-divider/view';
import { InlinePresetViewExtension } from '@blocksuite/affine-inline-preset/view';
import { LatexViewExtension } from '@blocksuite/affine-inline-latex/view';
import { FootnoteViewExtension } from '@blocksuite/affine-inline-footnote/view';
import { LinkViewExtension } from '@blocksuite/affine-inline-link/view';
import { MentionViewExtension } from '@blocksuite/affine-inline-mention/view';
import { ReferenceViewExtension } from '@blocksuite/affine-inline-reference/view';
import { SurfaceViewExtension } from '@blocksuite/affine-block-surface/view';
import { DataViewViewExtension } from '@blocksuite/affine-block-data-view/view';
import { DatabaseViewExtension } from '@blocksuite/affine-block-database/view';
import { ImageViewExtension } from '@blocksuite/affine-block-image/view';
import { EdgelessTextViewExtension } from '@blocksuite/affine-block-edgeless-text/view';
import { BrushViewExtension } from '@blocksuite/affine-gfx-brush/view';
import { ConnectorViewExtension } from '@blocksuite/affine-gfx-connector/view';
import { GroupViewExtension } from '@blocksuite/affine-gfx-group/view';
import { MindmapViewExtension } from '@blocksuite/affine-gfx-mindmap/view';
import { PointerViewExtension } from '@blocksuite/affine-gfx-pointer/view';
import { ShapeViewExtension } from '@blocksuite/affine-gfx-shape/view';
import { TextViewExtension as GfxTextViewExtension } from '@blocksuite/affine-gfx-text/view';
import { EdgelessAutoConnectViewExtension } from '@blocksuite/affine-widget-edgeless-auto-connect/view';
import { EdgelessDraggingAreaViewExtension } from '@blocksuite/affine-widget-edgeless-dragging-area/view';
import { EdgelessSelectedRectViewExtension } from '@blocksuite/affine-widget-edgeless-selected-rect/view';
import { EdgelessToolbarViewExtension } from '@blocksuite/affine-widget-edgeless-toolbar/view';
import { EdgelessZoomToolbarViewExtension } from '@blocksuite/affine-widget-edgeless-zoom-toolbar/view';
import { FrameTitleViewExtension } from '@blocksuite/affine-widget-frame-title/view';
import { KeyboardToolbarViewExtension } from '@blocksuite/affine-widget-keyboard-toolbar/view';
import { NoteSlicerViewExtension } from '@blocksuite/affine-widget-note-slicer/view';
import { RemoteSelectionViewExtension } from '@blocksuite/affine-widget-remote-selection/view';
import { ViewportOverlayViewExtension } from '@blocksuite/affine-widget-viewport-overlay/view';

// ViewExtensionProvider.effectRan is static per provider class. All scopes must
// come from one manager so elements/effects register once in the running app.
const providers = [
  FoundationViewExtension, RootViewExtension, NoteViewExtension, ParagraphViewExtension,
  ListViewExtension, CodeBlockViewExtension, TableViewExtension, DividerViewExtension,
  InlinePresetViewExtension, LatexViewExtension, FootnoteViewExtension, LinkViewExtension,
  MentionViewExtension, ReferenceViewExtension, SurfaceViewExtension, DataViewViewExtension,
  DatabaseViewExtension, ImageViewExtension, EdgelessTextViewExtension, BrushViewExtension,
  ConnectorViewExtension, GroupViewExtension, MindmapViewExtension, PointerViewExtension,
  ShapeViewExtension, GfxTextViewExtension, EdgelessAutoConnectViewExtension,
  EdgelessDraggingAreaViewExtension, EdgelessSelectedRectViewExtension,
  EdgelessToolbarViewExtension, EdgelessZoomToolbarViewExtension, FrameTitleViewExtension,
  KeyboardToolbarViewExtension, NoteSlicerViewExtension, RemoteSelectionViewExtension,
  ViewportOverlayViewExtension,
];

registerStdEffects();
// Some eagerly loaded BlockSuite surfaces register their Lit elements before
// Notes creates its scope. ViewExtensionProvider tracks effects per class, so
// mark fully-present package anchors as already effected before each scope is
// built, while still running each provider's scope-specific setup.
const registeredEffectAnchors: Array<[typeof providers[number], string]> = [
  [FoundationViewExtension, 'icon-button'],
  [RootViewExtension, 'affine-page-root'],
  [NoteViewExtension, 'affine-note'],
  [ParagraphViewExtension, 'affine-paragraph'],
  [ListViewExtension, 'affine-list'],
  [CodeBlockViewExtension, 'affine-code'],
  [TableViewExtension, 'affine-table'],
  [DividerViewExtension, 'affine-divider'],
  [InlinePresetViewExtension, 'affine-text'],
  [LatexViewExtension, 'affine-latex'],
  [FootnoteViewExtension, 'affine-footnote-node'],
  [LinkViewExtension, 'link-popup'],
  [MentionViewExtension, 'affine-mention'],
  [ReferenceViewExtension, 'reference-popup'],
  [SurfaceViewExtension, 'affine-surface'],
  [DataViewViewExtension, 'affine-data-view'],
  [DatabaseViewExtension, 'affine-database'],
  [ImageViewExtension, 'affine-image'],
  [EdgelessTextViewExtension, 'affine-edgeless-text'],
  [BrushViewExtension, 'edgeless-eraser-tool-button'],
  [ConnectorViewExtension, 'edgeless-connector-tool-button'],
  [GroupViewExtension, 'edgeless-group-title-editor'],
  [MindmapViewExtension, 'edgeless-mindmap-tool-button'],
  [PointerViewExtension, 'edgeless-default-tool-button'],
  [ShapeViewExtension, 'edgeless-shape-text-editor'],
  [GfxTextViewExtension, 'edgeless-text-editor'],
  [EdgelessAutoConnectViewExtension, 'affine-edgeless-auto-connect-widget'],
  [EdgelessDraggingAreaViewExtension, 'edgeless-dragging-area-rect'],
  [EdgelessSelectedRectViewExtension, 'edgeless-auto-complete'],
  [EdgelessToolbarViewExtension, 'edgeless-toolbar-button'],
  [EdgelessZoomToolbarViewExtension, 'edgeless-zoom-toolbar'],
  [FrameTitleViewExtension, 'affine-frame-title-editor'],
  [KeyboardToolbarViewExtension, 'affine-keyboard-tool-panel'],
  [NoteSlicerViewExtension, 'note-slicer'],
  [RemoteSelectionViewExtension, 'affine-edgeless-remote-selection-widget'],
  [ViewportOverlayViewExtension, 'affine-viewport-overlay-widget'],
];
export function prepareViewExtensions() {
  for (const [Provider, anchor] of registeredEffectAnchors) {
    if (customElements.get(anchor)) Provider.effectRan = true;
  }
}

export const markdownViewManager = new ViewExtensionManager(providers);
export const resourceViewManager = markdownViewManager;
