import { popupTargetFromElement } from '@blocksuite/affine-components/context-menu';
import { computed } from '@preact/signals-core';
import { html } from 'lit/static-html.js';

import { popTagSelect } from '../../core/component/tags/multi-tag-select.js';
import type { SelectTag } from '../../core/index.js';
import { BaseCellRenderer } from '../../core/property/index.js';
import { createFromBaseCellRenderer } from '../../core/property/renderer.js';
import { stopPropagation } from '../../core/utils/event.js';
import { createIcon } from '../../core/utils/uni-icon.js';
import type { SelectPropertyData } from '../select/define.js';
import { multiSelectStyle } from './cell-renderer-css.js';
import { multiSelectPropertyModelConfig } from './define.js';

export class MultiSelectCell extends BaseCellRenderer<
  string[],
  string[],
  SelectPropertyData
> {
  closePopup?: () => void;
  private completing = false; // sb-select-cell-close-reentrancy-guard-v1
  private readonly popTagSelect = () => {
    this.closePopup = popTagSelect(popupTargetFromElement(this), {
      name: this.cell.property.name$.value,
      options: this.options$,
      onOptionsChange: this._onOptionsChange,
      value: this._value$,
      onChange: v => {
        this.valueSetImmediate(v);
      },
      onComplete: this._editComplete,
      minWidth: 400,
    });
  };

  _editComplete = () => {
    if (this.completing) return;
    this.completing = true;
    // Clear before changing selection: beforeExitEditingMode closes the popover,
    // whose onComplete callback can otherwise re-enter this method recursively.
    this.closePopup = undefined;
    this.selectCurrentCell(false);
  };

  _onOptionsChange = (options: SelectTag[]) => {
    this.property.dataUpdate(data => {
      return {
        ...data,
        options,
      };
    });
  };

  options$ = computed(() => {
    return this.property.data$.value.options;
  });
  _value$ = computed(() => {
    return this.value ?? [];
  });

  override afterEnterEditingMode() {
    this.completing = false;
    if (!this.closePopup) {
      this.popTagSelect();
    }
  }

  override beforeExitEditingMode() {
    const closePopup = this.closePopup;
    this.closePopup = undefined;
    closePopup?.();
  }

  override render() {
    return html`
      <div
        class="${multiSelectStyle}"
        @pointerdown="${this.isEditing$.value ? stopPropagation : undefined}"
      >
        <affine-multi-tag-view
          .value="${this._value$.value}"
          .options="${this.options$.value}"
        ></affine-multi-tag-view>
      </div>
    `;
  }
}

export const multiSelectPropertyConfig =
  multiSelectPropertyModelConfig.createPropertyMeta({
    icon: createIcon('MultiSelectIcon'),
    cellRenderer: {
      view: createFromBaseCellRenderer(MultiSelectCell),
    },
  });
