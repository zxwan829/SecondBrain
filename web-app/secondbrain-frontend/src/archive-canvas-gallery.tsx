import React from 'react';
import type { CanvasPreviewShape } from './canvas-preview';

export type ArchiveCanvasCard = {
  resourceId: string; blockId: string; title: string; revision?: string; dirty?: boolean;
  preview: CanvasPreviewShape[]; loading?: boolean; error?: string;
};
/** The host maps these explicit actions to the current note's guarded Core APIs. */
export function ArchiveCanvasGallery({ cards, readonly, onCreate, onOpen, onCopy, onRemoveReference }: {
  cards: ArchiveCanvasCard[]; readonly: boolean; onCreate: () => void;
  onOpen: (card: ArchiveCanvasCard) => void; onCopy: (card: ArchiveCanvasCard) => void;
  onRemoveReference: (card: ArchiveCanvasCard) => void;
}) {
  return <section className="sb-archive-surface canvas-b-page" aria-label="独立画布资源">
    <div className="canvas-b-controls"><button disabled={readonly} onClick={onCreate}>新建独立画布</button></div>
    <div className="canvas-b-card-grid">{cards.map(card => {
      const list = card.preview.filter(item => item.bound.length === 4 && item.bound.every(Number.isFinite));
      const bounds = list.map(item => item.bound);
      const minX = Math.min(...bounds.map(bound => bound[0])), minY = Math.min(...bounds.map(bound => bound[1]));
      const maxX = Math.max(...bounds.map(bound => bound[0] + bound[2])), maxY = Math.max(...bounds.map(bound => bound[1] + bound[3]));
      const padding = 18;
      return <article className="canvas-b-card" key={card.resourceId}>
        <div className="canvas-b-card-preview" role="button" tabIndex={0} aria-label={`打开画布 ${card.title}`}
          onDoubleClick={() => onOpen(card)} onKeyDown={event => { if (event.key === 'Enter') onOpen(card); }}>
          {bounds.length ? <><span>自动裁剪预览 · {list.length} 个对象</span><svg viewBox={`${minX - padding} ${minY - padding} ${Math.max(1, maxX - minX + padding * 2)} ${Math.max(1, maxY - minY + padding * 2)}`} preserveAspectRatio="xMidYMid meet">
            {list.map(item => item.type === 'shape' && item.shapeType === 'ellipse'
              ? <ellipse key={item.id} cx={item.bound[0] + item.bound[2] / 2} cy={item.bound[1] + item.bound[3] / 2} rx={item.bound[2] / 2} ry={item.bound[3] / 2} />
              : <rect key={item.id} x={item.bound[0]} y={item.bound[1]} width={item.bound[2]} height={item.bound[3]} />)}
          </svg></> : <span>{card.loading ? '正在读取画布…' : card.error ? '画布暂时无法读取；资源仍保留' : '空白画布 · 尚无 GFX 对象'}</span>}
        </div>
        <strong>{card.title}</strong><code>{card.resourceId}</code><small>{card.dirty ? '有未保存修改' : '已保存'} · {card.revision ?? '尚无版本'}</small>
        <div className="canvas-b-controls"><button disabled={card.loading} onClick={() => onOpen(card)}>打开编辑</button>
          <button disabled={readonly || card.loading} onClick={() => onCopy(card)}>深拷贝画布</button>
          <button disabled={readonly || card.loading} onClick={() => onRemoveReference(card)}>移除引用</button></div>
      </article>;
    })}</div>
  </section>;
}
