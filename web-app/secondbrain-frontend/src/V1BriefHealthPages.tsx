import React, { useCallback, useEffect, useState } from 'react';

type Locale = 'zh-CN' | 'en';
type BriefPageState = 'loading' | 'not-configured' | 'unauthorized' | 'unavailable' | 'backend-not-implemented';
type HealthPageState = 'loading' | 'online' | 'not-configured' | 'unavailable' | 'unauthorized' | 'backend-not-implemented';
type AgentHealth = { status: 'online' | 'unavailable' | 'not_configured'; source: 'hermes-runtime' | null; checked_at: string };

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function isIsoDateTime(value: unknown): value is string {
  return typeof value === 'string' && Number.isFinite(Date.parse(value));
}

function shanghaiDate(now = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(now);
  const part = (type: string) => parts.find((item) => item.type === type)?.value ?? '';
  return `${part('year')}-${part('month')}-${part('day')}`;
}

async function read(path: string, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(path, { credentials: 'same-origin', signal, headers: { Accept: 'application/json' } });
  if (response.status === 401 || response.status === 403) throw new Error('unauthorized');
  if (response.status === 404 || response.status === 501) throw new Error('backend-not-implemented');
  if (!response.ok) throw new Error('unavailable');
  return response.json();
}

function isNotConfiguredBrief(value: unknown): boolean {
  return isRecord(value) && Object.keys(value).every((key) => ['status', 'items', 'source'].includes(key))
    && value.status === 'not_configured' && Array.isArray(value.items)
    && value.items.length === 0 && value.source === null;
}

function parseAgentHealth(value: unknown): AgentHealth | null {
  if (!isRecord(value) || !['online', 'unavailable', 'not_configured'].includes(String(value.status))
    || (value.source !== 'hermes-runtime' && value.source !== null) || !isIsoDateTime(value.checked_at)) return null;
  const allowed = new Set(['status', 'source', 'checked_at']);
  if (Object.keys(value).some((key) => !allowed.has(key))) return null;
  return value as AgentHealth;
}

const text = {
  'zh-CN': {
    brief: { eyebrow: 'WORKSPACE / DAILY BRIEF', title: '每日简报', description: '查看当天已获准提供的简报。', notConfigured: 'DAILY_BRIEF_NOT_CONFIGURED · 当前没有已批准的简报来源；此页面不会自动汇总或生成内容。' },
    health: { eyebrow: 'WORKSPACE / AGENT HEALTH', title: 'Agent 状态', description: '查看 Hermes 运行能力检查结果，不加载会话或消息。', online: '在线', notConfigured: '未配置', unavailable: '暂不可用' },
    loading: '正在检查…', unauthorized: '当前账户无权读取此页面数据。', unavailable: '该页面数据暂不可用。请稍后重试。',
    notImplemented: 'BACKEND_NOT_IMPLEMENTED · 只读接口尚未进入 main。', retry: '重试', checked: '检查时间',
    localPreview: '查看本地合成预览', hidePreview: '隐藏合成预览', local: 'LOCAL_CANDIDATE · SYNTHETIC FIXTURE',
    disclosure: '仅本地开发预览样例，不是真实 Agent 状态或已生成简报。', previewBrief: '本地样例：暂无已配置简报。', previewHealth: '本地样例：未连接 Agent 服务。',
  },
  en: {
    brief: { eyebrow: 'WORKSPACE / DAILY BRIEF', title: 'Daily Brief', description: 'View an approved brief for today.', notConfigured: 'DAILY_BRIEF_NOT_CONFIGURED · No approved brief source is configured; this page does not summarize or generate content.' },
    health: { eyebrow: 'WORKSPACE / AGENT HEALTH', title: 'Agent Health', description: 'View the Hermes runtime capability check without loading sessions or messages.', online: 'Online', notConfigured: 'Not configured', unavailable: 'Unavailable' },
    loading: 'Checking…', unauthorized: 'This account cannot read this page.', unavailable: 'This page data is unavailable. Try again later.',
    notImplemented: 'BACKEND_NOT_IMPLEMENTED · The read-only API is not on main yet.', retry: 'Retry', checked: 'Checked at',
    localPreview: 'Show local synthetic preview', hidePreview: 'Hide synthetic preview', local: 'LOCAL_CANDIDATE · SYNTHETIC FIXTURE',
    disclosure: 'Local development preview only. This is not real Agent status or a generated brief.',
    previewBrief: 'Local sample: no configured brief.', previewHealth: 'Local sample: Agent service is not connected.',
  },
} as const;

