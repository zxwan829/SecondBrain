import { EdgelessFrameManagerIdentifier } from '@blocksuite/affine-block-frame';
import { EdgelessCRUDExtension } from '@blocksuite/affine-block-surface';
import { insertSurfaceRefBlockCommand } from '@blocksuite/affine-block-surface-ref';
import { KeyboardToolbarConfigExtension, defaultKeyboardToolbarConfig } from '@blocksuite/affine-widget-keyboard-toolbar';
import { SlashMenuConfigExtension } from '@blocksuite/affine-widget-slash-menu';
import { getSelectedModelsCommand } from '@blocksuite/affine-shared/commands';
import { Bound } from '@blocksuite/global/gfx';
import { FrameIcon } from '@blocksuite/icons/lit';
import { BlockSelection } from '@blocksuite/std';
import { GfxControllerIdentifier } from '@blocksuite/std/gfx';

const CANVAS_LABEL = '新建画布';
const CANVAS_GROUP = '5_画布';

export function createCanvasAfter(std: any, model: any) {
  if (!model) return;
  const gfx = std.get(GfxControllerIdentifier);
  const frameManager = std.get(EdgelessFrameManagerIdentifier);
  const bound = Bound.fromXYWH([0, 0, 720, 440]);
  let occupied = gfx.grid.search(bound);
  while (occupied.length) {
    const rightmost = occupied.reduce((left: any, right: any) =>
      left.x + left.w > right.x + right.w ? left : right
    );
    bound.x = rightmost.x + rightmost.w + 48;
    occupied = gfx.grid.search(bound);
  }

  const frame = frameManager.createFrameOnBound(bound);
  frame.props.title.clear();
  frame.props.title.insert(CANVAS_LABEL, 0);
  const [, result] = std.command.exec(insertSurfaceRefBlockCommand, {
    reference: frame.id,
    place: 'after',
    removeEmptyLine: true,
    selectedModels: [model],
  });
  const blockId = result?.insertedSurfaceRefBlockId;
  if (!blockId) {
    std.store.deleteBlock(frame);
    return;
  }
  std.selection.set([
    std.selection.create(BlockSelection, { blockId }),
  ]);
}

const canvasMenuItem = {
  name: CANVAS_LABEL,
  description: '插入可编辑的文档内嵌画布',
  searchAlias: ['画布', '白板', '线框图', '思维导图'],
  icon: FrameIcon(),
  group: `${CANVAS_GROUP}@0` as `${number}_${string}@${number}`,
  action: ({ std, model }: { std: any; model: any }) => createCanvasAfter(std, model),
};

export const EmbeddedCanvasSlashExtension = SlashMenuConfigExtension(
  'secondbrain-embedded-canvas',
  { items: [canvasMenuItem] }
);

const selectedModelCanvasItem = {
  name: CANVAS_LABEL,
  icon: FrameIcon(),
  action: ({ std }: { std: any }) => {
    const [, result] = std.command.exec(getSelectedModelsCommand);
    createCanvasAfter(std, result?.selectedModels?.[0]);
  },
};

const morePanel = defaultKeyboardToolbarConfig.items[0] as {
  icon: any;
  activeIcon?: any;
  activeBackground?: string;
  groups: any[];
};

export const EmbeddedCanvasPlusExtension = KeyboardToolbarConfigExtension({
  items: [
    {
      ...morePanel,
      groups: [
        ...morePanel.groups,
        { name: '画布', items: [selectedModelCanvasItem] },
      ],
    },
    ...defaultKeyboardToolbarConfig.items.slice(1),
  ],
});

export function cropReferencedFramesToContent(std: any, store: any) {
  const references = new Set(
    store.getBlocksByFlavour('affine:surface-ref')
      .map((block: any) => block.model.props.reference)
      .filter(Boolean)
  );
  if (!references.size) return 0;

  const frameManager = std.get(EdgelessFrameManagerIdentifier);
  let cropped = 0;
  store.transact(() => {
    for (const frame of frameManager.frames) {
      if (!references.has(frame.id)) continue;
      const bounds = frameManager.getChildElementsInFrame(frame)
        .map((element: any) => element.elementBound)
        .filter((bound: any) => bound && bound.w > 0 && bound.h > 0);
      if (!bounds.length) continue;
      const left = Math.min(...bounds.map((bound: any) => bound.x));
      const top = Math.min(...bounds.map((bound: any) => bound.y));
      const right = Math.max(...bounds.map((bound: any) => bound.x + bound.w));
      const bottom = Math.max(...bounds.map((bound: any) => bound.y + bound.h));
      const padding = 40;
      frame.props.xywh = Bound.fromXYWH([
        left - padding,
        top - padding,
        right - left + padding * 2,
        bottom - top + padding * 2,
      ]).serialize();
      cropped++;
    }
  });
  return cropped;
}
