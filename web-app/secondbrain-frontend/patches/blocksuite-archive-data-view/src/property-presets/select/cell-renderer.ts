import { popupTargetFromElement } from '@blocksuite/affine-components/context-menu';
import { computed } from '@preact/signals-core';
import { html } from 'lit/static-html.js';

import { popTagSelect } from '../../core/component/tags/multi-tag-select.js';
import type { SelectTag } from '../../core/index.js';
import { BaseCellRenderer } from '../../core/property/index.js';
import { createFromBaseCellRenderer } from '../../core/property/renderer.js';
import { createIcon } from '../../core/utils/uni-icon.js';
import { selectStyle } from './cell-renderer-css.js';
import {
  type SelectPropertyData,
  selectPropertyModelConfig,
} from './define.js';

export class SelectCell extends BaseCellRenderer<
  string,
  string,
  SelectPropertyData
> {
  closePopup?: () => void;
  private completing = false; // sb-select-cell-close-reentrancy-guard-v1
  private readonly popTagSelect = () => {
    this.closePopup = popTagSelect(popupTargetFromElement(this), {
      name: this.cell.property.name$.value,
      mode: 'single',
      options: this.options$,
      onOptionsChange: this._onOptionsChange,
      value: this._value$,
      onChange: v => {
        this.valueSetImmediate(v[0]);
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
    const value = this.value;
    return value ? [value] : [];
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
      <div class="${selectStyle}">
        <affine-multi-tag-view
          .value="${this._value$.value}"
          .options="${this.options$.value}"
        ></affine-multi-tag-view>
      </div>
    `;
  }
}

export const selectPropertyConfig =
  selectPropertyModelConfig.createPropertyMeta({
    icon: createIcon('SingleSelectIcon'),
    cellRenderer: {
      view: createFromBaseCellRenderer(SelectCell),
    },
  });
