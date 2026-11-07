import { KeyboardToolbarConfigExtension, defaultKeyboardToolbarConfig } from '@blocksuite/affine-widget-keyboard-toolbar';
import { SlashMenuConfigExtension } from '@blocksuite/affine-widget-slash-menu';
import { getSelectedModelsCommand } from '@blocksuite/affine-shared/commands';
import { FrameIcon } from '@blocksuite/icons/lit';
import { BlockSelection } from '@blocksuite/std';
import {
  CANVAS_REF_CREATE_EVENT,
  CANVAS_REF_FLAVOUR,
} from './canvas-ref-block';

const CANVAS_LABEL = '新建画布';
const CANVAS_GROUP = '5_画布';

export function insertCanvasRefAfter(std: any, model: any) {
  if (!model || !std?.store?.getParent(model)) return;
  const existing = std.store.getBlocksByFlavour(CANVAS_REF_FLAVOUR);
  const title = `独立画布 ${existing.length + 1}`;
  // Core assigns the actual resource ID; this temporary block is not a resource.
  const resourceId = '';
  const docId = '';
  const [blockId] = std.store.addSiblingBlocks(model, [{
    flavour: CANVAS_REF_FLAVOUR,
    resourceId,
    docId,
    title,
    state: 'creating',
    revision: '',
    previewJson: '[]',
    error: '',
  }], 'after');
  if (!blockId) return;

  if (model.flavour === 'affine:paragraph' && model.text?.length === 0) {
    std.store.deleteBlock(model);
  }
  std.selection.set([std.selection.create(BlockSelection, { blockId })]);
  (std.host as HTMLElement).dispatchEvent(new CustomEvent(CANVAS_REF_CREATE_EVENT, {
    bubbles: true, composed: true, detail: { blockId, resourceId, docId, title },
  }));
}

/**
 * The Page leading plus opens BlockSuite's SlashMenu registry directly
 * (see DesktopPageLeadingPlusExtension). Keep the label, discovery terms,
 * icon and command body here so the Slash entry and the keyboard toolbar
 * shortcut cannot drift into different canvas creation behavior.
 */
const canvasRefCommand = {
  name: CANVAS_LABEL,
  description: '在正文中插入独立、可编辑的内嵌画布',
  searchAlias: ['画布', '白板', '线框图', '思维导图'],
  icon: FrameIcon(),
  group: `${CANVAS_GROUP}@0` as `${number}_${string}@${number}`,
  action: ({ std, model }: { std: any; model: any }) => insertCanvasRefAfter(std, model),
};

export const CanvasRefSlashExtension = SlashMenuConfigExtension(
  'secondbrain-canvas-ref-slash',
  { items: [canvasRefCommand] }
);

function insertCanvasRefFromSelection(std: any) {
  const [, result] = std.command.exec(getSelectedModelsCommand);
  insertCanvasRefAfter(std, result?.selectedModels?.[0]);
}

// This is an additional contextual-toolbar shortcut. The desktop row-leading
// plus is intentionally not implemented here: it displays the full native
// SlashMenu registry, including the item above and all built-in commands.
const plusItem = {
  ...canvasRefCommand,
  action: ({ std }: { std: any }) => {
    insertCanvasRefFromSelection(std);
  },
};

const morePanel = defaultKeyboardToolbarConfig.items[0] as {
  icon: unknown;
  activeIcon?: unknown;
  activeBackground?: string;
  groups: any[];
};

export const CanvasRefPlusExtension = KeyboardToolbarConfigExtension({
  items: [
    {
      ...morePanel,
      groups: [...morePanel.groups, { name: '画布', items: [plusItem] }],
    },
    ...defaultKeyboardToolbarConfig.items.slice(1),
  ] as any,
});
