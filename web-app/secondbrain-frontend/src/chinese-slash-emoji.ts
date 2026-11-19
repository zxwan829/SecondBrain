import { SlashMenuConfigExtension } from '@blocksuite/affine-widget-slash-menu';
import { html } from 'lit';

/**
 * Isolated, official SlashMenuConfigExtension contribution.
 * BlockSuite 0.22.4 ships no locale registry or Chinese locale bundle; this
 * extension adds discoverable Chinese slash entries without replacing native
 * menu strings or mutating the DOM.
 */
export const ChineseSlashEmojiExtension = SlashMenuConfigExtension(
  'secondbrain-chinese-emoji',
  {
    items: [
      {
        name: '插入表情图标',
        searchAlias: ['emoji', 'emojis', '表情', '表情选择器', '表情库'],
        icon: html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="8.5"></circle><path d="M8.5 14.2c.9 1.2 2.1 1.8 3.5 1.8s2.6-.6 3.5-1.8"></path><path d="M9 9.5h.01M15 9.5h.01"></path></svg>`,
        group: '4_内容与媒体@40',
        action: ({ std, model }) => {
          (std.host as HTMLElement).dispatchEvent(new CustomEvent('sb-open-emoji-picker', { bubbles: true, composed: true, detail: { modelId: model.id } }));
        },
      },
    ],
  }
);
