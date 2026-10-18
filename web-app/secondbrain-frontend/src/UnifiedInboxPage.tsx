import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { notesApi, type NoteCollection } from './api/notes';
import { makeUnifiedInboxId, suggestInboxClassification, type MockClassification, type UnifiedInboxItem } from './unified-inbox';

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
type Decision = { status: 'approved_recorded' | 'rejected' | 'stale'; value: string };
type ExecutionPreview = { status: string; proposal_id: string; kind: string; proposal_version: number; vocabulary_version: number | string; source_summary: { source_kind: string; source_ref: string; source_version: string; source_content_sha256: string }; target_action: string; target: { text: string; title?: string; date?: string }; preview_sha256: string };
type PersistedProposal = { proposal_id: string; source_kind?: string; source_id?: string; collection?: string; path?: string; kind: string; status: string; version: number; source_version: string; suggestion: { original: any; current: any }; target_execution_status: string; history?: { event: string; actor: string; at: string; version: number }[]; execution?: { status: string; target?: ExecutionPreview['target']; source_summary?: ExecutionPreview['source_summary']; target_uri?: string; target_status?: string; error_code?: string } };
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
  saving?: boolean;
  editError?: string;
  classificationOptions?: { type: string; types: string[]; tags: string[]; tagOptions: string[]; unknownTags: string[]; onTypeChange: (value: string) => void; onTagsChange: (value: string[]) => void };
  execution?: { status: string; kind: string; target?: ExecutionPreview['target']; sourceSummary?: ExecutionPreview['source_summary']; targetUri?: string; error?: string; onPrepare: () => Promise<ExecutionPreview['target']>; onExecute: (target: ExecutionPreview['target']) => Promise<void> };
};

