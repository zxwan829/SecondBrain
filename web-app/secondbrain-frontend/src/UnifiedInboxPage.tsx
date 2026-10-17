import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { notesApi, type NoteCollection } from './api/notes';
import { DEMO_NOTE_TAGS, DEMO_NOTE_TYPES, makeUnifiedInboxId, suggestInboxClassification, type MockClassification, type UnifiedInboxItem } from './unified-inbox';

type Locale = 'zh-CN' | 'en';
type CaptureItem = {
  capture_id: string;
  raw_path: string;
  review_path?: string | null;
  status: string;
  source_type?: string;
  input_type?: string;
  captured_at?: string;
  display_filename?: string | null;
  content_preview?: string;
  error?: { message?: string } | null;
};
type Decision = { status: 'approved_pending' | 'rejected'; value: string };
type ProposalProps = {
  id: string;
  title: string;
  reason: string;
  impact: string;
  preview: string;
  value: string;
  decision?: Decision;
  decisionRequired: boolean;
  onChange: (value: string) => void;
  onApprove: () => void;
  onReject: () => void;
  en: boolean;
  classificationOptions?: { type: string; tags: string[]; unknownTags: string[]; onTypeChange: (value: string) => void; onTagsChange: (value: string[]) => void };
};

function Proposal({ id, title, reason, impact, preview, value, decision, decisionRequired, onChange, onApprove, onReject, en, classificationOptions }: ProposalProps) {
  return <article className="unified-proposal" data-proposal={id}>
    <header><h4>{title}</h4><span>{en ? 'Mock AI suggestion' : '模拟 AI 建议'}</span></header>
    <p>{reason}</p>
    <p className="unified-proposal-impact">{en ? 'Impact scope' : '影响范围'}：{impact}</p>
    {classificationOptions ? <div className="unified-vocabulary-editor">
      <label>{en ? 'Suggested type (fixed demo vocabulary)' : '建议类型（固定演示词库）'}
        <select value={classificationOptions.type} onChange={(event) => classificationOptions.onTypeChange(event.target.value)} disabled={Boolean(decision)}>
          {DEMO_NOTE_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}
        </select>
      </label>
      <fieldset disabled={Boolean(decision)}><legend>{en ? 'Known demo tags' : '已知演示标签'}</legend>
        {DEMO_NOTE_TAGS.map((tag) => <label key={tag}><input type="checkbox" checked={classificationOptions.tags.includes(tag)} onChange={(event) => {
          const next = event.target.checked ? [...classificationOptions.tags, tag] : classificationOptions.tags.filter((item) => item !== tag);
          classificationOptions.onTagsChange(DEMO_NOTE_TAGS.filter((item) => next.includes(item)));
        }} />{tag}</label>)}
      </fieldset>
      {classificationOptions.unknownTags.length > 0 && <p role="status">{en ? 'Unrecognized tag candidates; separate vocabulary approval is required:' : '未识别的标签候选；需单独审批词库：'} {classificationOptions.unknownTags.map((tag) => `#${tag}`).join(' ')}</p>}
      <small>{en ? 'Synthetic fixed vocabulary only. New vocabulary is not applied by approving this content suggestion.' : '仅使用合成固定词库；批准内容建议不会批准或应用新词。'}</small>
    </div> : <label>{en ? 'Editable proposal' : '可编辑建议'}
      <textarea value={value} onChange={(event) => onChange(event.target.value)} disabled={Boolean(decision)} rows={3} />
    </label>}
    <small>{en ? 'Source preview' : '来源预览'}：{preview || (en ? 'No text preview available.' : '暂无正文预览。')}</small>
    {decision ? <p className={`unified-decision ${decision.status}`} role="status">
      {decision.status === 'rejected'
        ? (en ? 'Rejected; original retained.' : '已拒绝；原始内容保留。')
        : (en ? 'Simulation only: not submitted, persisted, queued, or executed. This status disappears on reload.'
          : '仅本页模拟同意：未提交、未持久化、未排队、未执行；刷新后消失。')}
    </p> : !decisionRequired ? <p className="unified-decision" role="status">{en
      ? 'Existing type and approved demo tags require no per-note approval under the product rule. Demo only: no metadata is written; unknown tag terms need separate vocabulary approval.'
      : '按产品规则，既有类型与演示词库中的有效标签无需逐条审批。仅为演示：不会写回属性；未知标签需单独经过词库审批。'}</p> : <footer>
      <button type="button" onClick={onApprove}>{en ? 'Simulate agreement (not executed)' : '本页模拟同意（未执行）'}</button>
      <button type="button" onClick={onReject}>{en ? 'Reject' : '拒绝'}</button>
    </footer>}
  </article>;
}

