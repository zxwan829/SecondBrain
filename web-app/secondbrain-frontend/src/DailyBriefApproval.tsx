import React, { useEffect, useRef, useState } from 'react';
import { JournalSourcePicker } from './JournalSourcePicker';
import { parseDailyBriefResponse, parseProjectsResponse, type DailyBriefRecord, type ProjectRecord } from './projects-brief-wire';

type Locale = 'zh-CN' | 'en';
type SourceRef = { kind: 'task' | 'project' | 'journal'; id: string; version: string };
type SourceChoice = { key: string; label: string; ref: SourceRef; sourceDate?: string };
type WriteReceipt = { status: 'created' | 'duplicate'; brief_id: string; date: string; timezone: 'Asia/Shanghai'; record_version: string; operation_id: string };
type ManualBriefRequest = {
  mode: 'manual_generate'; date: string; timezone: 'Asia/Shanghai'; idempotency_key: string;
  categories: string[]; summary: string; source_refs: SourceRef[]; approved: true;
};
type StoredPending = { body: ManualBriefRequest; receipt: WriteReceipt | null };
type Phase = 'idle' | 'loading-sources' | 'editing' | 'confirming' | 'submitting' | 'unknown' | 'resolving-unknown' | 'unknown-date-blocked' | 'unknown-date-match' | 'done';
type ReadbackState = 'pending' | 'verified' | 'matched-content-unconfirmed' | 'unavailable' | 'stale' | 'empty' | 'mismatch';
const TASK_SOURCE_VERSION_FIELDS = ['id', 'title', 'due_date', 'status', 'created_at', 'updated_at', 'source'] as const;
const PENDING_STORAGE_KEY = 'secondbrain.dailyBrief.pending.v1';

