import React, { useCallback, useEffect, useMemo, useState } from 'react';

type Locale = 'zh-CN' | 'en';
type CalendarEvent = { id: string; kind: 'journal' | 'task'; date: string; occurred_at?: string; status?: 'open' | 'completed' | 'succeeded' | 'failed' };
type CalendarResponse = { status: 'ok' | 'empty' | 'partial' | 'unavailable'; items: CalendarEvent[]; source: Array<'journal' | 'tasks'>; freshness: { checked_at: string } };
type LoadState = 'loading' | 'loaded' | 'unauthorized' | 'unavailable' | 'backend-not-implemented';

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function validDate(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00.000Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

function isoDateTime(value: unknown): value is string {
  return typeof value === 'string' && Number.isFinite(Date.parse(value));
}

function shanghaiMonth(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit' }).formatToParts(now);
  const year = Number(parts.find((item) => item.type === 'year')?.value);
  const month = Number(parts.find((item) => item.type === 'month')?.value);
  const pad = (value: number) => String(value).padStart(2, '0');
  const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate();
  return { from: `${year}-${pad(month)}-01`, to: `${year}-${pad(month)}-${pad(lastDay)}`, year, month, days: lastDay };
}

function parseCalendar(value: unknown, from: string, to: string): CalendarResponse | null {
  const allowedResponse = new Set(['status', 'items', 'source', 'freshness']);
  if (!isRecord(value) || Object.keys(value).some((field) => !allowedResponse.has(field))
    || !['ok', 'empty', 'partial', 'unavailable'].includes(String(value.status))
    || !Array.isArray(value.items) || !Array.isArray(value.source) || !isRecord(value.freshness)
    || !isoDateTime(value.freshness.checked_at)
    || !value.source.every((source) => source === 'journal' || source === 'tasks')) return null;
  const allowedItem = new Set(['id', 'kind', 'date', 'occurred_at', 'status']);
  const items: CalendarEvent[] = [];
  for (const raw of value.items) {
    if (!isRecord(raw) || Object.keys(raw).some((field) => !allowedItem.has(field))
      || typeof raw.id !== 'string' || !raw.id.trim()
      || (raw.kind !== 'journal' && raw.kind !== 'task') || !validDate(raw.date)
      || raw.date < from || raw.date > to
      || (raw.occurred_at !== undefined && !isoDateTime(raw.occurred_at))
      || (raw.status !== undefined && !['open', 'completed', 'succeeded', 'failed'].includes(String(raw.status)))) return null;
    items.push(raw as CalendarEvent);
  }
  if (value.status === 'empty' && items.length !== 0) return null;
  return { status: value.status as CalendarResponse['status'], items, source: value.source as CalendarResponse['source'], freshness: { checked_at: value.freshness.checked_at } };
}

const words = {
  'zh-CN': {
    eyebrow: 'WORKSPACE / CALENDAR', title: '日历', description: '仅显示已授权的日记日期与待办到期元数据，不加载正文。',
    loading: '正在读取日历…', unavailable: '日历数据暂不可用。', unauthorized: '当前账户无权读取日历数据。',
    notImplemented: 'BACKEND_NOT_IMPLEMENTED · 日历只读接口尚未进入 main。', partial: '部分来源不可用；只显示可确认的数据。', empty: '本月暂无日记或待办元数据。',
    journal: '日记', task: '待办', retry: '重试', checked: '数据检查时间', source: '来源', sources: { journal: '日记', tasks: '待办' },
    weekdays: ['一', '二', '三', '四', '五', '六', '日'], local: 'LOCAL_CANDIDATE · SYNTHETIC FIXTURE',
    localButton: '查看本地合成预览', hideButton: '隐藏合成预览', disclosure: '仅本地开发样例，不是实际日记或待办记录。',
  },
  en: {
    eyebrow: 'WORKSPACE / CALENDAR', title: 'Calendar', description: 'Shows authorized Journal dates and Task due metadata only; bodies are not loaded.',
    loading: 'Loading calendar…', unavailable: 'Calendar data is unavailable.', unauthorized: 'This account cannot read Calendar data.',
    notImplemented: 'BACKEND_NOT_IMPLEMENTED · The read-only Calendar API is not on main.', partial: 'Some sources are unavailable; only confirmed data is shown.', empty: 'No Journal or Task metadata this month.',
    journal: 'Journal', task: 'Task', retry: 'Retry', checked: 'Data checked', source: 'Sources', sources: { journal: 'Journal', tasks: 'Tasks' },
    weekdays: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'], local: 'LOCAL_CANDIDATE · SYNTHETIC FIXTURE',
    localButton: 'Show local synthetic preview', hideButton: 'Hide synthetic preview', disclosure: 'Local development sample only; not actual Journal or Task records.',
  },
} as const;

export function CalendarPage({ locale }: { locale: Locale }) {
  const t = words[locale];
  const month = useMemo(() => shanghaiMonth(), []);
  const [state, setState] = useState<LoadState>('loading');
  const [data, setData] = useState<CalendarResponse | null>(null);
  const [preview, setPreview] = useState(false);
  const [revision, setRevision] = useState(0);
  const load = useCallback(async (signal: AbortSignal) => {
    setState('loading');
    try {
      const query = new URLSearchParams({ from: month.from, to: month.to, timezone: 'Asia/Shanghai' });
      const response = await fetch(`/api/calendar?${query}`, { credentials: 'same-origin', signal, headers: { Accept: 'application/json' } });
      if (response.status === 401 || response.status === 403) throw new Error('unauthorized');
      if (response.status === 404 || response.status === 501) throw new Error('backend-not-implemented');
      if (!response.ok) throw new Error('unavailable');
      const parsed = parseCalendar(await response.json(), month.from, month.to);
      if (!parsed) throw new Error('unavailable');
      if (signal.aborted) return;
      setData(parsed);
      setState('loaded');
    } catch (error) {
      if (signal.aborted) return;
      const reason = error instanceof Error ? error.message : 'unavailable';
      setState(reason === 'unauthorized' ? 'unauthorized' : reason === 'backend-not-implemented' ? 'backend-not-implemented' : 'unavailable');
    }
  }, [month]);
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load, revision]);

  const eventsByDate = useMemo(() => {
    const groups = new Map<string, CalendarEvent[]>();
    for (const event of data?.items ?? []) groups.set(event.date, [...(groups.get(event.date) ?? []), event]);
    return groups;
  }, [data]);
  const firstWeekday = (new Date(`${month.from}T00:00:00Z`).getUTCDay() + 6) % 7;
  const eventsTotal = data?.items.length ?? 0;
  const stateMessage = state === 'loading' ? t.loading : state === 'unauthorized' ? t.unauthorized
    : state === 'unavailable' ? t.unavailable : t.notImplemented;
  const formatTime = (value: string) => new Date(value).toLocaleTimeString(locale === 'en' ? 'en-US' : 'zh-CN', { timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit' });

  return <section className="v1-readonly-page calendar-page" aria-labelledby="calendar-title">
    <header className="v1-page-header"><div><p className="eyebrow">SECONDBRAIN <span>/</span> {t.eyebrow}</p><h1 id="calendar-title">{t.title}</h1><p className="workspace-subtitle">{t.description}</p></div>
      <button type="button" className="v1-page-retry" onClick={() => setRevision((value) => value + 1)} disabled={state === 'loading'}>{t.retry}</button></header>
    {state !== 'loaded' ? <p className="v1-page-state is-unavailable" role={state === 'unauthorized' || state === 'unavailable' ? 'alert' : 'status'}>{stateMessage}</p>
      : data?.status === 'unavailable' ? <p className="v1-page-state is-unavailable" role="alert">{t.unavailable}</p>
        : <>
          {data?.status === 'partial' && <p className="v1-page-state is-partial" role="status">{t.partial}</p>}
          {data?.status === 'empty' && <p className="v1-page-state" role="status">{t.empty}</p>}
          <section className="calendar-month" aria-label={`${month.year}-${String(month.month).padStart(2, '0')}`}>
            <h2 className="calendar-month-title">{new Intl.DateTimeFormat(locale === 'en' ? 'en-US' : 'zh-CN', { timeZone: 'Asia/Shanghai', year: 'numeric', month: 'long' }).format(new Date(`${month.from}T00:00:00Z`))}</h2>
            <div className="calendar-weekdays" aria-hidden="true">{t.weekdays.map((day) => <span key={day}>{day}</span>)}</div>
            <ol className="calendar-grid" aria-label={t.title}>
              {Array.from({ length: firstWeekday }, (_, index) => <li className="calendar-day is-outside" aria-hidden="true" key={`blank-${index}`} />)}
              {Array.from({ length: month.days }, (_, index) => {
                const day = index + 1;
                const date = `${month.year}-${String(month.month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
                const items = eventsByDate.get(date) ?? [];
                return <li className="calendar-day" key={date} data-date={date} aria-label={`${date}, ${items.length} ${locale === 'en' ? 'items' : '项'}`}>
                  <time className="calendar-date" dateTime={date}>{day}</time>
                  {items.length > 0 && <ul className="calendar-events">{items.slice(0, 2).map((event) => <li key={event.id} className={`calendar-event is-${event.kind}`}>
                    <span>{event.kind === 'journal' ? t.journal : t.task}</span>{event.occurred_at && <time dateTime={event.occurred_at}>{formatTime(event.occurred_at)}</time>}
                  </li>)}{items.length > 2 && <li className="calendar-more">+{items.length - 2}</li>}</ul>}
                </li>;
              })}
            </ol>
          </section>
          <p className="calendar-source-note">{t.source}: {data?.source.length ? data.source.map((source) => t.sources[source]).join(' · ') : '—'} · {t.checked}: {data?.freshness.checked_at ? new Date(data.freshness.checked_at).toLocaleString(locale === 'en' ? 'en-US' : 'zh-CN') : '—'} · {eventsTotal}</p>
        </>}
    {import.meta.env.DEV && <section className="v1-local-preview" aria-label={t.local}><button type="button" className="v1-local-preview-toggle" aria-expanded={preview} onClick={() => setPreview((value) => !value)}>{preview ? t.hideButton : t.localButton}</button>{preview && <div className="v1-local-preview-content"><strong>{t.local}</strong><p>{t.disclosure}</p><p>2026-10-20 · {t.journal} · 09:30</p></div>}</section>}
  </section>;
}