export function UnifiedInboxPage({ locale, onReview, showSyntheticCaptureDemo = import.meta.env.DEV, notesOnly = false }: { locale: Locale; onReview: (reviewPath: string) => void; showSyntheticCaptureDemo?: boolean; notesOnly?: boolean }) {
  const en = locale === 'en';
  const [captures, setCaptures] = useState<CaptureItem[]>([]);
  const [notes, setNotes] = useState<UnifiedInboxItem[]>([]);
  const [captureError, setCaptureError] = useState('');
  const [notesError, setNotesError] = useState('');
  const [loading, setLoading] = useState(true);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [createError, setCreateError] = useState('');
  const [creating, setCreating] = useState(false);
  const createInFlight = useRef(false);
  const [classifications, setClassifications] = useState<Record<string, MockClassification>>({});
  const [edits, setEdits] = useState<Record<string, Record<string, string>>>({});
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [syntheticCaptures, setSyntheticCaptures] = useState<CaptureItem[]>([]);
  const [manuallyRemovedTags, setManuallyRemovedTags] = useState<Record<string, string[]>>({});
  const [manuallySetTypes, setManuallySetTypes] = useState<Record<string, string>>({});

  const load = useCallback(async (showLoading = false) => {
    if (showLoading) setLoading(true);
    setCaptureError(''); setNotesError('');
    const captureTask = notesOnly ? Promise.resolve([] as CaptureItem[]) : fetch('/api/inbox?limit=100', { credentials: 'same-origin' }).then(async (response) => {
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return Array.isArray(payload.items) ? payload.items as CaptureItem[] : [];
    });
    const notesTask = (async () => {
      const { collections } = await notesApi.collections();
      const available = (Array.isArray(collections) ? collections : []).filter((collection) => collection.kind === 'drafts').slice(0, 1);
      const lists = await Promise.all(available.map(async (collection: NoteCollection) => ({
        collection,
        items: (await notesApi.list(collection.id)).items.slice(0, 100),
      })));
      const rows = await Promise.all(lists.flatMap(({ collection, items }) => items.slice(0, 100).map(async (item) => {
        const note = await notesApi.read(collection.id, item.path);
        return {
          id: makeUnifiedInboxId('notes', collection.id, item.path),
          source: 'notes' as const,
          sourceRef: `${collection.id}/${item.path}`,
          sourcePath: item.path,
          title: item.title || item.path,
          content: note.content,
          collection: collection.id,
          readOnly: note.read_only,
        };
      })));
      return rows;
    })();
    const [captureResult, notesResult] = await Promise.allSettled([captureTask, notesTask]);
    if (captureResult.status === 'fulfilled') setCaptures(captureResult.value);
    else setCaptureError(en ? 'Capture inbox could not be loaded.' : 'Capture 收件箱暂时无法加载。');
    if (notesResult.status === 'fulfilled') setNotes(notesResult.value);
    else {
      setNotes([]);
      setNotesError(en ? 'Notes are unavailable under the current Core session or configuration.' : '当前 Core 会话或配置未开放 Notes；Capture 收件箱仍可单独使用。');
    }
    setLoading(false);
  }, [en, notesOnly]);

  useEffect(() => {
    void load(true);
    const refresh = () => void load();
    window.addEventListener('sb-inbox-refresh', refresh);
    return () => window.removeEventListener('sb-inbox-refresh', refresh);
  }, [load]);

  const items = useMemo(() => {
    const captureItems = (notesOnly ? syntheticCaptures : [...captures, ...syntheticCaptures]).map((item) => ({
      id: makeUnifiedInboxId('capture', 'raw', item.capture_id),
      source: 'capture' as const,
      sourceRef: item.capture_id,
      sourcePath: item.raw_path,
      title: item.display_filename || item.raw_path.split('/').pop() || item.capture_id,
      content: item.content_preview || '',
      status: item.status,
      capturedAt: item.captured_at,
      readOnly: true,
      captureId: item.capture_id,
      reviewPath: item.review_path,
    }));
    return [...captureItems, ...notes].sort((a, b) => (b.capturedAt || '').localeCompare(a.capturedAt || '') || a.id.localeCompare(b.id));
  }, [captures, notes, syntheticCaptures, notesOnly]);

  const createNote = async (event: React.FormEvent) => {
    event.preventDefault();
    if (createInFlight.current || !title.trim() || !body.trim()) return;
    createInFlight.current = true;
    setCreating(true); setCreateError('');
    const markdown = `# ${title.trim()}\n\n${body.trim()}\n`;
    try {
      await notesApi.create(markdown);
      setTitle(''); setBody('');
      await load();
    } catch (cause) {
      setCreateError(cause instanceof Error ? cause.message : (en ? 'The note could not be created.' : '笔记创建失败。'));
    } finally { createInFlight.current = false; setCreating(false); }
  };

  const addSyntheticCapture = () => {
    const capture: CaptureItem = {
      capture_id: 'synthetic-capture-demo', raw_path: 'synthetic://capture-demo/meeting.md',
      status: 'completed', source_type: 'synthetic_demo', input_type: 'markdown',
      display_filename: '合成会议输入.md', captured_at: new Date(0).toISOString(),
      content_preview: '# 项目会议\n\n项目：SecondBrain\n讨论 Inbox 人工审批流程。 #SecondBrain',
    };
    setSyntheticCaptures((current) => current.some((item) => item.capture_id === capture.capture_id) ? current : [capture, ...current]);
  };

  const suggest = (item: UnifiedInboxItem) => {
    const previous = edits[item.id] || {};
    const value = suggestInboxClassification(item.content, item.title, manuallyRemovedTags[item.id] || [], manuallySetTypes[item.id] || '');
    setClassifications((current) => ({ ...current, [item.id]: value }));
    setEdits((current) => ({ ...current, [item.id]: {
      type: value.type, tags: previous.tags ?? value.tags.join(', '), unknownTags: value.unknownTagCandidates.join(', '), journal: value.journalExcerpt,
      knowledge: value.knowledgeReview, project: value.projectAssociation,
    } }));
  };
  const edit = (itemId: string, kind: string, value: string) => {
    if (kind === 'type') setManuallySetTypes((current) => ({ ...current, [itemId]: value }));
    if (kind === 'tags') {
      const previous = (edits[itemId]?.tags ?? classifications[itemId]?.tags.join(', ') ?? '').split(',').map((tag) => tag.trim()).filter(Boolean);
      const next = new Set(value.split(',').map((tag) => tag.trim().toLocaleLowerCase()).filter(Boolean));
      const removed = previous.filter((tag) => !next.has(tag.toLocaleLowerCase()));
      const added = value.split(',').map((tag) => tag.trim().toLocaleLowerCase()).filter(Boolean);
      setManuallyRemovedTags((current) => ({ ...current, [itemId]: [...new Set([...(current[itemId] || []).filter((tag) => !added.includes(tag.toLocaleLowerCase())), ...removed])] }));
    }
    setEdits((current) => ({ ...current, [itemId]: { ...(current[itemId] || {}), [kind]: value } }));
  };
  const decide = (item: UnifiedInboxItem, kind: string, status: Decision['status']) => {
    const key = `${item.id}:${kind}`;
    setDecisions((current) => current[key] ? current : ({ ...current, [key]: {
      status, value: status === 'approved_pending' ? (edits[item.id]?.[kind] ?? '') : '',
    } }));
  };

  const text = (key: string, fallback: string) => {
    const map: Record<string, string> = {
      createTitle: en ? 'New note' : '新建笔记', create: en ? 'Create note' : '新建并收录',
      inbox: en ? 'Unified Inbox' : '统一收件箱', subtitle: en ? 'Notes drafts and protected Capture items share one review view; original sources remain in their own Core-managed storage.' : '笔记草稿与受保护的 Capture 条目在此统一查看；原件仍保留于各自由 Core 管理的存储边界。',
      local: en ? 'Local development flow: new notes use the configured Notes Drafts API. This does not create or map a production 00-Inbox directory.' : '本地开发流程：新建笔记通过已配置的 Notes Drafts API 保存；不会创建或映射生产 00-Inbox 目录。',
      ai: en ? 'Generate deterministic mock suggestions' : '生成确定性 Mock 建议',
    };
    return map[key] || fallback;
  };

  return <section className={notesOnly ? 'unified-notes-inbox' : 'capture-page unified-inbox-page'} aria-labelledby="unified-inbox-title">
    {!notesOnly && <header className="capture-page-header"><div><p className="eyebrow">SECONDBRAIN <span>/</span> INBOX</p><h1 id="unified-inbox-title">{text('inbox', '统一收件箱')}</h1><p className="workspace-subtitle">{text('subtitle', '')}</p><p className="unified-inbox-boundary">{text('local', '')}</p></div>
      {showSyntheticCaptureDemo && <button type="button" className="capture-secondary" onClick={addSyntheticCapture}>{en ? 'Add synthetic Capture' : '添加合成 Capture 示例'}</button>}
    </header>}
    {notesOnly && <div className="unified-inbox-subheader"><h2 id="unified-inbox-title">{en ? 'Notes drafts' : '笔记草稿'}</h2>{showSyntheticCaptureDemo && <button type="button" className="capture-secondary" onClick={addSyntheticCapture}>{en ? 'Add synthetic Capture' : '添加合成 Capture 示例'}</button>}</div>}
    <form className="unified-note-create" onSubmit={(event) => void createNote(event)}>
      <h2>{text('createTitle', '')}</h2>
      <label>{en ? 'Title' : '标题'}<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={160} required /></label>
      <label>{en ? 'Content' : '正文'}<textarea value={body} onChange={(event) => setBody(event.target.value)} rows={3} maxLength={200000} required /></label>
      {createError && <p role="alert" className="capture-alert">{createError}</p>}
      <button type="submit" disabled={creating || !title.trim() || !body.trim()}>{creating ? (en ? 'Saving…' : '保存中…') : text('create', '')}</button>
    </form>
    {!notesOnly && captureError && <p role="alert" className="capture-alert">{captureError}</p>}
    {notesError && <p className="capture-processing-note" role="status">{notesError}</p>}
    <div className="inbox-list unified-inbox-list" aria-live="polite">
      {loading ? <p>{en ? 'Loading…' : '加载中…'}</p> : items.length ? items.map((item) => {
        const classification = classifications[item.id];
        const values = edits[item.id] || {};
        const decisionsFor = (kind: string) => decisions[`${item.id}:${kind}`];
        const suggestions = classification ? [
          { kind: 'classification', title: en ? 'Type and tags' : '类型与标签', reason: classification.reason, impact: en ? 'Existing vocabulary values are editable; no note metadata is written in this demo.' : '可编辑既有词汇建议；本演示不写入笔记属性。', value: `${values.type || classification.type}\n${values.tags ?? classification.tags.join(', ')}`, preview: `${item.source} · ${item.sourceRef}`, textarea: false },
          { kind: 'journal', title: en ? 'Journal excerpt' : '建议日记摘录', reason: /^\s*(?:记一下|记下来|写日记|记录一下)/.test(item.content) ? (en ? 'Explicit Journal intent detected; final writing still requires the existing journal.append gate.' : '检测到显式日记意图；最终写入仍须通过现有 journal.append 门禁。') : (en ? 'No explicit Journal intent; this is a suggestion only.' : '未检测到显式日记意图，仅作为建议。'), impact: en ? 'No Journal record is created in this slice; source provenance is not yet represented by the Journal API.' : '本切片不会创建 Journal 记录；当前 Journal API 尚不能表达此来源的可追溯关联。', value: values.journal ?? classification.journalExcerpt, preview: item.content.slice(0, 200), textarea: true },
          { kind: 'knowledge', title: en ? 'Knowledge Review submission' : '知识 Review 提交', reason: en ? 'Would create a new Raw/Capture copy; a provenance-bound Review endpoint is not available in this slice.' : '若提交会新增 Raw/Capture 副本；本切片没有可保留原始来源关联的 Review 接口。', impact: en ? 'No Raw, Review, or Knowledge file is written or promoted; the original stays in its source.' : '不写入 Raw、Review 或 Knowledge 文件，也不执行 Promote；原件留在原位置。', value: values.knowledge ?? classification.knowledgeReview, preview: item.sourceRef, textarea: true },
          { kind: 'project', title: en ? 'Project association' : '项目关联', reason: en ? 'Use a source link/metadata reference; project-link persistence is not available in this slice.' : '按规范应使用来源链接/元数据引用；本切片暂无项目关联持久化接口。', impact: en ? 'No project file is moved or edited; only an in-page pending decision is recorded.' : '不移动或编辑项目文件；仅记录本页待执行审批状态。', value: values.project ?? classification.projectAssociation, preview: item.sourceRef, textarea: false },
        ] : [];
        return <article className="inbox-item unified-inbox-item" key={item.id} data-source={item.source}>
          <div className="inbox-item-main"><span className="inbox-type">{item.source === 'capture' ? 'CAPTURE' : 'NOTES'}</span><div><h2>{item.title}</h2><p>{item.sourceRef} · {item.sourcePath}</p></div>{item.status && <span className={`capture-status status-${item.status}`}>{item.status}</span>}</div>
          {item.content && <pre className="inbox-preview">{item.content.slice(0, 700)}</pre>}
          {item.readOnly && <p className="capture-processing-note">{en ? 'This source contains Markdown syntax that the rich-text editor cannot safely rewrite.' : '此来源包含富文本编辑器无法安全回写的 Markdown 特殊语法。'}</p>}
          <div className="inbox-links">{item.source === 'capture' && item.captureId && !item.sourcePath.startsWith('synthetic://') && <a href={`/api/inbox/${encodeURIComponent(item.captureId)}/raw`} download>{en ? 'Download original' : '下载原件'}</a>}{item.reviewPath && <button type="button" onClick={() => onReview(item.reviewPath!)}>{en ? 'Open Review' : '打开 Review'}</button>}</div>
          {!classification ? <button type="button" className="unified-suggest-button" onClick={() => suggest(item)}>{text('ai', '')}</button> : <div className="unified-suggestion-list" aria-label={en ? 'Suggestions for human approval' : '待人工逐项审批的建议'}>
            <p className="unified-mock-boundary">{en ? 'Deterministic local Mock only. Decisions shown here are not persisted or executed.' : '仅确定性本地 Mock。此处显示的审批决定不会持久化或执行。'}</p>
            <button type="button" className="unified-suggest-button" onClick={() => suggest(item)}>{en ? 'Regenerate Mock suggestions (preserve manual corrections)' : '重新生成 Mock 建议（保留手动修正）'}</button>
            {suggestions.map((suggestion) => <Proposal key={suggestion.kind} id={suggestion.kind} title={suggestion.title} reason={suggestion.reason} impact={suggestion.impact} preview={suggestion.preview} value={suggestion.value} en={en} decision={decisionsFor(suggestion.kind)} decisionRequired={suggestion.kind !== 'classification'}
              classificationOptions={suggestion.kind === 'classification' ? { type: (DEMO_NOTE_TYPES as readonly string[]).includes(values.type || '') ? values.type || classification.type : classification.type, tags: (values.tags ?? classification.tags.join(', ')).split(/,\s*/).filter((tag) => (DEMO_NOTE_TAGS as readonly string[]).includes(tag)), unknownTags: classification.unknownTagCandidates, onTypeChange: (value) => edit(item.id, 'type', value), onTagsChange: (tags) => edit(item.id, 'tags', tags.join(', ')) } : undefined}
              onChange={(value) => edit(item.id, suggestion.kind, value)} onApprove={() => decide(item, suggestion.kind, 'approved_pending')} onReject={() => decide(item, suggestion.kind, 'rejected')} />)}
          </div>}
        </article>;
      }) : <p className="capture-empty">{en ? 'Nothing is waiting in Inbox.' : '收件箱中暂无待处理内容。'}</p>}
    </div>
  </section>;
}
