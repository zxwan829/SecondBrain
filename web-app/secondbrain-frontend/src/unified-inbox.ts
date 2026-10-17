export type UnifiedInboxSource = 'notes' | 'capture';

export type UnifiedInboxItem = {
  id: string;
  source: UnifiedInboxSource;
  sourceRef: string;
  sourcePath: string;
  title: string;
  content: string;
  status?: string;
  capturedAt?: string;
  collection?: string;
  readOnly?: boolean;
  captureId?: string;
  reviewPath?: string | null;
};

export type MockClassification = {
  type: string;
  tags: string[];
  reason: string;
  journalExcerpt: string;
  knowledgeReview: string;
  projectAssociation: string;
};

/** Deterministic local-only classifier. It never calls a model or external service. */
export function suggestInboxClassification(content: string, title = ''): MockClassification {
  const text = `${title}\n${content}`;
  const journalIntent = /^\s*(?:记一下|记下来|写日记|记录一下)(?:[：:,，\s]+|$)/.test(content);
  const type = journalIntent ? '日记'
    : /会议|纪要|参会|议程/.test(text) ? '会议纪要'
      : /头脑风暴|brainstorm|发散/.test(text) ? '头脑风暴'
        : /摘要|总结|summary/i.test(text) ? '摘要' : '笔记';
  const tags = [...new Set(Array.from(text.matchAll(/(?:^|\s)#([\p{L}\p{N}_-]{1,40})/gu), (match) => match[1]))].slice(0, 5);
  const project = text.match(/项目\s*[：:]\s*([^\n，,。]+)/)?.[1]?.trim()
    || text.match(/#(SecondBrain|[A-Za-z][A-Za-z0-9_-]{2,})/)?.[1]
    || '';
  const excerpt = content.trim().slice(0, 1200);
  const summary = content.trim().replace(/\s+/g, ' ').slice(0, 240);
  return {
    type,
    tags: tags.length ? tags : ['待整理'],
    reason: journalIntent ? '命中显式日记表达。'
      : type === '会议纪要' ? '内容包含会议或纪要线索。'
        : type === '头脑风暴' ? '内容包含头脑风暴线索。'
          : type === '摘要' ? '内容包含摘要或总结线索。' : '未发现更具体的类型线索，建议先作为普通笔记。',
    journalExcerpt: journalIntent ? excerpt : '未检测到明确日记意图；仅供人工评估。',
    knowledgeReview: summary || '暂无可用于 Review 的正文预览。',
    projectAssociation: project || '未检测到可核验的项目引用。',
  };
}

export function makeUnifiedInboxId(source: UnifiedInboxSource, collection: string, path: string): string {
  return `${source}:${collection}:${path}`;
}