const text = {
  'zh-CN': {
    start: '手动准备简报', cancel: '取消', loading: '正在读取可核验的任务与项目…',
    title: '手动创建每日简报', sourceHeading: '选择本次简报来源', journalNote: 'Journal 仅返回 Core 核验过的来源元数据，不读取正文。点击“加载 Journal 来源”后才会发起只读请求。',
    summary: '简报正文（由你编写并确认）', summaryPlaceholder: '仅填写基于下方已选来源的内容；不会调用模型。',
    categories: '分类（逗号分隔）', categoriesPlaceholder: '今日任务', prepare: '预览并确认',
    confirmationTitle: '确认要保存这份简报？', confirmationBody: '这是你手动编写的文本；只有点击下面的确认按钮后，页面才会提交一次保存请求。未知结果时，请求正文和幂等键仅暂存于当前标签页 sessionStorage，以便安全恢复。',
    confirm: '确认并创建简报', submitting: '正在保存…', retry: '用同一请求安全重试', checkOriginalDate: '只读核对原日期结果', retryReadback: '只读重试当前状态核验',
    writePending: '写入已确认，当前回读待核验。', writeUnavailable: '写入已确认，当前回读不可用；可只读重试核验，不会重发写入。',
    currentVerified: '当前简报已核验：Brief 和来源版本与本次提交一致。', currentStale: '写入已确认，但当前来源已失效或变化；Core 未提供可信当前内容。', currentEmpty: '写入已确认，但当前日期没有对应记录；尚不能核验本次结果。', currentMismatch: '写入已确认，但当前回读与提交内容不匹配；未将回读视为本次结果。',
    unknown: '写入结果未知。请求正文和幂等键已保留；只能用相同请求重试。', resolving: '业务日期已变化，正在只读核对原日期；不会重放旧写入。', unknownDate: '旧日期结果仍未知或不可核验。没有重发请求；可只读重试核对，不能自动改日期或内容。',
    unknownDateMatch: '当前可读取到内容与原请求匹配的简报，但无法确认它由原 POST 创建。原 POST 结果仍未知；原请求正文和幂等键已保留。只能继续只读核对，不会清除或重发请求。',
    saved: '写入已确认，当前回读待核验。', duplicate: '写入已确认（Core 判定为相同请求的重复回执），当前回读待核验。',
    noSources: '当前没有可核验的任务、项目或日记来源。', loadFailed: '来源读取失败；没有提交简报。',
    invalid: '请至少选择一个可核验来源，并填写正文。', dateChanged: '上海日期已变化。请核对更新后的日期与来源并重新预览确认；尚未提交。',
    journalDateChanged: '所选 Journal 来源不属于当前上海业务日期。请重新加载来源并重新预览确认。',
    conflict: 'Core 检测到同日或同幂等键冲突。已刷新当前简报状态；没有覆盖已有记录。',
    auth: '登录或写入权限已失效。请重新登录；本次请求未获成功回执。',
    invalidRequest: '请求未通过 Core 校验。请重新核对来源与内容；Journal 来源可能已变化，请重新加载并选择。',
    unavailable: 'Core 暂不可用。结果尚未确认；可用同一请求安全重试。',
    storageUnavailable: '浏览器当前标签页不能安全暂存未知请求，因此未发送任何保存请求。',
  },
  en: {
    start: 'Prepare a brief manually', cancel: 'Cancel', loading: 'Loading verifiable Tasks and Projects…',
    title: 'Create a daily brief manually', sourceHeading: 'Select sources for this brief', journalNote: 'Journal returns only Core-verified source metadata, not entry text. The read-only request runs only when you select “Load Journal sources.”',
    summary: 'Brief text (written and confirmed by you)', summaryPlaceholder: 'Use only the selected sources. No model is called.',
    categories: 'Categories (comma-separated)', categoriesPlaceholder: 'Today’s tasks', prepare: 'Review and confirm',
    confirmationTitle: 'Save this brief?', confirmationBody: 'You wrote this text. One save request is sent only after you confirm below. If its result is unknown, the exact body and idempotency key are kept in this tab’s sessionStorage for safe recovery.',
    confirm: 'Confirm and create brief', submitting: 'Saving…', retry: 'Retry the same request safely', checkOriginalDate: 'Check the original date (read only)', retryReadback: 'Retry current-state check (read only)',
    writePending: 'Write confirmed; current readback is pending.', writeUnavailable: 'Write confirmed; current readback is unavailable. Retry the read only; the write will not be repeated.',
    currentVerified: 'Current brief verified: the brief and source versions match this submission.', currentStale: 'Write confirmed, but current sources are stale or changed; Core did not provide trusted current content.', currentEmpty: 'Write confirmed, but no matching record exists for this date; this result is not verified.', currentMismatch: 'Write confirmed, but the current readback does not match this submission; it is not treated as this result.',
    unknown: 'Write result unknown. The exact request body and idempotency key are retained; retry only the same request.', resolving: 'The business date changed. Checking the original date read-only; the old write will not be replayed.', unknownDate: 'The old-date result remains unknown or unverifiable. Nothing was resubmitted; retry the read only. The request will not be changed automatically.',
    unknownDateMatch: 'A current brief matching the original request is readable, but this cannot establish that the original POST created it. The POST result remains unknown; the exact body and idempotency key are retained. You can only repeat the read check; the request will not be cleared or resubmitted.',
    saved: 'Write confirmed; current readback is pending.', duplicate: 'Write confirmed (Core returned a duplicate receipt for the same request); current readback is pending.',
    noSources: 'No verifiable Task, Project, or Journal sources are currently selected.', loadFailed: 'Could not read sources; no brief was submitted.',
    invalid: 'Select at least one verifiable source and enter the brief text.', dateChanged: 'The Shanghai date changed. Review the updated date and sources, then preview and confirm again; nothing was submitted.',
    journalDateChanged: 'The selected Journal source is not for the current Shanghai business date. Reload sources and review the brief again.',
    conflict: 'Core reported a same-day or idempotency conflict. Current brief state was refreshed; no record was overwritten.',
    auth: 'Sign-in or write permission expired. Sign in again; this request did not receive a success receipt.',
    invalidRequest: 'Core rejected the request. Review its sources and content; a Journal source may have changed, so reload and reselect it.',
    unavailable: 'Core is unavailable. The result is unconfirmed; retry the same request safely.',
    storageUnavailable: 'This browser tab cannot safely retain the unknown request, so no save request was sent.',
  },
} as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function shanghaiDate(now = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now);
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? '';
  return `${get('year')}-${get('month')}-${get('day')}`;
}