function Proposal({ id, title, reason, impact, preview, value, decision, decisionRequired, onChange, onApprove, onReject, en, saving = false, editError = '', classificationOptions, execution }: ProposalProps) {
  const [draft, setDraft] = useState(value);
  const [executionTarget, setExecutionTarget] = useState<ExecutionPreview['target'] | undefined>(execution?.target);
  const [executing, setExecuting] = useState(false);
  const [executionError, setExecutionError] = useState('');
  useEffect(() => { setDraft(value); }, [value, decision, editError]);
  useEffect(() => { setExecutionTarget(execution?.target); }, [execution?.status, execution?.target]);
  const runExecution = async () => {
    if (!execution || !executionTarget || executing) return;
    setExecuting(true); setExecutionError('');
    try { await execution.onExecute(executionTarget); }
    catch (cause) { setExecutionError(cause instanceof Error ? cause.message : (en ? 'Execution failed. Reload and retry.' : '执行失败，请刷新后重试。')); }
    finally { setExecuting(false); }
  };
  const prepareExecution = async () => {
    if (!execution || executing) return;
    setExecuting(true); setExecutionError('');
    try { setExecutionTarget(await execution.onPrepare()); }
    catch (cause) { setExecutionError(cause instanceof Error ? cause.message : (en ? 'Preview failed. Reload and retry.' : '预览失败，请刷新重试。')); }
    finally { setExecuting(false); }
  };
  return <article className="unified-proposal" data-proposal={id}>
    <header><h4>{title}</h4><span>{en ? 'Mock AI suggestion' : '模拟 AI 建议'}</span></header>
    <p>{reason}</p>
    <p className="unified-proposal-impact">{en ? 'Impact scope' : '影响范围'}：{impact}</p>
    {classificationOptions ? <div className="unified-vocabulary-editor">
      <label>{en ? 'Suggested type (Core vocabulary)' : '建议类型（Core 集中词库）'}
        <select value={classificationOptions.type} onChange={(event) => classificationOptions.onTypeChange(event.target.value)} disabled={Boolean(decision) || saving || classificationOptions.types.length === 0}>
          {classificationOptions.types.map((type) => <option key={type} value={type}>{type}</option>)}
        </select>
      </label>
      <fieldset disabled={Boolean(decision) || saving}><legend>{en ? 'Active Core tags' : 'Core 词库中的有效标签'}</legend>
        {classificationOptions.tagOptions.map((tag) => <label key={tag}><input type="checkbox" checked={classificationOptions.tags.includes(tag)} onChange={(event) => {
          const next = event.target.checked ? [...classificationOptions.tags, tag] : classificationOptions.tags.filter((item) => item !== tag);
          classificationOptions.onTagsChange(classificationOptions.tagOptions.filter((item) => next.includes(item)));
        }} />{tag}</label>)}
      </fieldset>
      {classificationOptions.unknownTags.length > 0 && <p role="status">{en ? 'Unrecognized tag candidates; separate vocabulary approval is required:' : '未识别的标签候选；需单独审批词库：'} {classificationOptions.unknownTags.map((tag) => `#${tag}`).join(' ')}</p>}
      <small>{en ? 'Suggestions use the centralized Core vocabulary snapshot. New vocabulary is not applied by approving this content suggestion.' : '建议基于 Core 集中词库快照；批准内容建议不会批准或应用新词。'}</small>
    </div> : <><label>{en ? 'Editable proposal' : '可编辑建议'}
      <textarea value={draft} onChange={(event) => setDraft(event.target.value)} disabled={Boolean(decision) || saving} rows={3} />
    </label><button type="button" onClick={() => onChange(draft)} disabled={Boolean(decision) || saving || draft === value}>{saving ? (en ? 'Saving…' : '保存中…') : (en ? 'Save suggestion' : '保存建议')}</button></>}
    <small>{en ? 'Source preview' : '来源预览'}：{preview || (en ? 'No text preview available.' : '暂无正文预览。')}</small>
    {decision ? <p className={`unified-decision ${decision.status}`} role="status">
      {decision.status === 'stale' ? (en ? 'Source changed; regenerate and review again.' : '来源已变化；请重新生成并复核。')
        : decision.status === 'rejected'
          ? (en ? 'Rejected; original retained.' : '已拒绝；原始内容保留。')
          : (en ? 'Decision recorded in Core. This records approval only; it is not queued or executed.'
            : '决定已记录到 Core；这只记录审批，不会排队或执行。')}
    </p> : !decisionRequired ? <p className="unified-decision" role="status">{en
      ? 'Existing type and approved demo tags require no per-note approval under the product rule. Demo only: no metadata is written; unknown tag terms need separate vocabulary approval.'
      : '按产品规则，既有类型与 Core 词库中的有效标签无需逐条审批。本演示不会写回笔记属性；新词仅作为待词库审批候选。'}</p> : <footer>
      <button type="button" onClick={onApprove}>{en ? 'Record approval (not executed)' : '记录审批（不执行）'}</button>
      <button type="button" onClick={onReject}>{en ? 'Reject' : '拒绝'}</button>
    </footer>}
    {execution && decision?.status === 'approved_recorded' && <section className="unified-execution" aria-label={en ? 'Explicit target execution' : '明确执行目标'}>
      {execution.kind === 'project' ? <p role="status">{en ? 'NOT IMPLEMENTED: project association is metadata only and cannot execute.' : '尚未实现：项目关联仅作为元数据，不可执行。'}</p> : <>
        <p>{en ? 'Approval is recorded only. Review this exact target preview, then explicitly confirm execution.' : '审批记录本身不会执行。请核对以下目标预览，再明确确认执行。'}</p>
        {execution.status !== 'executed' && execution.status !== 'blocked' && !executionTarget && <button type="button" onClick={() => void prepareExecution()} disabled={executing}>{en ? 'Prepare target preview' : '准备目标预览'}</button>}
        {executionTarget && execution.status !== 'executed' && execution.status !== 'blocked' && <>
          {execution.sourceSummary && <p className="unified-execution-source">{en ? 'Source/version' : '来源 / 版本'}：{execution.sourceSummary.source_kind} · {execution.sourceSummary.source_ref} · {execution.sourceSummary.source_version} · SHA-256 {execution.sourceSummary.source_content_sha256}</p>}
          {executionTarget.title !== undefined && <label>{en ? 'Review title' : 'Review 标题'}<input value={executionTarget.title} onChange={(event) => setExecutionTarget({ ...executionTarget, title: event.target.value })} /></label>}
          {executionTarget.date !== undefined && <label>{en ? 'Journal date' : 'Journal 日期'}<input type="date" value={executionTarget.date} onChange={(event) => setExecutionTarget({ ...executionTarget, date: event.target.value })} /></label>}
          <label>{en ? 'Exact target text' : '目标正文（将按此内容写入）'}<textarea rows={5} value={executionTarget.text} onChange={(event) => setExecutionTarget({ ...executionTarget, text: event.target.value })} /></label>
          <button type="button" onClick={() => void runExecution()} disabled={executing || !executionTarget.text.trim()}>{executing ? (en ? 'Executing…' : '执行中…') : execution.status === 'failed_retryable' ? (en ? 'Confirm retry' : '确认重试') : (en ? 'Confirm and execute' : '确认并执行')}</button>
        </>}
        {execution.status === 'executed' && <p role="status">{en ? 'Executed' : '已执行'} · {execution.targetUri || execution.status}</p>}
        {execution.status === 'blocked' && <p role="alert" className="capture-alert">{en ? 'Blocked by a target conflict. This operation cannot be replayed; review the source and create a new proposal.' : '目标冲突导致执行已阻断；该操作不能重放，请重新核对来源并生成新建议。'}</p>}
        {executionError && <p role="alert" className="capture-alert">{executionError}</p>}
      </>}
    </section>}
  </article>;
}