export function V1BriefHealthPage({ page, locale }: { page: 'brief' | 'agent-health'; locale: Locale }) {
  const copy = text[locale];
  const words = copy[page === 'brief' ? 'brief' : 'health'];
  const [state, setState] = useState<BriefPageState | HealthPageState>('loading');
  const [checkedAt, setCheckedAt] = useState<string | null>(null);
  const [preview, setPreview] = useState(false);
  const [revision, setRevision] = useState(0);

  const load = useCallback(async (signal: AbortSignal) => {
    setState('loading');
    setCheckedAt(null);
    try {
      const path = page === 'brief'
        ? `/api/daily-brief?date=${shanghaiDate()}&timezone=Asia%2FShanghai`
        : '/api/agent/health';
      const payload = await read(path, signal);
      if (signal.aborted) return;
      if (page === 'brief') {
        if (!isNotConfiguredBrief(payload)) throw new Error('unavailable');
        setState('not-configured');
        return;
      }
      const health = parseAgentHealth(payload);
      if (!health) throw new Error('unavailable');
      setCheckedAt(health.checked_at);
      setState(health.status === 'online' ? 'online' : health.status === 'not_configured' ? 'not-configured' : 'unavailable');
    } catch (error) {
      if (signal.aborted) return;
      const reason = error instanceof Error ? error.message : 'unavailable';
      setState(reason === 'unauthorized' ? 'unauthorized' : reason === 'backend-not-implemented' ? 'backend-not-implemented' : 'unavailable');
    }
  }, [page]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load, revision]);

  const formatTime = (value: string) => new Date(value).toLocaleString(locale === 'en' ? 'en-US' : 'zh-CN');
  const statusLabel = state === 'online' ? copy.health.online : state === 'not-configured' ? copy.health.notConfigured : copy.health.unavailable;

  return (
    <section className={`v1-readonly-page v1-readonly-page-${page}`} aria-labelledby={`${page}-title`}>
      <header className="v1-page-header">
        <div><p className="eyebrow">SECONDBRAIN <span>/</span> {words.eyebrow}</p><h1 id={`${page}-title`}>{words.title}</h1><p className="workspace-subtitle">{words.description}</p></div>
        <button type="button" className="v1-page-retry" onClick={() => setRevision((value) => value + 1)} disabled={state === 'loading'}>{copy.retry}</button>
      </header>
      {state === 'loading' ? <p className="v1-page-state" role="status">{copy.loading}</p>
        : state === 'unauthorized' ? <p className="v1-page-state is-unavailable" role="alert">{copy.unauthorized}</p>
          : state === 'unavailable' ? <p className="v1-page-state is-unavailable" role="alert">{copy.unavailable}</p>
            : state === 'backend-not-implemented' ? <p className="v1-page-state is-unavailable" role="status">{copy.notImplemented}</p>
              : page === 'brief' ? <p className="v1-contract-notice" role="status">{copy.brief.notConfigured}</p>
                : <article className="v1-data-card v1-agent-health-card" aria-label={words.title}>
                  <div className="v1-data-card-heading"><h2>{words.title}</h2><span className={`v1-status-pill ${state === 'online' ? 'is-healthy' : 'is-unavailable'}`}>{statusLabel}</span></div>
                  {checkedAt && <dl className="v1-data-fields"><div><dt>{copy.checked}</dt><dd><time>{formatTime(checkedAt)}</time></dd></div>{state !== 'not-configured' && <div><dt>Source</dt><dd>Hermes runtime</dd></div>}</dl>}
                </article>}
      {import.meta.env.DEV && <section className="v1-local-preview" aria-label={copy.local}>
        <button type="button" className="v1-local-preview-toggle" aria-expanded={preview} onClick={() => setPreview((value) => !value)}>{preview ? copy.hidePreview : copy.localPreview}</button>
        {preview && <div className="v1-local-preview-content"><strong>{copy.local}</strong><p>{copy.disclosure}</p><p>{page === 'brief' ? copy.previewBrief : copy.previewHealth}</p></div>}
      </section>}
    </section>
  );
}