function isCalendarDate(value: unknown): value is string {
  if (typeof value !== 'string') return false;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return false;
  const year = Number(match[1]); const month = Number(match[2]); const day = Number(match[3]);
  if (year < 1 || month < 1 || month > 12) return false;
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return day >= 1 && day <= days[month - 1];
}

function isCoreTaskTimestamp(value: unknown): value is string {
  if (typeof value !== 'string') return false;
  const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?(Z|([+-])(\d{2}):(\d{2}))$/.exec(value);
  if (!match || !isCalendarDate(match[1])) return false;
  const hour = Number(match[2]); const minute = Number(match[3]); const second = Number(match[4]);
  const offsetHour = match[8] ? Number(match[8]) : 0; const offsetMinute = match[9] ? Number(match[9]) : 0;
  return hour <= 23 && minute <= 59 && second <= 59 && offsetHour <= 23 && offsetMinute <= 59
    && Number.isFinite(Date.parse(value));
}

async function taskReference(task: Record<string, unknown>): Promise<SourceRef | null> {
  if (typeof task.source !== 'string') throw new Error('task_source_unverifiable');
  if (task.source !== 'web_app_explicit_task') return null;
  if (TASK_SOURCE_VERSION_FIELDS.some((key) => !Object.hasOwn(task, key))
    || typeof task.id !== 'string' || !/^[0-9a-f]{32}$/.test(task.id)
    || typeof task.title !== 'string' || !task.title.trim()
    || (task.due_date !== null && !isCalendarDate(task.due_date))
    || (task.status !== 'open' && task.status !== 'completed')
    || !isCoreTaskTimestamp(task.created_at) || !isCoreTaskTimestamp(task.updated_at)) {
    throw new Error('task_source_unverifiable');
  }
  const titleBytes = new TextEncoder().encode(task.title);
  if (titleBytes.length > 4096 || new TextDecoder('utf-8', { fatal: true }).decode(titleBytes) !== task.title) {
    throw new Error('task_source_unverifiable');
  }
  // Match Python json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(',', ':')).
  const canonical = JSON.stringify(Object.fromEntries([...TASK_SOURCE_VERSION_FIELDS].sort().map((key) => [key, task[key]])));
  const canonicalBytes = new TextEncoder().encode(canonical);
  if (new TextDecoder('utf-8', { fatal: true }).decode(canonicalBytes) !== canonical) throw new Error('task_source_unverifiable');
  const digest = await crypto.subtle.digest('SHA-256', canonicalBytes);
  const version = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
  return { kind: 'task', id: task.id, version };
}

function parseReceipt(value: unknown, expectedDate: string): WriteReceipt | null {
  const keys = ['status', 'brief_id', 'date', 'timezone', 'record_version', 'operation_id'];
  if (!isRecord(value) || Object.keys(value).length !== keys.length || Object.keys(value).some((key) => !keys.includes(key))
    || (value.status !== 'created' && value.status !== 'duplicate')
    || typeof value.brief_id !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(value.brief_id)
    || value.date !== expectedDate || value.timezone !== 'Asia/Shanghai'
    || typeof value.record_version !== 'string' || !/^[a-f0-9]{64}$/.test(value.record_version)
    || typeof value.operation_id !== 'string' || !/^dbi-[a-f0-9]{64}$/.test(value.operation_id)) return null;
  return value as WriteReceipt;
}

function isSourceRef(value: unknown): value is SourceRef {
  return isRecord(value) && Object.keys(value).length === 3
    && ['kind', 'id', 'version'].every((key) => Object.hasOwn(value, key))
    && ['task', 'project', 'journal'].includes(String(value.kind))
    && typeof value.id === 'string' && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(value.id)
    && typeof value.version === 'string' && /^[a-f0-9]{64}$/.test(value.version);
}

