import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { notesApi, type NoteCollection } from './api/notes';
import { makeUnifiedInboxId, suggestInboxClassification, SYNTHETIC_APPROVED_TAGS, SYNTHETIC_STANDARD_TYPES, type MockClassification, type UnifiedInboxItem } from './unified-inbox';
import { apiFailureLabel, captureFailureLabel, captureStatusLabel, isImageOcrDescriptionUnavailable } from './user-messages';

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
  processor?: { kind?: string } | null;
  source_url?: string | null;
  derived_source_url?: string | null;
};
type Decision = { status: 'simulated_accepted' | 'rejected'; value: string };
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
};

function Proposal({ id, title, reason, impact, preview, value, decision, decisionRequired, onChange, onApprove, onReject, en }: ProposalProps) {
  return <article className="unified-proposal" data-proposal={id}>
    <header><h4>{title}</h4><span>{en ? 'Mock AI suggestion' : '模拟 AI 建议'}</span></header>
    <p>{reason}</p>
    <p className="unified-proposal-impact">{en ? 'Impact scope' : '影响范围'}：{impact}</p>
    <label>{en ? 'Editable proposal' : '可编辑建议'}
      {id === 'type' ? <><input value={value} list="synthetic-standard-types" onChange={(event) => onChange(event.target.value)} disabled={Boolean(decision)} /><datalist id="synthetic-standard-types">{SYNTHETIC_STANDARD_TYPES.map((type) => <option key={type} value={type} />)}</datalist></> : <textarea value={value} onChange={(event) => onChange(event.target.value)} disabled={Boolean(decision)} rows={3} />}
    </label>
    <small>{en ? 'Source preview' : '来源预览'}：{preview || (en ? 'No text preview available.' : '暂无正文预览。')}</small>
    {decision ? <p className={`unified-decision ${decision.status}`} role="status">
      {decision.status === 'rejected'
        ? (en ? 'Rejected; original retained.' : '已拒绝；原始内容保留。')
        : (en ? 'Simulation only: not submitted, queued, or executed. This decision exists only in this page and disappears after reload.'
          : '仅本页模拟同意：未提交、未排队、未执行；此决定只存在于当前页面，刷新后消失。')}
    </p> : !decisionRequired ? <p className="unified-decision" role="status">{id === 'type'
      ? (en ? (value && (SYNTHETIC_STANDARD_TYPES as readonly string[]).includes(value.trim()) ? 'An existing type can be selected automatically under the product rule. Demo only: this value is not written.' : 'A new type needs separate vocabulary approval in Issue #55. This demo neither adds it nor writes note properties.') : (value && (SYNTHETIC_STANDARD_TYPES as readonly string[]).includes(value.trim()) ? '按产品规则，既有类型可自动选用。仅为演示：不会写回属性。' : '新类型需在 Issue #55 独立词库中审批；本演示不会新增词条或写回笔记。'))
      : (en ? 'Existing valid tags may be applied automatically. Demo only: no tags are written; new vocabulary still requires separate approval.' : '既有有效标签按规则可自动应用。仅为演示：不会写入标签；新词仍需单独审批。')}</p> : <footer>
      <button type="button" onClick={onApprove}>{en ? 'Simulate agreement (not executed)' : '本页模拟同意（未执行）'}</button>
      <button type="button" onClick={onReject}>{en ? 'Reject' : '拒绝'}</button>
    </footer>}
  </article>;
}