export type SingleInboxSource = { collection: 'drafts'; path: string };

export function UnifiedInboxPage({ locale, onReview, showSyntheticCaptureDemo = import.meta.env.DEV, notesOnly = false, singleSourceMode = false, singleSource = null }: { locale: Locale; onReview: (reviewPath: string) => void; showSyntheticCaptureDemo?: boolean; notesOnly?: boolean; singleSourceMode?: boolean; singleSource?: SingleInboxSource | null }) {
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
  const suggestionKeys = useRef<Record<string, string>>({});
  const decisionKeys = useRef<Record<string, string>>({});
  const [classifications, setClassifications] = useState<Record<string, MockClassification>>({});
  const [edits, setEdits] = useState<Record<string, Record<string, string>>>({});
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [syntheticCaptures, setSyntheticCaptures] = useState<CaptureItem[]>([]);
  const [proposalRecords, setProposalRecords] = useState<Record<string, PersistedProposal[]>>({});
  const [proposalErrors, setProposalErrors] = useState<Record<string, string>>({});
  const [savingEdits, setSavingEdits] = useState<Record<string, boolean>>({});
  const [executionPreviews, setExecutionPreviews] = useState<Record<string, ExecutionPreview>>({});
  const [proposalHistory, setProposalHistory] = useState<Record<string, { event: string; actor: string; at: string; version: number }[]>>({});
  const [sourceBindingBlocked, setSourceBindingBlocked] = useState<Record<string, boolean>>({});
  const editInFlight = useRef(new Set<string>());

  const matchesSingleSource = useCallback((record: PersistedProposal, item: UnifiedInboxItem) =>
    record.source_kind === 'notes' && record.source_id === `${item.collection}:${item.sourcePath}`
    && record.collection === item.collection && record.path === item.sourcePath,
  []);
  const blockSourceBinding = (item: UnifiedInboxItem, message: string) => {
    setSourceBindingBlocked((current) => ({ ...current, [item.id]: true }));
    setProposalRecords((current) => ({ ...current, [item.id]: [] }));
    setClassifications((current) => { const next = { ...current }; delete next[item.id]; return next; });
    setProposalErrors((current) => ({ ...current, [item.id]: message }));
  };

  const load = useCallback(async (showLoading = false) => {
    if (showLoading) setLoading(true);
    setCaptureError(''); setNotesError('');
    if (singleSourceMode) {
      if (!singleSource || singleSource.collection !== 'drafts' || !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(singleSource.path)) {
        setNotes([]);
        setNotesError(en ? 'A valid Draft source is required. No Inbox sources were loaded.' : '必须提供有效的 Draft 来源；未加载任何收件箱来源。');
        setLoading(false);
        return;
      }
      try {
        const note = await notesApi.read(singleSource.collection, singleSource.path);
        if (note.collection !== singleSource.collection || note.path !== singleSource.path) {
          setCaptures([]); setNotes([]);
          setNotesError(en ? 'Core returned a different Draft; no Inbox source was shown.' : 'Core 返回了其他 Draft；未展示任何收件箱来源。');
          return;
        }
        setCaptures([]);
        setNotes([{
          id: makeUnifiedInboxId('notes', singleSource.collection, singleSource.path),
          source: 'notes', sourceRef: `${singleSource.collection}/${singleSource.path}`,
          sourcePath: singleSource.path, title: note.content.split(/\r?\n/).find((line) => line.startsWith('# '))?.slice(2).trim() || singleSource.path,
          content: note.content, collection: singleSource.collection, readOnly: note.read_only,
        }]);
      } catch {
        setCaptures([]); setNotes([]);
        setNotesError(en ? 'The selected Draft could not be read under the current Core session.' : '当前 Core 会话无法读取所选 Draft。');
      } finally { setLoading(false); }
      return;
    }
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
  }, [en, notesOnly, singleSourceMode, singleSource?.collection, singleSource?.path]);

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

  const refreshProposals = useCallback(async (item: UnifiedInboxItem, clearResolvedConflicts = false) => {
    if (item.captureId === 'synthetic-capture-demo') return;
    const params = new URLSearchParams({ source_kind: item.source === 'capture' ? 'capture' : 'notes', source_id: item.captureId || `${item.collection}:${item.sourcePath}` });
    if (item.source === 'notes') { params.set('collection', item.collection || ''); params.set('path', item.sourcePath); }
    const response = await fetch(`/api/inbox/proposals?${params}`, { credentials: 'same-origin' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    const records = Array.isArray(payload.proposals) ? payload.proposals as PersistedProposal[] : [];
    if (singleSourceMode && records.some((record) => !matchesSingleSource(record, item))) {
      blockSourceBinding(item, en ? 'Core returned a proposal bound to another source; all results were hidden.' : 'Core 返回了绑定到其他来源的提案；已隐藏全部结果。');
      return;
    }
    if (singleSourceMode) setSourceBindingBlocked((current) => ({ ...current, [item.id]: false }));
    setProposalRecords((current) => ({ ...current, [item.id]: records }));
    setProposalErrors((current) => ({ ...current, [item.id]: '' }));
    const byKind = new Map(records.map((record) => [record.kind, record]));
    const current = (kind: string) => byKind.get(kind)?.suggestion.current;
    const type = current('type')?.value;
    const tags = current('tags');
    if (records.length) {
      const mock = suggestInboxClassification(item.content, item.title);
      const classification = { ...mock, type: type ?? '', tags: tags?.values || [],
        unknownTagCandidates: tags?.unknown_candidates || [], allowedTypes: current('type')?.vocabulary_values || [],
        allowedTags: tags?.vocabulary_values || [] } as MockClassification;
      setClassifications((value) => ({ ...value, [item.id]: classification }));
      setEdits((value) => ({ ...value, [item.id]: { ...(value[item.id] || {}), type: classification.type, tags: classification.tags.join(', '),
        journal: current('journal')?.value ?? classification.journalExcerpt, knowledge: current('review')?.value ?? classification.knowledgeReview,
        project: current('project')?.value ?? classification.projectAssociation } }));
      for (const kind of ['journal', 'review', 'project']) {
        const record = byKind.get(kind);
        if (record && ['approved_recorded', 'rejected', 'stale'].includes(record.status)) {
          setDecisions((value) => ({ ...value, [`${item.id}:${kind === 'review' ? 'knowledge' : kind}`]: { status: record.status === 'stale' ? 'stale' : record.status === 'rejected' ? 'rejected' : 'approved_recorded', value: current(kind)?.value || '' } }));
        } else if (clearResolvedConflicts) {
          setDecisions((value) => { const key = `${item.id}:${kind === 'review' ? 'knowledge' : kind}`; if (value[key]?.status !== 'stale') return value; const next = { ...value }; delete next[key]; return next; });
        }
      }
      if (['type', 'tags'].some((kind) => byKind.get(kind)?.status === 'stale')) {
        setDecisions((value) => ({ ...value, [`${item.id}:classification`]: { status: 'stale', value: '' } }));
      } else if (clearResolvedConflicts) {
        setDecisions((value) => { const key = `${item.id}:classification`; if (value[key]?.status !== 'stale') return value; const next = { ...value }; delete next[key]; return next; });
      }
    }
  }, [singleSourceMode, matchesSingleSource, en]);

  useEffect(() => {
    for (const item of items) void refreshProposals(item).catch((cause) => setProposalErrors((current) => ({
      ...current,
      [item.id]: cause instanceof Error ? cause.message : (en ? 'Proposals could not be loaded.' : '建议加载失败。'),
    })));
  }, [items, refreshProposals]);

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

  const suggest = async (item: UnifiedInboxItem) => {
    if (item.captureId === 'synthetic-capture-demo') return;
    if (sourceBindingBlocked[item.id]) return;
    const source = item.source === 'capture' ? { source_kind: 'capture', source_id: item.captureId } : { source_kind: 'notes', source_id: `${item.collection}:${item.sourcePath}`, collection: item.collection, path: item.sourcePath };
    const idempotencyKey = suggestionKeys.current[item.id] || (suggestionKeys.current[item.id] = crypto.randomUUID());
    const response = await fetch('/api/inbox/proposals', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey }, body: JSON.stringify(source) });
    if (!response.ok) {
      if (response.status === 409) delete suggestionKeys.current[item.id];
      throw new Error(response.status === 409 ? (en ? 'The source changed or this request key was already used. Reload before generating suggestions.' : '来源已变化或请求键已使用，请刷新后重新生成建议。') : (en ? `Suggestions could not be saved (HTTP ${response.status}).` : `建议保存失败（HTTP ${response.status}）。`));
    }
    if (singleSourceMode) {
      const payload = await response.json();
      const records = Array.isArray(payload.proposals) ? payload.proposals as PersistedProposal[] : [];
      if (!records.length || records.some((record) => !matchesSingleSource(record, item))) {
        blockSourceBinding(item, en ? 'The proposal-create response did not match the selected source; controls are locked.' : '创建提案响应未绑定到所选来源；已锁定本来源操作。');
        throw new Error(en ? 'The response did not match the selected source.' : '响应未绑定到所选来源。');
      }
    }
    delete suggestionKeys.current[item.id];
    await refreshProposals(item);
  };
  const suggestSafely = (item: UnifiedInboxItem) => {
    void suggest(item).catch((cause) => setProposalErrors((current) => ({
      ...current,
      [item.id]: cause instanceof Error ? cause.message : (en ? 'Suggestions could not be saved.' : '建议保存失败。'),
    })));
  };
  const edit = async (item: UnifiedInboxItem, kind: string, value: string) => {
    const itemId = item.id;
    if (editInFlight.current.has(itemId)) return;
    editInFlight.current.add(itemId);
    setSavingEdits((current) => ({ ...current, [itemId]: true }));
    const recordKind = kind === 'knowledge' ? 'review' : kind;
    const record = proposalRecords[itemId]?.find((candidate) => candidate.kind === recordKind);
    if (!record) {
      editInFlight.current.delete(itemId);
      setSavingEdits((current) => ({ ...current, [itemId]: false }));
      return;
    }
    try {
      const suggestion = kind === 'type' ? { ...record.suggestion.current, value }
        : kind === 'tags' ? { ...record.suggestion.current, values: value.split(',').map((tag) => tag.trim()).filter(Boolean) }
          : { ...record.suggestion.current, value };
      const response = await fetch(`/api/inbox/proposals/${record.proposal_id}`, { method: 'PUT', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ suggestion, expected_version: record.version }) });
      if (!response.ok) {
        const conflict = response.status === 409 || response.status === 412;
        if (conflict) {
          const decisionKey = `${itemId}:${kind === 'type' || kind === 'tags' ? 'classification' : kind}`;
          setDecisions((current) => ({ ...current, [decisionKey]: { status: 'stale', value: '' } }));
        }
        await refreshProposals(item).catch(() => undefined);
        setProposalErrors((current) => ({ ...current, [itemId]: conflict
          ? (en ? 'Conflict: this source or suggestion changed. The local edit was not saved; reload and review again.' : '发生冲突：来源或建议已变化。本地修改未保存，请重新加载并复核。')
          : (en ? `Edit was not saved (HTTP ${response.status}).` : `修改未保存（HTTP ${response.status}）。`) }));
        return;
      }
      if (singleSourceMode) {
        const payload = await response.json();
        if (!payload.proposal || payload.proposal.proposal_id !== record.proposal_id || !matchesSingleSource(payload.proposal, item)) {
          blockSourceBinding(item, en ? 'Core returned an edit for a different source; controls are locked.' : 'Core 返回的修改结果不属于所选来源；已锁定本来源操作。');
          throw new Error(en ? 'Core returned an edit for a different source.' : 'Core 返回的修改结果不属于所选来源。');
        }
      }
      await refreshProposals(item);
      setProposalErrors((current) => ({ ...current, [itemId]: '' }));
    } catch (cause) {
      await refreshProposals(item).catch(() => undefined);
      setProposalErrors((current) => ({ ...current, [itemId]: cause instanceof Error ? cause.message : (en ? 'Edit was not saved.' : '修改未保存。') }));
    } finally {
      editInFlight.current.delete(itemId);
      setSavingEdits((current) => ({ ...current, [itemId]: false }));
    }
  };
  const editSafely = (item: UnifiedInboxItem, kind: string, value: string) => { void edit(item, kind, value); };
  const decide = async (item: UnifiedInboxItem, kind: string, status: Decision['status']) => {
    const key = `${item.id}:${kind}`;
    const recordKind = kind === 'knowledge' ? 'review' : kind;
    const record = proposalRecords[item.id]?.find((candidate) => candidate.kind === recordKind);
    if (!record || record.status !== 'suggested') return;
    const idempotencyKey = decisionKeys.current[record.proposal_id] || (decisionKeys.current[record.proposal_id] = crypto.randomUUID());
    const response = await fetch(`/api/inbox/proposals/${record.proposal_id}/decision`, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey }, body: JSON.stringify({ decision: status === 'rejected' ? 'rejected' : 'approved_recorded', expected_version: record.version }) });
    if (!response.ok) {
      if (response.status === 409 || response.status === 412) delete decisionKeys.current[record.proposal_id];
      await refreshProposals(item);
      setProposalErrors((current) => ({ ...current, [item.id]: response.status === 409 || response.status === 412 ? (en ? 'The source or proposal changed. Reload and review it again.' : '来源或建议已变化，请刷新并重新复核。') : (en ? `Decision could not be saved (HTTP ${response.status}).` : `审批记录保存失败（HTTP ${response.status}）。`) }));
      return;
    }
    if (singleSourceMode) {
      const payload = await response.json();
      if (!payload.proposal || payload.proposal.proposal_id !== record.proposal_id || !matchesSingleSource(payload.proposal, item)) {
        blockSourceBinding(item, en ? 'Core returned a decision for a different source; controls are locked.' : 'Core 返回的审批结果不属于所选来源；已锁定本来源操作。');
        throw new Error(en ? 'Core returned a decision for a different source.' : 'Core 返回的审批结果不属于所选来源。');
      }
    }
    delete decisionKeys.current[record.proposal_id];
    await refreshProposals(item);
    setProposalErrors((current) => ({ ...current, [item.id]: '' }));
  };
  const decideSafely = (item: UnifiedInboxItem, kind: string, status: Decision['status']) => {
    void decide(item, kind, status).catch((cause) => setProposalErrors((current) => ({ ...current, [item.id]: cause instanceof Error ? cause.message : (en ? 'Decision failed.' : '审批记录失败。') })));
  };

  const executeProposal = async (item: UnifiedInboxItem, record: PersistedProposal, target: ExecutionPreview['target']) => {
    const headers = { 'Content-Type': 'application/json' };
    const previewResponse = await fetch(`/api/inbox/proposals/${record.proposal_id}/execution-preview`, { method: 'POST', credentials: 'same-origin', headers, body: JSON.stringify({ target_text: target.text, ...(target.title !== undefined ? { target_title: target.title } : {}), ...(target.date !== undefined ? { target_date: target.date } : {}) }) });
    const preview = await previewResponse.json().catch(() => ({}));
    if (!previewResponse.ok || preview.status !== 'ready') {
      await refreshProposals(item).catch(() => undefined);
      throw new Error(en ? `Preview unavailable (HTTP ${previewResponse.status}); reload and review again.` : `预览不可用（HTTP ${previewResponse.status}），请刷新并重新核对。`);
    }
    if (singleSourceMode && (preview.proposal_id !== record.proposal_id || preview.source_summary?.source_kind !== 'notes'
      || preview.source_summary?.source_ref !== item.sourcePath || preview.source_summary?.source_version !== record.source_version
      || (record.kind === 'journal' ? preview.target_action !== 'journal.append' : record.kind === 'review' ? preview.target_action !== 'capture.write' : true))) {
      blockSourceBinding(item, en ? 'The target preview is not bound to the selected source; controls are locked.' : '目标预览未绑定到所选来源；已锁定本来源操作。');
      throw new Error(en ? 'The target preview is not bound to the selected source.' : '目标预览未绑定到所选来源。');
    }
    setExecutionPreviews((current) => ({ ...current, [record.proposal_id]: preview as ExecutionPreview }));
    const response = await fetch(`/api/inbox/proposals/${record.proposal_id}/execute`, { method: 'POST', credentials: 'same-origin', headers, body: JSON.stringify({ target_text: target.text, ...(target.title !== undefined ? { target_title: target.title } : {}), ...(target.date !== undefined ? { target_date: target.date } : {}), confirmed: true, preview_sha256: preview.preview_sha256 }) });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      await refreshProposals(item).catch(() => undefined);
      throw new Error(response.status === 409 ? (en ? 'Conflict: source, vocabulary, or preview changed. Reload and review again.' : '执行冲突：来源、词库或预览已变化，请刷新后重新核对。') : (en ? `Execution failed (HTTP ${response.status}); retry the same preview if allowed.` : `执行失败（HTTP ${response.status}）；如允许，请对同一预览重试。`));
    }
    if (singleSourceMode && (!payload.proposal || payload.proposal.proposal_id !== record.proposal_id || !matchesSingleSource(payload.proposal, item))) {
      blockSourceBinding(item, en ? 'Core returned an execution for a different source; controls are locked.' : 'Core 返回的执行结果不属于所选来源；已锁定本来源操作。');
      throw new Error(en ? 'Core returned an execution for a different source.' : 'Core 返回的执行结果不属于所选来源。');
    }
    setProposalRecords((current) => ({ ...current, [item.id]: (current[item.id] || []).map((row) => row.proposal_id === record.proposal_id ? payload.proposal : row) }));
    setExecutionPreviews((current) => { const next = { ...current }; delete next[record.proposal_id]; return next; });
    await refreshProposals(item);
  };
  const prepareProposal = async (record: PersistedProposal) => {
    const response = await fetch(`/api/inbox/proposals/${record.proposal_id}/execution-preview`, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    const preview = await response.json().catch(() => ({}));
    if (!response.ok || preview.status !== 'ready') {
      const item = items.find((candidate) => proposalRecords[candidate.id]?.some((row) => row.proposal_id === record.proposal_id));
      if (item) await refreshProposals(item).catch(() => undefined);
      throw new Error(en ? `Preview unavailable (HTTP ${response.status}); reload and review again.` : `预览不可用（HTTP ${response.status}），请刷新并重新核对。`);
    }
    const item = items.find((candidate) => proposalRecords[candidate.id]?.some((row) => row.proposal_id === record.proposal_id));
    if (singleSourceMode && (!item || preview.proposal_id !== record.proposal_id || preview.source_summary?.source_kind !== 'notes'
      || preview.source_summary?.source_ref !== item.sourcePath || preview.source_summary?.source_version !== record.source_version
      || (record.kind === 'journal' ? preview.target_action !== 'journal.append' : record.kind === 'review' ? preview.target_action !== 'capture.write' : true))) {
      if (item) blockSourceBinding(item, en ? 'The target preview is not bound to the selected source; controls are locked.' : '目标预览未绑定到所选来源；已锁定本来源操作。');
      throw new Error(en ? 'The target preview is not bound to the selected source.' : '目标预览未绑定到所选来源。');
    }
    setExecutionPreviews((current) => ({ ...current, [record.proposal_id]: preview as ExecutionPreview }));
    return (preview as ExecutionPreview).target;
  };

  const loadHistory = async (item: UnifiedInboxItem, record: PersistedProposal) => {
    const response = await fetch(`/api/inbox/proposals/${encodeURIComponent(record.proposal_id)}/history`, { credentials: 'same-origin' });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.proposal || !Array.isArray(payload.history)) throw new Error(en ? `History unavailable (HTTP ${response.status}).` : `审批历史不可用（HTTP ${response.status}）。`);
    if (singleSourceMode && (payload.proposal.proposal_id !== record.proposal_id || !matchesSingleSource(payload.proposal, item))) {
      blockSourceBinding(item, en ? 'Core returned history for a different source; controls are locked.' : 'Core 返回的历史记录不属于所选来源；已锁定本来源操作。');
      throw new Error(en ? 'Core returned history for a different source.' : 'Core 返回的历史记录不属于所选来源。');
    }
    setProposalHistory((current) => ({ ...current, [record.proposal_id]: payload.history }));
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

  return <section className={notesOnly || singleSourceMode ? 'unified-notes-inbox' : 'capture-page unified-inbox-page'} aria-labelledby="unified-inbox-title">
    {!notesOnly && <header className="capture-page-header"><div><p className="eyebrow">SECONDBRAIN <span>/</span> {singleSourceMode ? 'INBOX / SOURCE' : 'INBOX'}</p><h1 id="unified-inbox-title">{singleSourceMode ? (en ? 'Single-source Inbox review' : '单来源 Inbox 审批') : text('inbox', '统一收件箱')}</h1><p className="workspace-subtitle">{singleSourceMode
        ? singleSource ? `${en ? 'Only this Draft is in scope' : '当前范围仅限此 Draft'}：${singleSource.collection}/${singleSource.path}` : (en ? 'Missing or invalid Draft source; no source was loaded.' : 'Draft 来源缺失或无效；未加载任何来源。')
        : text('subtitle', '')}</p>{!singleSourceMode && <p className="unified-inbox-boundary">{text('local', '')}</p>}</div>
      {!singleSourceMode && showSyntheticCaptureDemo && <button type="button" className="capture-secondary" onClick={addSyntheticCapture}>{en ? 'Add synthetic Capture' : '添加合成 Capture 示例'}</button>}
    </header>}
    {notesOnly && <div className="unified-inbox-subheader"><h2 id="unified-inbox-title">{en ? 'Notes drafts' : '笔记草稿'}</h2>{showSyntheticCaptureDemo && <button type="button" className="capture-secondary" onClick={addSyntheticCapture}>{en ? 'Add synthetic Capture' : '添加合成 Capture 示例'}</button>}</div>}
    {singleSourceMode && <p className="unified-mock-boundary">{en ? 'This isolated route never loads the full Inbox or lists Notes/Capture sources.' : '此隔离页面不会加载全量 Inbox，也不会枚举 Notes 或 Capture 来源。'}</p>}
    {!singleSourceMode && <form className="unified-note-create" onSubmit={(event) => void createNote(event)}>
      <h2>{text('createTitle', '')}</h2>
      <label>{en ? 'Title' : '标题'}<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={160} required /></label>
      <label>{en ? 'Content' : '正文'}<textarea value={body} onChange={(event) => setBody(event.target.value)} rows={3} maxLength={200000} required /></label>
      {createError && <p role="alert" className="capture-alert">{createError}</p>}
      <button type="submit" disabled={creating || !title.trim() || !body.trim()}>{creating ? (en ? 'Saving…' : '保存中…') : text('create', '')}</button>
    </form>}
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
          {proposalErrors[item.id] && <p role="alert" className="capture-alert">{proposalErrors[item.id]} <button type="button" onClick={() => void refreshProposals(item, true).catch(() => setProposalErrors((current) => ({ ...current, [item.id]: en ? 'Reload failed; check the Core session and retry.' : '重新加载失败，请检查 Core 会话后重试。' })))}>{en ? 'Reload proposals' : '重新加载建议'}</button></p>}
          <div className="inbox-links">{item.source === 'capture' && item.captureId && !item.sourcePath.startsWith('synthetic://') && <a href={`/api/inbox/${encodeURIComponent(item.captureId)}/raw`} download>{en ? 'Download original' : '下载原件'}</a>}{item.reviewPath && <button type="button" onClick={() => onReview(item.reviewPath!)}>{en ? 'Open Review' : '打开 Review'}</button>}</div>
          {!classification ? <button type="button" className="unified-suggest-button" disabled={Boolean(sourceBindingBlocked[item.id])} onClick={() => suggestSafely(item)}>{text('ai', '')}</button> : <div className="unified-suggestion-list" aria-label={en ? 'Suggestions for human approval' : '待人工逐项审批的建议'}>
            <p className="unified-mock-boundary">{en ? 'Deterministic local Mock only. Suggestions and human decisions are persisted by Core; approval never executes a target action.' : '仅确定性本地 Mock。建议和人工决定由 Core 持久化；审批不会执行目标动作。'}</p>
            <button type="button" className="unified-suggest-button" disabled={Boolean(sourceBindingBlocked[item.id])} onClick={() => suggestSafely(item)}>{en ? 'Regenerate Mock suggestions (preserve manual corrections)' : '重新生成 Mock 建议（保留手动修正）'}</button>
            {suggestions.map((suggestion) => <Proposal key={suggestion.kind} id={suggestion.kind} title={suggestion.title} reason={suggestion.reason} impact={suggestion.impact} preview={suggestion.preview} value={suggestion.value} en={en} saving={savingEdits[item.id]} editError={proposalErrors[item.id]} decision={decisionsFor(suggestion.kind)} decisionRequired={suggestion.kind !== 'classification'}
              classificationOptions={suggestion.kind === 'classification' ? { type: values.type ?? classification.type, types: classification.allowedTypes || [], tags: (values.tags ?? classification.tags.join(', ')).split(/,\s*/).filter((tag) => (classification.allowedTags || []).includes(tag)), tagOptions: classification.allowedTags || [], unknownTags: classification.unknownTagCandidates, onTypeChange: (value) => editSafely(item, 'type', value), onTagsChange: (tags) => editSafely(item, 'tags', tags.join(', ')) } : undefined}
              execution={['journal', 'knowledge', 'project'].includes(suggestion.kind) ? (() => { const kind = suggestion.kind === 'knowledge' ? 'review' : suggestion.kind; const record = proposalRecords[item.id]?.find((candidate) => candidate.kind === kind); if (!record || record.status !== 'approved_recorded') return undefined; const execution = record.execution || { status: record.target_execution_status }; const preview = executionPreviews[record.proposal_id]; const previewTarget = preview?.target || execution.target; const sourceSummary = preview?.source_summary || execution.source_summary; return { status: execution.status, kind, target: previewTarget, sourceSummary, targetUri: execution.target_uri, error: execution.error_code, onPrepare: () => prepareProposal(record), onExecute: (target: ExecutionPreview['target']) => executeProposal(item, record, target) }; })() : undefined}
              onChange={(value) => editSafely(item, suggestion.kind, value)} onApprove={() => decideSafely(item, suggestion.kind, 'approved_recorded')} onReject={() => decideSafely(item, suggestion.kind, 'rejected')} />)}
            {singleSourceMode && proposalRecords[item.id]?.map((record) => <section className="single-source-history" key={`${record.proposal_id}-history`} aria-label={`${record.kind} audit history`}>
              <button type="button" onClick={() => { void loadHistory(item, record).catch((cause) => setProposalErrors((current) => ({
                ...current, [item.id]: cause instanceof Error ? cause.message : (en ? 'History unavailable.' : '审批历史不可用。'),
              }))); }}>{en ? `View ${record.kind} audit history` : `查看 ${record.kind} 审计历史`}</button>
              {(proposalHistory[record.proposal_id] || []).map((event, index) => <p role="status" key={`${event.event}-${event.version}-${index}`}>{event.event} · {event.at} · v{event.version}</p>)}
            </section>)}
          </div>}
        </article>;
      }) : <p className="capture-empty">{en ? 'Nothing is waiting in Inbox.' : '收件箱中暂无待处理内容。'}</p>}
    </div>
  </section>;
}