function parseManualRequest(value: unknown): ManualBriefRequest | null {
  const keys = ['mode', 'date', 'timezone', 'idempotency_key', 'categories', 'summary', 'source_refs', 'approved'];
  if (!isRecord(value) || Object.keys(value).length !== keys.length || !keys.every((key) => Object.hasOwn(value, key))
    || value.mode !== 'manual_generate' || !isCalendarDate(value.date) || value.timezone !== 'Asia/Shanghai'
    || typeof value.idempotency_key !== 'string' || !/^ui-[A-Za-z0-9-]{16,128}$/.test(value.idempotency_key)
    || !Array.isArray(value.categories) || value.categories.length > 30
    || !value.categories.every((item) => typeof item === 'string' && item.trim().length > 0 && item.length <= 80)
    || typeof value.summary !== 'string' || !value.summary.trim() || value.summary.length > 20000
    || !Array.isArray(value.source_refs) || value.source_refs.length < 1 || value.source_refs.length > 50
    || !value.source_refs.every(isSourceRef) || value.approved !== true) return null;
  const refs = value.source_refs as SourceRef[];
  if (new Set(refs.map((ref) => `${ref.kind}:${ref.id}`)).size !== refs.length) return null;
  return value as unknown as ManualBriefRequest;
}

function readPending(): StoredPending | null {
  try {
    const raw = window.sessionStorage.getItem(PENDING_STORAGE_KEY);
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    if (!isRecord(value) || Object.keys(value).length !== 2 || !Object.hasOwn(value, 'body') || !Object.hasOwn(value, 'receipt')) return null;
    const body = parseManualRequest(value.body);
    const receipt = value.receipt === null ? null : parseReceipt(value.receipt, body?.date ?? '');
    return body && (value.receipt === null || receipt) ? { body, receipt } : null;
  } catch { return null; }
}

function savePending(body: ManualBriefRequest, receipt: WriteReceipt | null): boolean {
  try {
    window.sessionStorage.setItem(PENDING_STORAGE_KEY, JSON.stringify({ body, receipt }));
    return true;
  } catch { return false; }
}

function clearPending() {
  try { window.sessionStorage.removeItem(PENDING_STORAGE_KEY); } catch { /* storage cleanup is best effort */ }
}

function matchesRequest(record: DailyBriefRecord, body: ManualBriefRequest, receipt?: WriteReceipt | null): boolean {
  return record.date === body.date && record.timezone === body.timezone
    && record.generation_status === 'generated'
    && record.summary === body.summary
    && JSON.stringify(record.categories) === JSON.stringify(body.categories)
    && JSON.stringify(record.source_refs) === JSON.stringify(body.source_refs)
    && (!receipt || record.brief_id === receipt.brief_id);
}

async function loadSources(): Promise<SourceChoice[]> {
  const [taskResponse, projectResponse] = await Promise.all([
    fetch('/api/tasks?status=all', { credentials: 'same-origin', headers: { Accept: 'application/json' } }),
    fetch('/api/projects?limit=50&offset=0', { credentials: 'same-origin', headers: { Accept: 'application/json' } }),
  ]);
  if (!taskResponse.ok || !projectResponse.ok) throw new Error('source_read_failed');
  const [taskPayload, projectPayload] = await Promise.all([taskResponse.json(), projectResponse.json()]);
  if (!isRecord(taskPayload) || !Array.isArray(taskPayload.tasks) || taskPayload.tasks.length > 200) throw new Error('source_read_failed');
  const projects = parseProjectsResponse(projectPayload, 50, 0);
  if (!projects || projects.pagination.has_more || !['real', 'empty'].includes(projects.status)) throw new Error('source_read_failed');
  const tasks: SourceChoice[] = [];
  for (const item of taskPayload.tasks) {
    if (!isRecord(item)) throw new Error('source_read_failed');
    const ref = await taskReference(item);
    if (ref) tasks.push({ key: `${ref.kind}:${ref.id}`, label: item.title as string, ref });
  }
  const projectChoices = projects.items.map((project: ProjectRecord) => ({
    key: `project:${project.id}`, label: project.title,
    ref: { kind: 'project' as const, id: project.source_ref.id, version: project.source_ref.version },
  }));
  return [...tasks, ...projectChoices];
}