export function UnifiedInboxPage({ locale, onReview, showSyntheticCaptureDemo = import.meta.env.DEV }: { locale: Locale; onReview: (reviewPath: string) => void; showSyntheticCaptureDemo?: boolean }) {
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
  const [preview, setPreview] = useState<CaptureItem | null>(null);
  const [previewText, setPreviewText] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState('');
  const [organizeReason, setOrganizeReason] = useState('');
  const [organizeAvailable, setOrganizeAvailable] = useState(false);
  const [organizeBusy, setOrganizeBusy] = useState(false);
  const [organizeMessage, setOrganizeMessage] = useState('');
  const [manuallyRemovedTags, setManuallyRemovedTags] = useState<Record<string, string[]>>({});

  const load = useCallback(async (showLoading = false, refreshNotes = true) => {
    if (showLoading) setLoading(true);
    setCaptureError(''); if (refreshNotes) setNotesError('');
    const captureTask = fetch('/api/inbox', { credentials: 'same-origin' }).then(async (response) => {
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return Array.isArray(payload.items) ? payload.items as CaptureItem[] : [];
    });
    const notesTask = refreshNotes ? (async () => {
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
    })() : Promise.resolve<UnifiedInboxItem[]>([]);
    const results = await Promise.allSettled([captureTask, notesTask]);
    const captureResult = results[0];
    if (captureResult.status === 'fulfilled') setCaptures(captureResult.value);
    else setCaptureError(en ? 'Capture inbox could not be loaded.' : 'Capture 收件箱暂时无法加载。');
    if (refreshNotes) {
      const notesResult = results[1];
      if (notesResult.status === 'fulfilled') setNotes(notesResult.value);
      else {
        setNotes([]);
        setNotesError(en ? 'Notes are unavailable under the current Core session or configuration.' : '当前 Core 会话或配置未开放 Notes；Capture 收件箱仍可单独使用。');
      }
    }
    setLoading(false);
  }, [en]);

  useEffect(() => {
    void load(true);
    void fetch('/api/automation/organize/status', { credentials: 'same-origin' }).then((response) => response.json()).then((value) => {
      if (typeof value?.blocked_reason === 'string') setOrganizeReason(value.blocked_reason);
      setOrganizeAvailable(value?.execution_available === true);
    }).catch(() => setOrganizeReason(en ? 'The organization runner is unavailable.' : '自动整理执行器当前不可用。'));
    const refresh = () => void load(false, false);
    window.addEventListener('sb-inbox-refresh', refresh);
    const timer = window.setInterval(refresh, 5000);
    return () => { window.removeEventListener('sb-inbox-refresh', refresh); window.clearInterval(timer); };
  }, [load, en]);

  const items = useMemo(() => {
    const captureItems: UnifiedInboxItem[] = [...captures, ...syntheticCaptures].map((item) => ({
      id: makeUnifiedInboxId('capture', 'raw', item.capture_id),
      source: 'capture' as const,
      sourceRef: item.capture_id,
      sourcePath: item.raw_path,
      title: item.display_filename || item.raw_path.split('/').pop() || item.capture_id,
      content: item.content_preview || '',
      status: item.status,
      capturedAt: item.captured_at,
      captureId: item.capture_id,
      reviewPath: item.review_path,
    }));
    return [...captureItems, ...notes].sort((a, b) => (b.capturedAt || '').localeCompare(a.capturedAt || '') || a.id.localeCompare(b.id));
  }, [captures, notes, syntheticCaptures]);

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
    const value = suggestInboxClassification(item.content, item.title, manuallyRemovedTags[item.id] || [], previous.type || '');
    setClassifications((current) => ({ ...current, [item.id]: value }));
    setEdits((current) => ({ ...current, [item.id]: {
      type: value.type, tags: previous.tags ?? value.tags.join(', '), journal: value.journalExcerpt,
      knowledge: value.knowledgeReview, project: value.projectAssociation,
    } }));
  };
  const edit = (itemId: string, kind: string, value: string) => {
    if (kind === 'tags') {
      const previous = (edits[itemId]?.tags || '').split(',').map((tag) => tag.trim()).filter(Boolean);
      const next = new Set(value.split(',').map((tag) => tag.trim().toLocaleLowerCase()).filter(Boolean));
      const removedNow = previous.filter((tag) => !next.has(tag.toLocaleLowerCase()));
      const addedNow = value.split(',').map((tag) => tag.trim().toLocaleLowerCase()).filter(Boolean);
      setManuallyRemovedTags((current) => ({ ...current, [itemId]: [...new Set([...(current[itemId] || []).filter((tag) => !addedNow.includes(tag.toLocaleLowerCase())), ...removedNow])] }));
    }
    setEdits((current) => ({ ...current, [itemId]: { ...(current[itemId] || {}), [kind]: value } }));
  };
  const decide = (item: UnifiedInboxItem, kind: string, status: Decision['status']) => {
    const key = `${item.id}:${kind}`;
    setDecisions((current) => current[key] ? current : ({ ...current, [key]: {
      status, value: status === 'simulated_accepted' ? (edits[item.id]?.[kind] ?? '') : '',
    } }));
  };

  const previewKind = (path: string): 'text' | 'pdf' | 'image' | 'audio' | 'unsupported' => {
    const suffix = path.toLowerCase().split('.').pop() || '';
    if (['txt', 'md', 'markdown'].includes(suffix)) return 'text';
    if (suffix === 'pdf') return 'pdf';
    if (['png', 'jpg', 'jpeg', 'webp', 'gif'].includes(suffix)) return 'image';
    if (['wav', 'mp3', 'm4a', 'aac', 'ogg', 'flac'].includes(suffix)) return 'audio';
    return 'unsupported';
  };
  const openPreview = async (item: CaptureItem) => {
    setPreview(item); setPreviewText(null); setPreviewError('');
    if (previewKind(item.raw_path) === 'text') {
      try {
        const response = await fetch(`/api/inbox/${encodeURIComponent(item.capture_id)}/preview`, { credentials: 'same-origin' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        setPreviewText(await response.text());
      } catch { setPreviewError(en ? 'Preview could not be loaded.' : '原件预览暂时无法加载。'); }
    }
  };
  const retryCapture = async (item: CaptureItem) => {
    setCaptureError('');
    try {
      const response = await fetch(`/api/capture/${encodeURIComponent(item.capture_id)}/retry`, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(apiFailureLabel(payload.detail, response.status, locale, 'capture'));
      await load(false, false);
    } catch (cause) {
      setCaptureError(cause instanceof Error ? cause.message : (en ? 'Retry failed.' : '重试请求未成功，请稍后再试。'));
    }
  };
  const organizeNow = async () => {
    if (!organizeAvailable || organizeBusy) return;
    setOrganizeBusy(true); setOrganizeMessage('');
    try {
      const response = await fetch('/api/automation/organize/run', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      const value = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error('organizer_run_failed');
      setOrganizeMessage(value.status === 'no_new_messages' ? (en ? 'No new messages to organize.' : '没有新增对话，无需整理。')
        : value.status === 'already_running' ? (en ? 'An organization job is already running.' : '已有整理任务正在运行。')
          : (en ? `Organization finished; ${Number(value.draft_count ?? 0)} drafts added.` : `整理完成，新增 ${Number(value.draft_count ?? 0)} 条 Review 草稿。`));
      window.dispatchEvent(new Event('sb-inbox-refresh'));
    } catch {
      setOrganizeMessage(en ? 'Organization could not be completed; check its status and try again.' : '整理未能完成，请查看运行状态后再试。');
    } finally { setOrganizeBusy(false); }
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

  return <section className="capture-page unified-inbox-page" aria-labelledby="unified-inbox-title">
    <header className="capture-page-header"><div><p className="eyebrow">SECONDBRAIN <span>/</span> INBOX</p><h1 id="unified-inbox-title">{text('inbox', '统一收件箱')}</h1><p className="workspace-subtitle">{text('subtitle', '')}</p><p className="unified-inbox-boundary">{text('local', '')}</p></div>
      <div className="inbox-header-actions"><button type="button" disabled={!organizeAvailable || organizeBusy} title={organizeReason} onClick={() => void organizeNow()}>{organizeBusy ? (en ? 'Organizing…' : '整理中…') : (en ? 'Organize now' : '立即整理')}</button><small>{organizeReason || (en ? 'Settings are saved, but the organizer is not active.' : '设置仅保存，自动整理尚未运行。')}</small>{organizeMessage && <small role="status">{organizeMessage}</small>}{showSyntheticCaptureDemo && <button type="button" className="capture-secondary" onClick={addSyntheticCapture}>{en ? 'Add synthetic Capture' : '添加合成 Capture 示例'}</button>}</div>
    </header>
    <form className="unified-note-create" onSubmit={(event) => void createNote(event)}>
      <h2>{text('createTitle', '')}</h2>
      <label>{en ? 'Title' : '标题'}<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={160} required /></label>
      <label>{en ? 'Content' : '正文'}<textarea value={body} onChange={(event) => setBody(event.target.value)} rows={3} maxLength={200000} required /></label>
      {createError && <p role="alert" className="capture-alert">{createError}</p>}
      <button type="submit" disabled={creating || !title.trim() || !body.trim()}>{creating ? (en ? 'Saving…' : '保存中…') : text('create', '')}</button>
    </form>
    {captureError && <p role="alert" className="capture-alert">{captureError}</p>}
    {notesError && <p className="capture-processing-note" role="status">{notesError}</p>}
    <div className="inbox-list unified-inbox-list" aria-live="polite">
      {loading ? <p>{en ? 'Loading…' : '加载中…'}</p> : items.length ? items.map((item) => {
        const captureItem = item.source === 'capture' ? captures.find((capture) => capture.capture_id === item.captureId) : undefined;
        const classification = classifications[item.id];
        const values = edits[item.id] || {};
        const decisionsFor = (kind: string) => decisions[`${item.id}:${kind}`];
        const typeValue = values.type ?? classification?.type ?? '';
        const typeIsStandard = (SYNTHETIC_STANDARD_TYPES as readonly string[]).includes(typeValue.trim());
        const tagValue = values.tags ?? classification?.tags.join(', ') ?? '';
        const tagTerms = tagValue.split(',').map((tag) => tag.trim()).filter(Boolean);
        const approvedTagNames = new Set((SYNTHETIC_APPROVED_TAGS as readonly string[]).map((tag) => tag.toLocaleLowerCase()));
        const newTagTerms = tagTerms.filter((tag) => !approvedTagNames.has(tag.toLocaleLowerCase()));
        const suggestions = classification ? [
          { kind: 'type', title: en ? 'Type suggestion' : '类型建议', reason: typeIsStandard ? (en ? `Existing synthetic vocabulary term; per-note approval is not required by the product rule. ${classification.reason}` : `合成词库中的既有类型；产品规则不要求逐条审批。${classification.reason}`) : (en ? 'New type candidate: requires separate vocabulary confirmation (Issue #55); it is not an approved standard term.' : '新类型候选：需在独立词库管理（Issue #55）中确认，目前不是标准类型。'), impact: en ? 'This mock writes nothing; note metadata and the central type library remain unchanged.' : '本 Mock 不写入任何内容；笔记属性和集中类型库均不变。', value: typeValue, preview: `${item.source} · ${item.sourceRef}`, textarea: false },
          { kind: 'tags', title: en ? 'Tag suggestions' : '标签建议', reason: en ? `Synthetic approved tags: ${classification.tags.join(', ') || 'none'}. New terms requiring Issue #55 vocabulary approval: ${[...new Set([...classification.newTagCandidates, ...newTagTerms])].join(', ') || 'none'}. Manually removed tags are suppressed for this item in this page.` : `合成有效标签：${classification.tags.join('、') || '无'}。需经 Issue #55 词库审批的新词候选：${[...new Set([...classification.newTagCandidates, ...newTagTerms])].join('、') || '无'}。本页对该条目已手动移除的标签会抑制自动建议。`, impact: en ? 'Type and tags remain separate. This page-only simulation does not write tags or create vocabulary entries.' : '类型和标签彼此独立。页面模拟不会写入标签或创建词条。', value: tagValue, preview: `${item.source} · ${item.sourceRef}`, textarea: true },
          { kind: 'journal', title: en ? 'Journal excerpt' : '建议日记摘录', reason: /^\s*(?:记一下|记下来|写日记|记录一下)/.test(item.content) ? (en ? 'Explicit Journal intent detected; final writing still requires the existing journal.append gate.' : '检测到显式日记意图；最终写入仍须通过现有 journal.append 门禁。') : (en ? 'No explicit Journal intent; this is a suggestion only.' : '未检测到显式日记意图，仅作为建议。'), impact: en ? 'No Journal record is created in this slice; source provenance is not yet represented by the Journal API.' : '本切片不会创建 Journal 记录；当前 Journal API 尚不能表达此来源的可追溯关联。', value: values.journal ?? classification.journalExcerpt, preview: item.content.slice(0, 200), textarea: true },
          { kind: 'knowledge', title: en ? 'Knowledge Review submission' : '知识 Review 提交', reason: en ? 'Would create a new Raw/Capture copy; a provenance-bound Review endpoint is not available in this slice.' : '若提交会新增 Raw/Capture 副本；本切片没有可保留原始来源关联的 Review 接口。', impact: en ? 'No Raw, Review, or Knowledge file is written or promoted; the original stays in its source.' : '不写入 Raw、Review 或 Knowledge 文件，也不执行 Promote；原件留在原位置。', value: values.knowledge ?? classification.knowledgeReview, preview: item.sourceRef, textarea: true },
          { kind: 'project', title: en ? 'Project association' : '项目关联', reason: en ? 'Use a source link/metadata reference; project-link persistence is not available in this slice.' : '按规范应使用来源链接/元数据引用；本切片暂无项目关联持久化接口。', impact: en ? 'No project file is moved or edited; only an in-page pending decision is recorded.' : '不移动或编辑项目文件；仅记录本页待执行审批状态。', value: values.project ?? classification.projectAssociation, preview: item.sourceRef, textarea: false },
        ] : [];
        return <article className="inbox-item unified-inbox-item" key={item.id} data-source={item.source}>
          <div className="inbox-item-main"><span className="inbox-type">{item.source === 'capture' ? (captureItem?.input_type || 'CAPTURE').toUpperCase() : 'NOTES'}</span><div><h2>{item.title}</h2><p>{item.source === 'capture' && captureItem?.source_type ? `${captureItem.source_type} · ` : ''}{item.sourceRef} · {item.sourcePath}{item.capturedAt ? ` · ${new Date(item.capturedAt).toLocaleString(en ? 'en-US' : 'zh-CN')}` : ''}</p></div>{item.status && <span className={`capture-status status-${item.status}`}>{item.source === 'capture' ? captureStatusLabel(item.status, locale) : item.status}</span>}</div>
          {item.content && <pre className="inbox-preview">{item.content.slice(0, item.source === 'capture' ? 500 : 700)}</pre>}
          {item.source === 'capture' && <>
            {captureItem && isImageOcrDescriptionUnavailable(captureItem)
              ? <p className="capture-processing-note" role="status">{en ? 'Text recognition completed; image understanding is not connected yet.' : '文字识别完成，画面理解暂未接入。'}</p>
              : captureItem?.error && <p className="capture-alert">{captureFailureLabel(captureItem.error, locale)}</p>}
            {captureItem && <div className="inbox-links"><button type="button" onClick={() => void openPreview(captureItem)}>{en ? 'Preview details' : '预览与详情'}</button><a href={`/api/inbox/${encodeURIComponent(item.captureId!)}/raw`} download>{en ? 'Download Raw' : '下载原件'}</a>{item.reviewPath && <button type="button" onClick={() => onReview(item.reviewPath!)}>{en ? 'View Review' : '查看 Review'}</button>}{item.status === 'partial_success' && !isImageOcrDescriptionUnavailable(captureItem) && <button type="button" onClick={() => void retryCapture(captureItem)}>{en ? 'Retry' : '重试处理'}</button>}</div>}
          </>}
          {item.source === 'notes' && item.readOnly && <p className="capture-processing-note">{en ? 'This source contains Markdown syntax that the rich-text editor cannot safely rewrite.' : '此来源包含富文本编辑器无法安全回写的 Markdown 特殊语法。'}</p>}
          {!classification ? <button type="button" className="unified-suggest-button" onClick={() => suggest(item)}>{text('ai', '')}</button> : <div className="unified-suggestion-list" aria-label={en ? 'Suggestions for human approval' : '待人工逐项审批的建议'}>
            <p className="unified-mock-boundary">{en ? 'Deterministic local demo only; no source or vocabulary changes are persisted.' : '仅本地确定性演示；不会持久化来源审批或词库变更。'}</p>
            <button type="button" className="unified-suggest-button" onClick={() => suggest(item)}>{en ? 'Regenerate Mock suggestions (preserve manual corrections)' : '重新生成 Mock 建议（保留手动修正）'}</button>
            {suggestions.map((suggestion) => <Proposal key={suggestion.kind} id={suggestion.kind} title={suggestion.title} reason={suggestion.reason} impact={suggestion.impact} preview={suggestion.preview} value={suggestion.value} en={en} decision={decisionsFor(suggestion.kind)} decisionRequired={suggestion.kind !== 'type' && suggestion.kind !== 'tags'}
              onChange={(value) => edit(item.id, suggestion.kind, value)} onApprove={() => decide(item, suggestion.kind, 'simulated_accepted')} onReject={() => decide(item, suggestion.kind, 'rejected')} />)}
          </div>}
        </article>;
      }) : <p className="capture-empty">{en ? 'Nothing is waiting in Inbox.' : '收件箱中暂无待处理内容。'}</p>}
    </div>
    {preview && <div className="capture-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setPreview(null); }}><section className="capture-modal capture-preview-modal" role="dialog" aria-modal="true" aria-labelledby="unified-capture-preview-title"><header><div><p className="eyebrow">SECONDBRAIN / INBOX</p><h2 id="unified-capture-preview-title">{preview.display_filename || preview.raw_path}</h2></div><button className="capture-close" onClick={() => setPreview(null)} aria-label={en ? 'Close' : '关闭'}>×</button></header><p>{captureStatusLabel(preview.status, locale)} · {preview.captured_at ? new Date(preview.captured_at).toLocaleString(en ? 'en-US' : 'zh-CN') : ''}</p><p>{preview.raw_path ? (en ? 'Raw preserved' : '原件已保存') : (en ? 'Raw unavailable' : '原件未保存')} · {preview.error ? captureFailureLabel(preview.error, locale) : (en ? 'No processing error' : '无处理错误')}</p>{preview.source_url && <dl><dt>{en ? 'Original URL' : '原始 URL'}</dt><dd>{preview.source_url}</dd>{preview.derived_source_url && <><dt>{en ? 'Fetched URL' : '实际获取地址'}</dt><dd>{preview.derived_source_url}</dd></>}</dl>}<div className="capture-preview-content">{previewKind(preview.raw_path) === 'text' && (previewError ? <p role="alert">{previewError}</p> : previewText === null ? <p>{en ? 'Loading preview…' : '正在读取预览…'}</p> : <pre>{previewText}</pre>)}{previewKind(preview.raw_path) === 'pdf' && <p><a href={`/api/inbox/${encodeURIComponent(preview.capture_id)}/preview`} target="_blank" rel="noreferrer">{en ? 'Open PDF preview' : '在新标签页预览 PDF'}</a></p>}{previewKind(preview.raw_path) === 'image' && <img src={`/api/inbox/${encodeURIComponent(preview.capture_id)}/preview`} alt={preview.display_filename || preview.raw_path} />}{previewKind(preview.raw_path) === 'audio' && <audio controls preload="metadata" src={`/api/inbox/${encodeURIComponent(preview.capture_id)}/preview`}>{en ? 'Audio playback is not supported by this browser.' : '当前浏览器不支持此音频。'}</audio>}{previewKind(preview.raw_path) === 'unsupported' && <p>{en ? 'This file type cannot be previewed here. Download the original file instead.' : '此类型暂不支持站内预览，可下载原件查看。'}</p>}</div><footer><a className="capture-secondary" href={`/api/inbox/${encodeURIComponent(preview.capture_id)}/raw`} download>{en ? 'Download original' : '下载原件'}</a>{preview.review_path && <button type="button" className="capture-primary" onClick={() => { onReview(preview.review_path!); setPreview(null); }}>{en ? 'View related Review' : '查看对应 Review'}</button>}<button type="button" className="capture-secondary" onClick={() => setPreview(null)}>{en ? 'Close' : '关闭'}</button></footer></section></div>}
  </section>;
}