export function DailyBriefApproval({ locale, onSaved, dateNow = () => new Date() }: { locale: Locale; onSaved: () => void; dateNow?: () => Date }) {
  const copy = text[locale];
  const initialPending = useRef<StoredPending | null | undefined>(undefined);
  if (initialPending.current === undefined) initialPending.current = readPending() ?? null;
  const restored = initialPending.current;
  const [phase, setPhase] = useState<Phase>(restored?.receipt ? 'done' : restored ? 'unknown' : 'idle');
  const [sources, setSources] = useState<SourceChoice[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [summary, setSummary] = useState('');
  const [categories, setCategories] = useState('');
  const [error, setError] = useState('');
  const [receipt, setReceipt] = useState<WriteReceipt | null>(restored?.receipt ?? null);
  const [savedRequest, setSavedRequest] = useState<ManualBriefRequest | null>(restored?.body ?? null);
  const [readbackState, setReadbackState] = useState<ReadbackState | null>(restored?.receipt ? 'pending' : null);
  const submitting = useRef(false);
  const mounted = useRef(true);
  const readbackController = useRef<AbortController | null>(null);
  const getBusinessDate = () => shanghaiDate(dateNow());
  const [businessDate, setBusinessDate] = useState(() => getBusinessDate());

  useEffect(() => {
    mounted.current = true;
    return () => {
    mounted.current = false;
    readbackController.current?.abort();
    };
  }, []);

  function invalidateRequest() { setSavedRequest(null); setReceipt(null); setReadbackState(null); clearPending(); }

  async function begin() {
    setPhase('loading-sources'); setError(''); setReceipt(null); setReadbackState(null); setSelected([]); setBusinessDate(getBusinessDate()); clearPending(); setSavedRequest(null);
    try { const values = await loadSources(); if (mounted.current) { setSources(values); setPhase('editing'); } }
    catch { if (mounted.current) { setSources([]); setError(copy.loadFailed); setPhase('idle'); } }
  }

  function onJournalSelectionChange(items: Array<{ kind: 'journal'; id: string; date: string; version: string }>, sourceDate: string) {
    const choices: SourceChoice[] = items.map((item) => ({
      key: `journal:${item.id}`, label: `Journal · ${item.date} · ${item.id.slice(-8)}`,
      ref: { kind: 'journal', id: item.id, version: item.version }, sourceDate,
    }));
    setSources((current) => [...current.filter((source) => source.ref.kind !== 'journal'), ...choices]);
    setSelected((current) => [...current.filter((key) => !key.startsWith('journal:')), ...choices.map((source) => source.key)]);
    invalidateRequest();
    setError('');
  }

  function updateSummary(value: string) { setSummary(value); invalidateRequest(); }
  function updateCategories(value: string) { setCategories(value); invalidateRequest(); }
  function toggleSource(key: string) {
    setSelected((current) => current.includes(key) ? current.filter((item) => item !== key) : [...current, key]);
    invalidateRequest();
  }

  function clearJournalChoices() {
    setSources((current) => current.filter((source) => source.ref.kind !== 'journal'));
    setSelected((current) => current.filter((key) => !key.startsWith('journal:')));
  }

  function confirmDraft() {
    const selectedSources = sources.filter((source) => selected.includes(source.key));
    if (!summary.trim() || summary.length > 20000 || selectedSources.length < 1 || selectedSources.length > 50) { setError(copy.invalid); return; }
    const categoryList = categories.split(',').map((item) => item.trim()).filter(Boolean);
    if (categoryList.length > 30 || categoryList.some((item) => item.length > 80)) { setError(copy.invalid); return; }
    const today = getBusinessDate();
    if (today !== businessDate) {
      clearJournalChoices(); setBusinessDate(today); invalidateRequest(); setError(copy.dateChanged); setPhase('editing'); return;
    }
    if (selectedSources.some((source) => source.ref.kind === 'journal' && source.sourceDate !== businessDate)) {
      clearJournalChoices(); invalidateRequest(); setError(copy.journalDateChanged); setPhase('editing'); return;
    }
    setError(''); setPhase('confirming');
  }

  async function requestCurrentRead(body: ManualBriefRequest, expectedReceipt: WriteReceipt | null): Promise<ReadbackState> {
    readbackController.current?.abort();
    const controller = new AbortController();
    readbackController.current = controller;
    const params = new URLSearchParams({ date: body.date, timezone: body.timezone });
    try {
      const response = await fetch(`/api/daily-brief?${params}`, { credentials: 'same-origin', cache: 'no-store', signal: controller.signal, headers: { Accept: 'application/json' } });
      if (!response.ok) return 'unavailable';
      const parsed = parseDailyBriefResponse(await response.json(), body.date, body.timezone);
      if (!parsed) return 'unavailable';
      if (parsed.status === 'stale') return 'stale';
      if (parsed.status === 'unavailable' || parsed.status === 'failed' || parsed.status === 'not_configured' || parsed.status === 'partial') return 'unavailable';
      if (parsed.status === 'empty') return 'empty';
      const record = parsed.items[0];
      if (!record || parsed.status !== 'real' || !matchesRequest(record, body, expectedReceipt)) return 'mismatch';
      return expectedReceipt ? 'verified' : 'matched-content-unconfirmed';
    } catch { return 'unavailable'; }
  }

  async function verifyReceipt(body: ManualBriefRequest, value: WriteReceipt) {
    if (mounted.current) setReadbackState('pending');
    const result = await requestCurrentRead(body, value);
    if (!mounted.current) return;
    setReadbackState(result);
    if (result === 'verified') clearPending();
    onSaved();
  }

  async function checkUnknownOriginalDate(body: ManualBriefRequest) {
    if (mounted.current) setPhase('resolving-unknown');
    const result = await requestCurrentRead(body, null);
    if (!mounted.current) return;
    setReadbackState(result);
    if (result === 'matched-content-unconfirmed') {
      setPhase('unknown-date-match');
    } else {
      setPhase('unknown-date-blocked');
    }
  }

  async function submit() {
    if (submitting.current) return;
    const existing = savedRequest;
    if (existing && getBusinessDate() !== existing.date) {
      await checkUnknownOriginalDate(existing);
      return;
    }
    if (!existing && getBusinessDate() !== businessDate) {
      clearJournalChoices(); setBusinessDate(getBusinessDate()); invalidateRequest(); setError(copy.dateChanged); setPhase('editing'); return;
    }
    const selectedSources = sources.filter((source) => selected.includes(source.key));
    if (!existing && selectedSources.some((source) => source.ref.kind === 'journal' && source.sourceDate !== businessDate)) {
      clearJournalChoices(); invalidateRequest(); setError(copy.journalDateChanged); setPhase('editing'); return;
    }
    const key = existing?.idempotency_key ?? `ui-${crypto.randomUUID()}`;
    const body = existing ?? {
      mode: 'manual_generate' as const, date: businessDate, timezone: 'Asia/Shanghai' as const, idempotency_key: key,
      categories: categories.split(',').map((item) => item.trim()).filter(Boolean),
      summary, source_refs: selectedSources.map((source) => source.ref), approved: true as const,
    };
    if (!existing && !savePending(body, null)) { setError(copy.storageUnavailable); setPhase('editing'); return; }
    submitting.current = true;
    setSavedRequest(body); setPhase('submitting'); setError('');
    try {
      const response = await fetch('/api/daily-brief', {
        method: 'POST', credentials: 'same-origin', headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (response.status === 401 || response.status === 403) {
        clearPending(); setSavedRequest(null); setError(copy.auth); setPhase('editing'); return;
      }
      if (response.status === 409) {
        clearPending(); setSavedRequest(null); setError(copy.conflict); setPhase('editing'); onSaved(); return;
      }
      if (response.status === 422) {
        clearPending(); setSavedRequest(null); clearJournalChoices(); setError(copy.invalidRequest); setPhase('editing'); return;
      }
      if (!response.ok) { setError(response.status === 503 ? copy.unavailable : copy.unknown); setPhase('unknown'); return; }
      const parsed = parseReceipt(await response.json(), body.date);
      if (!parsed || (response.status === 201 && parsed.status !== 'created') || (response.status === 200 && parsed.status !== 'duplicate')) {
        setError(copy.unknown); setPhase('unknown'); return;
      }
      setReceipt(parsed); setReadbackState('pending'); setPhase('done');
      savePending(body, parsed);
      onSaved();
      void verifyReceipt(body, parsed);
    } catch {
      setError(copy.unknown); setPhase('unknown');
    } finally {
      submitting.current = false;
    }
  }

  async function retryCurrentReadback() {
    if (!savedRequest) return;
    if (!receipt) { await checkUnknownOriginalDate(savedRequest); return; }
    setReadbackState('pending');
    const result = await requestCurrentRead(savedRequest, receipt);
    if (!mounted.current) return;
    setReadbackState(result);
    if (result === 'verified') clearPending();
    onSaved();
  }

  return <section className="daily-brief-approval" aria-label={copy.title}>
    {phase === 'idle' && <button type="button" onClick={() => void begin()}>{copy.start}</button>}
    {phase === 'loading-sources' && <p role="status">{copy.loading}</p>}
    {phase !== 'idle' && phase !== 'loading-sources' && phase !== 'done' && <>
      <h2>{copy.title}</h2>
      {phase !== 'unknown' && phase !== 'unknown-date-blocked' && phase !== 'unknown-date-match' && <button type="button" onClick={() => { setPhase('idle'); setError(''); clearJournalChoices(); }} disabled={phase === 'submitting' || phase === 'resolving-unknown'}>{copy.cancel}</button>}
      {phase === 'editing' && <>
        <p role="status">业务日期：{businessDate}</p>
        <h3>{copy.sourceHeading}</h3>
        {sources.filter((source) => source.ref.kind !== 'journal').map((source) => <label key={source.key}>
          <input type="checkbox" checked={selected.includes(source.key)} onChange={() => toggleSource(source.key)} />
          {source.ref.kind === 'task' ? 'Task' : 'Project'} · {source.label}
        </label>)}
        {sources.filter((source) => source.ref.kind !== 'journal').length === 0 && <p role="status">{copy.noSources}</p>}
        <p>{copy.journalNote}</p>
        <JournalSourcePicker key={businessDate} locale={locale} onSelectionChange={onJournalSelectionChange} />
        {sources.filter((source) => source.ref.kind === 'journal').map((source) => <p className="journal-source-picker-selection" key={source.key} role="status">{source.label} · {source.ref.version.slice(0, 8)}</p>)}
        <label>{copy.summary}<textarea value={summary} maxLength={20000} onChange={(event) => updateSummary(event.target.value)} placeholder={copy.summaryPlaceholder} /></label>
        <label>{copy.categories}<input value={categories} onChange={(event) => updateCategories(event.target.value)} placeholder={copy.categoriesPlaceholder} /></label>
        <button type="button" onClick={confirmDraft}>{copy.prepare}</button>
      </>}
      {phase === 'confirming' && <>
        <h3>{copy.confirmationTitle}</h3><p>{copy.confirmationBody}</p>
        <p>业务日期：{businessDate}</p>
        <p><strong>{summary}</strong></p>
        <p>{selected.map((key) => sources.find((source) => source.key === key)?.label).filter(Boolean).join(' · ')}</p>
        <button type="button" onClick={() => void submit()}>{copy.confirm}</button>
      </>}
      {phase === 'submitting' && <p role="status">{copy.submitting}</p>}
      {phase === 'unknown' && <><p role="alert">{error || copy.unknown}</p><button type="button" onClick={() => void submit()}>{copy.retry}</button></>}
      {phase === 'resolving-unknown' && <p role="status">{copy.resolving}</p>}
      {phase === 'unknown-date-blocked' && <><p role="alert">{copy.unknownDate}</p><button type="button" onClick={() => void retryCurrentReadback()}>{copy.checkOriginalDate}</button></>}
      {phase === 'unknown-date-match' && <><p role="status">{copy.unknownDateMatch}</p><button type="button" onClick={() => void retryCurrentReadback()}>{copy.checkOriginalDate}</button></>}
    </>}
    {phase === 'done' && receipt && <div>
      <p role="status">{readbackState === 'verified' ? copy.currentVerified
        : readbackState === 'stale' ? copy.currentStale
          : readbackState === 'empty' ? copy.currentEmpty
            : readbackState === 'mismatch' ? copy.currentMismatch
              : readbackState === 'unavailable' ? copy.writeUnavailable
                : receipt.status === 'duplicate' ? copy.duplicate : copy.writePending}</p>
      {readbackState !== 'verified' && <button type="button" onClick={() => void retryCurrentReadback()}>{copy.retryReadback}</button>}
      {error && <p role="alert">{error}</p>}
    </div>}
    {error && phase !== 'unknown' && phase !== 'done' && <p role="alert">{error}</p>}
  </section>;
}
