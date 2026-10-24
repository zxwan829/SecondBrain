import { expect, test, type Page, type Request, type Response } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

const baseUrl = process.env.SB_E2E_BASE_URL ?? 'http://127.0.0.1:4173';
const baseOrigin = new URL(baseUrl).origin;
const viewports = [
  { name: 'desktop-1440x1000', width: 1440, height: 1000 },
  { name: 'tablet-820x1180', width: 820, height: 1180 },
  { name: 'mobile-390x844', width: 390, height: 844 },
] as const;

type RequestRecord = { leg: 'browser' | 'core-upstream'; method: string; path: string; status: number | null; elapsed_ms: number | null; exact_inbox_target?: boolean };
type FailureStage = 'login' | 'session' | 'first_submit' | 'retry' | 'conflict'
  | 'ordinary_chat' | 'source_protection' | 'daily_brief_read' | 'daily_brief_sources'
  | 'daily_brief_journal' | 'daily_brief_preview' | 'daily_brief_confirm'
  | 'daily_brief_readback' | 'permission_revocation' | 'post_revocation_navigation'
  | 'notes_navigation' | 'notes_create' | 'notes_edit_save' | 'notes_reopen'
  | 'agent_health' | 'today' | 'journal' | 'calendar' | 'viewport_layout';
type DiagnosticAssertion = 'test_setup' | 'home_to_projects' | 'projects_heading'
  | 'home_after_projects' | 'home_to_activity' | 'activity_heading'
  | 'activity_get_response' | 'activity_get_status_200' | 'home_after_activity'
  | 'home_after_revocation' | 'agent_health_heading' | 'home_after_agent_health'
  | 'today_heading' | 'home_after_today' | 'journal_heading' | 'home_after_journal'
  | 'activity_revocation_denial' | 'activity_revocation_empty' | 'activity_revocation_status_403'
  | 'calendar_heading' | 'calendar_api_requests' | 'projects_navigation' | 'projects_api_response'
  | 'activity_navigation' | 'agent_health_navigation' | 'agent_health_api_response'
  | 'today_navigation' | 'today_api_response' | 'journal_navigation' | 'journal_api_response'
  | 'calendar_navigation' | 'calendar_api_response' | 'home_api_response'
  | 'notes_navigation_link' | 'notes_collections'
  | 'daily_brief_navigation' | 'daily_brief_heading' | 'daily_brief_saved_readback'
  | 'daily_brief_open_prepare' | 'daily_brief_sources' | 'daily_brief_journal_action'
  | 'daily_brief_journal_source' | 'daily_brief_preview'
  | 'layout_home' | 'layout_projects' | 'layout_activity' | 'layout_agent_health'
  | 'layout_today' | 'layout_journal' | 'layout_calendar' | 'layout_notes' | 'layout_no_horizontal_overflow';
const observations = new WeakMap<object, Awaited<ReturnType<typeof configurePage>>>();

function waitForGetResponse(page: Page, path: string, matchesQuery: (params: URLSearchParams) => boolean = () => true) {
  return page.waitForResponse((response) => {
    const request = response.request();
    const url = new URL(response.url());
    return request.method() === 'GET' && url.pathname === path && matchesQuery(url.searchParams);
  }, { timeout: 5000 }).catch(() => null);
}

async function expectSuccessfulGet(
  responsePromise: Promise<Response | null>,
  observed: Awaited<ReturnType<typeof configurePage>>,
  assertion: DiagnosticAssertion,
) {
  observed.setDiagnosticAssertion(assertion);
  const response = await responsePromise;
  expect(response, `${assertion}_observed`).not.toBeNull();
  expect(response?.status(), assertion).toBe(200);
}

async function expectNoHorizontalOverflow(
  page: Page,
  observed: Awaited<ReturnType<typeof configurePage>>,
  viewport: { width: number },
  assertion: Extract<DiagnosticAssertion, `layout_${string}`>,
) {
  observed.setDiagnosticAssertion(assertion);
  const widths = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
  }));
  expect(widths.viewport).toBe(viewport.width);
  expect(Math.max(widths.document, widths.body), assertion).toBeLessThanOrEqual(widths.viewport);
}

function safePath(value: string): string {
  const url = new URL(value, baseUrl);
  return url.pathname.replace(/[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}|[0-9a-f]{32}/gi, '<opaque-id>');
}

async function configurePage(page: Page) {
  const requestRecords: RequestRecord[] = [];
  const pending = new Map<Request, number>();
  const blockedOrigins = new Set<string>();
  let chatSession = `synthetic-${randomUUID()}`;
  let ordinaryRunCompleted = false;
  let inboxPostCount = 0;
  let createdInboxId = '';
  let firstInboxResponse = true;
  let lastInboxBody: Record<string, unknown> | null = null;
  let dailyBriefPostCount = 0;
  let lastDailyBriefBody: Record<string, unknown> | null = null;
  let activityReadRevoked = false;
  let failureStage: FailureStage = 'login';
  let diagnosticAssertion: DiagnosticAssertion = 'test_setup';

  page.on('request', (request) => {
    pending.set(request, Date.now());
    const url = new URL(request.url());
    if (url.pathname === '/api/inbox/entries' && request.method() === 'POST') {
      inboxPostCount += 1;
      try { lastInboxBody = JSON.parse(request.postData() ?? 'null') as Record<string, unknown>; }
      catch { lastInboxBody = null; }
    }
    if (url.pathname === '/api/daily-brief' && request.method() === 'POST') {
      dailyBriefPostCount += 1;
      try { lastDailyBriefBody = JSON.parse(request.postData() ?? 'null') as Record<string, unknown>; }
      catch { lastDailyBriefBody = null; }
    }
  });
  const recordedResponses = new WeakSet<Request>();
  page.on('response', (response) => {
    const request = response.request();
    const started = pending.get(request) ?? Date.now();
    pending.delete(request);
    recordedResponses.add(request);
    const path = new URL(request.url()).pathname;
    requestRecords.push({ leg: 'browser', method: request.method(), path: safePath(request.url()), status: response.status(),
      elapsed_ms: Date.now() - started,
      exact_inbox_target: request.method() === 'GET' && Boolean(createdInboxId)
        && path === `/api/inbox/entries/${createdInboxId}` });
  });
  page.on('requestfinished', (request) => { pending.delete(request); });
  page.on('requestfailed', (request) => {
    const started = pending.get(request) ?? Date.now();
    pending.delete(request);
    if (!recordedResponses.has(request)) {
      requestRecords.push({ leg: 'browser', method: request.method(), path: safePath(request.url()), status: null, elapsed_ms: Date.now() - started });
    }
  });

  // Only the localhost Vite origin is allowed. Chat/Hermes endpoints are
  // fixture-only; Core auth and Inbox calls continue through Vite to real Core.
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== baseOrigin) {
      blockedOrigins.add('<external-origin>');
      await route.abort('blockedbyclient');
      return;
    }
    if (url.pathname.startsWith('/api/chat/')) {
      const method = route.request().method();
      if (url.pathname === '/api/chat/sessions' && method === 'POST') {
        chatSession = `synthetic-${randomUUID()}`;
        ordinaryRunCompleted = false;
        await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ session_id: chatSession }) });
      } else if (/\/runs\/[^/]+\/events$/.test(url.pathname)) {
        await route.fulfill({ status: 200, contentType: 'text/event-stream', body: 'data: {"event":"run.completed","output":"Synthetic completion"}\n\n' });
      } else if (/\/runs$/.test(url.pathname) && method === 'POST') {
        ordinaryRunCompleted = true;
        await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ run_id: `synthetic-run-${randomUUID()}` }) });
      } else if (/\/messages$/.test(url.pathname)) {
        const messages = ordinaryRunCompleted ? [{ id: `synthetic-${randomUUID()}`, session_id: chatSession,
          role: 'assistant', timestamp: new Date().toISOString(), text: 'Synthetic completion' }] : [];
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ messages }) });
      } else {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ session_id: chatSession, sessions: [], messages: [], activities: [] }) });
      }
      return;
    }
    const inboxPath = /^\/api\/inbox\/entries(?:\/[0-9a-f]{32})?$/.test(url.pathname)
      && ['GET', 'POST'].includes(route.request().method());
    const authPath = ['/api/auth/session', '/api/auth/login', '/api/auth/logout'].includes(url.pathname);
    const params = url.searchParams;
    const exactParams = (expected: Record<string, string>) => Array.from(params.keys()).length === Object.keys(expected).length
      && Object.entries(expected).every(([key, value]) => params.get(key) === value);
    const briefPath = route.request().method() === 'GET' && url.pathname === '/api/daily-brief'
      ? exactParams({ date: params.get('date') ?? '', timezone: 'Asia/Shanghai' })
        && /^\d{4}-\d{2}-\d{2}$/.test(params.get('date') ?? '')
      : route.request().method() === 'POST' && url.pathname === '/api/daily-brief' && params.size === 0;
    const journalSourcePath = route.request().method() === 'GET'
      && url.pathname === '/api/daily-brief/source-options/journal'
      && exactParams({ date: params.get('date') ?? '' })
      && /^\d{4}-\d{2}-\d{2}$/.test(params.get('date') ?? '');
    const sourceListPath = route.request().method() === 'GET'
      && ((url.pathname === '/api/tasks' && exactParams({ status: 'all' }))
        || (url.pathname === '/api/projects' && exactParams({ limit: '50', offset: '0' })));
    const homePath = route.request().method() === 'GET' && url.pathname === '/api/home' && params.size === 0;
    const healthPath = route.request().method() === 'GET' && url.pathname === '/api/agent/health' && params.size === 0;
    const activityPath = route.request().method() === 'GET' && url.pathname === '/api/activity'
      && exactParams({ limit: '50', offset: '0' });
    const calendarPath = route.request().method() === 'GET' && url.pathname === '/api/calendar'
      && exactParams({ from: params.get('from') ?? '', to: params.get('to') ?? '', timezone: 'Asia/Shanghai' })
      && /^\d{4}-\d{2}-\d{2}$/.test(params.get('from') ?? '')
      && /^\d{4}-\d{2}-\d{2}$/.test(params.get('to') ?? '');
    const journalPath = route.request().method() === 'GET' && /^\/api\/journal\/\d{4}-\d{2}-\d{2}$/.test(url.pathname)
      && params.size === 0;
    const taskListPath = route.request().method() === 'GET' && url.pathname === '/api/tasks'
      && exactParams({ status: 'open' });
    const notesPath = params.size === 0 && (
      (url.pathname === '/api/notes' && ['GET', 'POST'].includes(route.request().method()))
      || (route.request().method() === 'GET' && url.pathname === '/api/notes/drafts')
      || (['GET', 'PUT'].includes(route.request().method())
        && /^\/api\/notes\/drafts\/[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(url.pathname))
    );
    if (url.pathname.startsWith('/api/') && !inboxPath && !authPath
      && !briefPath && !journalSourcePath && !sourceListPath && !homePath && !healthPath
      && !activityPath && !calendarPath && !journalPath && !taskListPath && !notesPath) {
      blockedOrigins.add('<disallowed-business-api>');
      await route.abort('blockedbyclient');
      return;
    }
    if (activityReadRevoked && activityPath) {
      // The current Core contract has one owner action and no action-level
      // revoke API. This same-origin synthetic denial verifies the Web's
      // fail-closed response to a revoked activity.read capability.
      await route.fulfill({ status: 403, contentType: 'application/json', body: JSON.stringify({ detail: 'activity.read revoked in synthetic fixture' }) });
      return;
    }
    if (url.pathname === '/api/inbox/entries' && route.request().method() === 'POST' && firstInboxResponse) {
      firstInboxResponse = false;
      // Let the real Core commit the exact request, then simulate a lost HTTP
      // response to exercise the UI's same-body/idempotency-key retry.
      const upstreamStarted = Date.now();
      const upstream = await route.fetch();
      try {
        const payload = await upstream.json() as Record<string, unknown>;
        if (typeof payload.inbox_id === 'string') createdInboxId = payload.inbox_id;
      } catch { /* request metadata never persists response bodies */ }
      requestRecords.push({ leg: 'core-upstream', method: 'POST', path: '/api/inbox/entries',
        status: upstream.status(), elapsed_ms: Date.now() - upstreamStarted });
      await upstream.dispose();
      await route.abort('connectionreset');
      return;
    }
    await route.continue();
  });

  return {
    requestRecords, blockedOrigins,
    setFailureStage(stage: FailureStage) { failureStage = stage; },
    get failureStage() { return failureStage; },
    get inboxPostCount() { return inboxPostCount; },
    get lastInboxBody() { return lastInboxBody; },
    get dailyBriefPostCount() { return dailyBriefPostCount; },
    get lastDailyBriefBody() { return lastDailyBriefBody; },
    get diagnosticAssertion() { return diagnosticAssertion; },
    get activityReadStatuses() { return requestRecords.filter((request) => request.method === 'GET'
      && request.path === '/api/activity').map((request) => request.status).slice(-4); },
    get notesCollectionReadStatuses() { return requestRecords.filter((request) => request.method === 'GET'
      && request.path === '/api/notes').map((request) => request.status).slice(-4); },
    get dailyBriefReadStatuses() { return requestRecords.filter((request) => request.method === 'GET'
      && request.path === '/api/daily-brief').map((request) => request.status).slice(-4); },
    get inboxId() { return createdInboxId; },
    setDiagnosticAssertion(assertion: DiagnosticAssertion) { diagnosticAssertion = assertion; },
    setActivityReadRevoked(revoked: boolean) { activityReadRevoked = revoked; },
  };
}

async function inspectOrCreateDailyBrief(
  page: Page,
  viewport: { name: string; width: number; height: number },
  observed: Awaited<ReturnType<typeof configurePage>>,
) {
  observed.setFailureStage('daily_brief_read');
  observed.setDiagnosticAssertion('daily_brief_navigation');
  await page.goto('/brief');
  observed.setDiagnosticAssertion('daily_brief_heading');
  await expect(page.getByRole('heading', { name: /每日简报|Daily Brief/ })).toBeVisible();
  const beforeOpen = observed.dailyBriefPostCount;
  expect(beforeOpen).toBe(0);
  const desktopWriter = viewport.name === 'desktop-1440x1000';
  if (!desktopWriter) {
    // The desktop viewport is the sole writer for today's singleton Brief.
    // Tablet and mobile independently verify the persisted read-only result.
    observed.setDiagnosticAssertion('daily_brief_saved_readback');
    await expect(page.getByText('Synthetic manually approved daily brief')).toBeVisible();
  }

  expect(observed.dailyBriefPostCount).toBe(0);
  observed.setFailureStage('daily_brief_sources');
  observed.setDiagnosticAssertion('daily_brief_open_prepare');
  await page.getByRole('button', { name: '手动准备简报' }).click();
  observed.setDiagnosticAssertion('daily_brief_sources');
  await expect(page.getByRole('checkbox', { name: /Synthetic brief task source/ })).toBeVisible();
  await expect(page.getByRole('checkbox', { name: /Synthetic brief project source/ })).toBeVisible();
  expect(observed.dailyBriefPostCount).toBe(0);
  expect(observed.requestRecords.some((item) => item.method === 'GET' && item.path === '/api/daily-brief/source-options/journal')).toBe(false);

  observed.setFailureStage('daily_brief_journal');
  observed.setDiagnosticAssertion('daily_brief_journal_action');
  await page.getByRole('button', { name: '加载 Journal 来源' }).click();
  observed.setDiagnosticAssertion('daily_brief_journal_source');
  const journalSource = page.getByRole('checkbox', { name: /Journal 来源 1/ });
  await expect(journalSource).toBeVisible();
  await expect(page.getByText('Synthetic Journal source fixture; never read or published by the UI.')).toHaveCount(0);
  expect(observed.dailyBriefPostCount).toBe(0);

  await page.getByRole('checkbox', { name: /Task · Synthetic brief task source/ }).check();
  await page.getByRole('checkbox', { name: /Project · Synthetic brief project source/ }).check();
  await journalSource.check();
  await page.getByLabel(/简报正文/).fill('Synthetic manually approved daily brief');
  await page.getByLabel('分类（逗号分隔）').fill('合成验收');

  observed.setFailureStage('daily_brief_preview');
  observed.setDiagnosticAssertion('daily_brief_preview');
  await page.getByRole('button', { name: '预览并确认' }).click();
  await expect(page.getByText('确认要保存这份简报？')).toBeVisible();
  expect(observed.dailyBriefPostCount).toBe(0);
  if (!desktopWriter) return;

  observed.setFailureStage('daily_brief_confirm');
  await page.getByRole('button', { name: '确认并创建简报' }).click();
  observed.setFailureStage('daily_brief_readback');
  await expect(page.getByText('当前简报已核验：Brief 和来源版本与本次提交一致。')).toBeVisible();
  await expect(page.getByText('Synthetic manually approved daily brief')).toBeVisible();
  expect(observed.dailyBriefPostCount).toBe(1);
  expect(observed.lastDailyBriefBody).toMatchObject({ mode: 'manual_generate', approved: true,
    summary: 'Synthetic manually approved daily brief', timezone: 'Asia/Shanghai' });
  const refs = observed.lastDailyBriefBody?.source_refs as Array<{ kind: string }>;
  expect(new Set(refs.map((ref) => ref.kind))).toEqual(new Set(['task', 'project', 'journal']));
  expect(observed.requestRecords.filter((item) => item.method === 'POST' && item.path === '/api/daily-brief'))
    .toEqual([expect.objectContaining({ status: 201 })]);
  expect(observed.requestRecords.filter((item) => item.method === 'GET' && item.path === '/api/daily-brief').length)
    .toBeGreaterThanOrEqual(2);
  expect(observed.requestRecords.some((item) => item.method === 'GET'
    && item.path === '/api/daily-brief/source-options/journal' && item.status === 200)).toBe(true);
  expect(observed.requestRecords.some((item) => item.method === 'GET'
    && item.path === '/api/tasks' && item.status === 200)).toBe(true);
  expect(observed.requestRecords.some((item) => item.method === 'GET'
    && item.path === '/api/projects' && item.status === 200)).toBe(true);
}

async function signInAndCreateBlankSession(page: Page, viewport: { width: number; height: number }, observed: Awaited<ReturnType<typeof configurePage>>) {
  observed.setFailureStage('login');
  await page.setViewportSize(viewport);
  await page.goto('/chat/blank');
  const passwordInput = page.getByLabel('SecondBrain 登录口令');
  await expect(passwordInput).toHaveAttribute('type', 'password');
  await passwordInput.fill(await readSyntheticPassword());
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page.getByRole('heading', { name: '空白验收' })).toBeVisible();
  expect(observed.requestRecords.some((request) => request.method === 'GET'
    && request.path === '/api/auth/session' && request.status === 401)).toBe(true);
  expect(observed.requestRecords.some((request) => request.method === 'POST'
    && request.path === '/api/auth/login' && request.status === 200)).toBe(true);
  expect(observed.requestRecords.some((request) => request.path.startsWith('/api/chat/'))).toBe(false);
  expect(observed.inboxPostCount).toBe(0);
  observed.setFailureStage('session');
  await page.getByRole('button', { name: '创建合成会话' }).click();
  await expect(page.getByRole('heading', { name: '合成会话 1' })).toBeVisible();
}

async function returnHomeFromNavigation(
  page: Page,
  viewport: { width: number },
  observed: Awaited<ReturnType<typeof configurePage>>,
  assertion: Extract<DiagnosticAssertion, 'home_after_projects' | 'home_after_activity' | 'home_after_revocation' | 'home_after_agent_health' | 'home_after_today' | 'home_after_journal'>,
) {
  observed.setDiagnosticAssertion(assertion);
  if (viewport.width <= 760) {
    const menu = page.locator('.mobile-menu-button');
    await expect(menu).toHaveAttribute('aria-expanded', 'false');
    await menu.click();
    await expect(menu).toHaveAttribute('aria-expanded', 'true');
  }
  await page.locator('.sidebar nav').getByRole('button', { name: '首页', exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole('heading', { name: '你的工作台' })).toBeVisible();
  if (viewport.width <= 760) await expect(page.locator('.mobile-menu-button')).toHaveAttribute('aria-expanded', 'false');
}

let cachedPassword: string | undefined;
async function readSyntheticPassword(): Promise<string> {
  if (!cachedPassword) {
    const { readFile } = await import('node:fs/promises');
    cachedPassword = (await readFile(process.env.SB_E2E_PASSWORD_FILE!, 'utf8')).trim();
  }
  return cachedPassword;
}

for (const viewport of viewports) {
  test(`explicit Inbox capture, retry, conflict and source protection at ${viewport.name}`, async ({ page }, testInfo) => {
    const observed = await configurePage(page);
    observations.set(testInfo, observed);
    const original = `记一下：合成浏览器验收 ${viewport.name} ${randomUUID()}`;
    await signInAndCreateBlankSession(page, viewport, observed);
    const composer = page.getByPlaceholder('发送消息给 Hermes…');
    await composer.fill(original);
    observed.setFailureStage('first_submit');
    await page.getByRole('button', { name: '发送' }).click();

    await expect(page.getByRole('button', { name: '使用同一请求重试' })).toBeVisible();
    expect(observed.inboxPostCount).toBe(1);
    const firstBody = observed.lastInboxBody;
    expect(firstBody).toMatchObject({ original_text: original, source_channel: 'web', intent: 'journal_intent' });
    expect(firstBody?.source_event_id).toEqual(expect.any(String));
    expect(firstBody?.occurred_at).toEqual(expect.any(String));
    observed.setFailureStage('retry');
    await page.getByRole('button', { name: '使用同一请求重试' }).click();

    await expect(page.getByRole('heading', { name: '原文已保存到 Inbox' })).toBeVisible();
    await expect(page.getByText('已核验 Inbox 状态')).toBeVisible();
    expect(observed.inboxPostCount).toBe(2);
    expect(observed.inboxId).toMatch(/^[0-9a-f]{32}$/);
    const replayBody = observed.lastInboxBody;
    expect(replayBody).toEqual(firstBody);

    const changedText = `记一下：冲突保护合成测试 ${randomUUID()}`;
    await composer.fill(changedText);
    observed.setFailureStage('conflict');
    await page.evaluate((eventId) => {
      Object.defineProperty(crypto, 'randomUUID', { configurable: true, value: () => eventId });
    }, firstBody!.source_event_id as string);
    await page.getByRole('button', { name: '发送' }).click();
    await expect(page.getByRole('alert')).toContainText('事件标识冲突');
    expect(observed.lastInboxBody?.source_event_id).toBe(firstBody?.source_event_id);
    expect(observed.lastInboxBody?.original_text).toBe(changedText);
    expect(observed.requestRecords.some((request) => request.method === 'POST'
      && request.path === '/api/inbox/entries' && request.status === 409)).toBe(true);
    expect(observed.inboxPostCount).toBe(3);

    observed.setFailureStage('source_protection');
    const inboxGet = observed.requestRecords.filter((request) => request.method === 'GET' && request.path === '/api/inbox/entries/<opaque-id>');
    expect(inboxGet.length).toBeGreaterThanOrEqual(1);
    expect(inboxGet.some((request) => request.status === 200)).toBe(true);
    expect(observed.requestRecords.some((request) => request.exact_inbox_target && request.status === 200)).toBe(true);
    expect(observed.requestRecords.some((request) => request.leg === 'core-upstream'
      && request.method === 'POST' && request.path === '/api/inbox/entries' && request.status === 202)).toBe(true);
    expect(observed.requestRecords.some((request) => request.leg === 'browser' && request.method === 'POST'
      && request.path === '/api/inbox/entries' && request.status === 202)).toBe(true);
    expect(observed.requestRecords.some((request) => request.path.startsWith('/api/journal/entries'))).toBe(false);
    expect(observed.requestRecords.some((request) => request.path.startsWith('/api/knowledge'))).toBe(false);
    expect(observed.requestRecords.some((request) => request.path.startsWith('/api/projects'))).toBe(false);

    // Plain conversation stays on the fixture Hermes route and never creates
    // an Inbox entry.
    observed.setFailureStage('ordinary_chat');
    await page.getByRole('button', { name: '创建合成会话' }).click();
    await expect(page.getByRole('heading', { name: '合成会话 2' })).toBeVisible();
    const postsBeforeOrdinaryChat = observed.inboxPostCount;
    await composer.fill(`普通聊天合成文本 ${randomUUID()}`);
    await page.getByRole('button', { name: '发送' }).click();
    await expect(page.getByText('Synthetic completion')).toBeVisible();
    expect(observed.inboxPostCount).toBe(postsBeforeOrdinaryChat);

    await inspectOrCreateDailyBrief(page, viewport, observed);
    expect(observed.blockedOrigins.size).toBe(0);

    observed.setFailureStage('viewport_layout');
    const homeResponsePromise = waitForGetResponse(page, '/api/home');
    await page.goto('/');
    await expect(page.getByRole('heading', { name: '你的工作台' })).toBeVisible();
    await expectSuccessfulGet(homeResponsePromise, observed, 'home_api_response');
    await expectNoHorizontalOverflow(page, observed, viewport, 'layout_home');
    observed.setDiagnosticAssertion('home_to_projects');
    const projectsResponsePromise = waitForGetResponse(page, '/api/projects', (params) =>
      params.get('limit') === '50' && params.get('offset') === '0' && Array.from(params.keys()).length === 2);
    await page.getByRole('button', { name: '打开项目' }).first().click();
    observed.setDiagnosticAssertion('projects_navigation');
    await expect(page).toHaveURL(/\/projects(?:\?.*)?$/);
    observed.setDiagnosticAssertion('projects_heading');
    await expect(page.getByRole('heading', { name: '项目' })).toBeVisible();
    await expectSuccessfulGet(projectsResponsePromise, observed, 'projects_api_response');
    await expectNoHorizontalOverflow(page, observed, viewport, 'layout_projects');
    await returnHomeFromNavigation(page, viewport, observed, 'home_after_projects');
    observed.setDiagnosticAssertion('home_to_activity');
    const activityResponsePromise = page.waitForResponse((response) => {
      const request = response.request();
      const url = new URL(response.url());
      return request.method() === 'GET' && url.pathname === '/api/activity'
        && url.searchParams.get('limit') === '50' && url.searchParams.get('offset') === '0'
        && Array.from(url.searchParams.keys()).length === 2;
    }, { timeout: 5000 }).catch(() => null);
    await page.getByRole('button', { name: '打开动态' }).first().click();
    observed.setDiagnosticAssertion('activity_navigation');
    await expect(page).toHaveURL(/\/activity(?:\?.*)?$/);
    observed.setDiagnosticAssertion('activity_heading');
    await expect(page.getByRole('heading', { name: '动态' })).toBeVisible();
    observed.setDiagnosticAssertion('activity_get_response');
    const activityResponse = await activityResponsePromise;
    observed.setDiagnosticAssertion('activity_get_status_200');
    expect(activityResponse, 'activity_get_response_observed').not.toBeNull();
    expect(activityResponse?.status(), 'activity_get_http_200').toBe(200);
    await expectNoHorizontalOverflow(page, observed, viewport, 'layout_activity');
    observed.setDiagnosticAssertion('home_after_activity');
    await returnHomeFromNavigation(page, viewport, observed, 'home_after_activity');
    observed.setFailureStage('permission_revocation');
    observed.setDiagnosticAssertion('activity_heading');
    observed.setActivityReadRevoked(true);
    await page.getByRole('button', { name: '打开动态' }).first().click();
    observed.setDiagnosticAssertion('activity_heading');
    await expect(page.getByRole('heading', { name: '动态' })).toBeVisible();
    observed.setDiagnosticAssertion('activity_revocation_denial');
    await expect(page.getByRole('alert')).toHaveText('当前账户无权读取此页面数据。');
    observed.setDiagnosticAssertion('activity_revocation_empty');
    expect(await page.locator('.v1-activity-card').count()).toBe(0);
    observed.setDiagnosticAssertion('activity_revocation_status_403');
    expect(observed.requestRecords.some((request) => request.method === 'GET'
      && request.path === '/api/activity' && request.status === 403)).toBe(true);
    observed.setActivityReadRevoked(false);
    observed.setFailureStage('post_revocation_navigation');
    await returnHomeFromNavigation(page, viewport, observed, 'home_after_revocation');
    observed.setFailureStage('agent_health');
    const agentHealthResponsePromise = waitForGetResponse(page, '/api/agent/health');
    observed.setDiagnosticAssertion('agent_health_navigation');
    await page.getByRole('button', { name: '查看 Agent 状态' }).first().click();
    await expect(page).toHaveURL(/\/agent-health(?:\?.*)?$/);
    observed.setDiagnosticAssertion('agent_health_heading');
    await expect(page.getByRole('heading', { level: 1, name: 'Agent 状态', exact: true })).toBeVisible();
    await expectSuccessfulGet(agentHealthResponsePromise, observed, 'agent_health_api_response');
    await expectNoHorizontalOverflow(page, observed, viewport, 'layout_agent_health');
    await returnHomeFromNavigation(page, viewport, observed, 'home_after_agent_health');
    observed.setFailureStage('today');
    const todayResponsePromise = waitForGetResponse(page, '/api/tasks', (params) =>
      params.get('status') === 'open' && Array.from(params.keys()).length === 1);
    if (viewport.width <= 760) {
      const menu = page.locator('.mobile-menu-button');
      await expect(menu).toHaveAttribute('aria-expanded', 'false');
      await menu.click();
      await expect(menu).toHaveAttribute('aria-expanded', 'true');
    }
    observed.setDiagnosticAssertion('today_navigation');
    await page.locator('.sidebar nav').getByRole('button', { name: '今日', exact: true }).click();
    await expect(page).toHaveURL(/\/today(?:\?.*)?$/);
    observed.setDiagnosticAssertion('today_heading');
    await expect(page.getByRole('heading', { name: '今日与待办' })).toBeVisible();
    await expectSuccessfulGet(todayResponsePromise, observed, 'today_api_response');
    await expectNoHorizontalOverflow(page, observed, viewport, 'layout_today');
    if (viewport.width <= 760) await expect(page.locator('.mobile-menu-button')).toHaveAttribute('aria-expanded', 'false');
    await returnHomeFromNavigation(page, viewport, observed, 'home_after_today');
    observed.setFailureStage('journal');
    const journalResponsePromise = page.waitForResponse((response) => {
      const request = response.request();
      const url = new URL(response.url());
      return request.method() === 'GET' && /^\/api\/journal\/\d{4}-\d{2}-\d{2}$/.test(url.pathname) && url.search === '';
    }, { timeout: 5000 }).catch(() => null);
    observed.setDiagnosticAssertion('journal_navigation');
    await page.getByRole('button', { name: '新建日记' }).click();
    await expect(page).toHaveURL(/\/journal(?:\?.*)?$/);
    observed.setDiagnosticAssertion('journal_heading');
    await expect(page.getByRole('heading', { name: '日记' })).toBeVisible();
    await expectSuccessfulGet(journalResponsePromise, observed, 'journal_api_response');
    await expectNoHorizontalOverflow(page, observed, viewport, 'layout_journal');
    await returnHomeFromNavigation(page, viewport, observed, 'home_after_journal');
    observed.setFailureStage('calendar');
    const calendarResponsePromise = waitForGetResponse(page, '/api/calendar', (params) =>
      /^\d{4}-\d{2}-\d{2}$/.test(params.get('from') ?? '')
      && /^\d{4}-\d{2}-\d{2}$/.test(params.get('to') ?? '')
      && params.get('timezone') === 'Asia/Shanghai' && Array.from(params.keys()).length === 3);
    observed.setDiagnosticAssertion('calendar_navigation');
    await page.getByRole('button', { name: '查看完整日历' }).click();
    await expect(page).toHaveURL(/\/calendar(?:\?.*)?$/);
    observed.setDiagnosticAssertion('calendar_heading');
    await expect(page.getByRole('heading', { name: '日历' })).toBeVisible();
    await expectSuccessfulGet(calendarResponsePromise, observed, 'calendar_api_response');
    await expectNoHorizontalOverflow(page, observed, viewport, 'layout_calendar');
    observed.setDiagnosticAssertion('calendar_api_requests');
    expect(observed.blockedOrigins.size).toBe(0);
    for (const path of ['/api/home', '/api/projects', '/api/activity', '/api/agent/health', '/api/tasks', '/api/journal/', '/api/calendar']) {
      expect(observed.requestRecords.some((request) => request.method === 'GET' && request.path.startsWith(path))).toBe(true);
    }

    observed.setFailureStage('notes_navigation');
    if (viewport.width <= 760) {
      const menu = page.locator('.mobile-menu-button');
      if (await menu.getAttribute('aria-expanded') === 'false') await menu.click();
      await expect(menu).toHaveAttribute('aria-expanded', 'true');
    }
    const collectionsResponsePromise = waitForGetResponse(page, '/api/notes');
    const notesNavigationButton = page.locator('.sidebar nav').getByRole('button', { name: '笔记', exact: true });
    observed.setDiagnosticAssertion('notes_navigation_link');
    await expect(notesNavigationButton).toBeVisible();
    observed.setDiagnosticAssertion('notes_navigation');
    await notesNavigationButton.click();
    observed.setDiagnosticAssertion('notes_collections');
    await expectSuccessfulGet(collectionsResponsePromise, observed, 'notes_collections');
    await expect(page).toHaveURL(/\/notes(?:\?.*)?$/);
    await expect(page.getByRole('heading', { name: '笔记', exact: true })).toBeVisible();
    await expectNoHorizontalOverflow(page, observed, viewport, 'layout_notes');

    observed.setFailureStage('notes_create');
    const createNoteResponsePromise = page.waitForResponse((response) =>
      response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/notes', { timeout: 5000 });
    observed.setDiagnosticAssertion('notes_create');
    await page.getByRole('button', { name: '新建 Draft', exact: true }).click();
    const createNoteResponse = await createNoteResponsePromise;
    expect(createNoteResponse.status(), 'notes_create').toBe(200);
    const createdNote = await createNoteResponse.json() as { collection: string; path: string };
    expect(createdNote.collection).toBe('drafts');
    expect(createdNote.path).toMatch(/^[0-9a-f-]{36}$/i);
    const editor = page.locator('.ProseMirror');
    await expect(editor).toBeVisible();

    const syntheticNoteBody = `Synthetic mobile note round trip ${viewport.name}`;
    observed.setFailureStage('notes_edit_save');
    const saveNoteResponsePromise = page.waitForResponse((response) => {
      const request = response.request();
      return request.method() === 'PUT' && new URL(response.url()).pathname === `/api/notes/drafts/${createdNote.path}`;
    }, { timeout: 5000 });
    observed.setDiagnosticAssertion('notes_save');
    await editor.fill(syntheticNoteBody);
    const saveNoteResponse = await saveNoteResponsePromise;
    expect(saveNoteResponse.status(), 'notes_save').toBe(200);
    await expect(page.getByRole('status').filter({ hasText: '已保存' }).first()).toBeVisible();

    observed.setFailureStage('notes_reopen');
    await page.reload();
    const readNoteResponsePromise = page.waitForResponse((response) => {
      const request = response.request();
      return request.method() === 'GET' && new URL(response.url()).pathname === `/api/notes/drafts/${createdNote.path}`;
    }, { timeout: 5000 });
    observed.setDiagnosticAssertion('notes_readback');
    await page.getByRole('button', { name: syntheticNoteBody, exact: true }).click();
    const readNoteResponse = await readNoteResponsePromise;
    expect(readNoteResponse.status(), 'notes_readback').toBe(200);
    await expect(page.locator('.ProseMirror')).toContainText(syntheticNoteBody);
    await expectNoHorizontalOverflow(page, observed, viewport, 'layout_notes');

    // Exercise the real Notes dialog layout CSS against each accepted viewport.
    // This uses only static synthetic markup; Notes save/reopen is covered by
    // the separate localhost HTTP and component tests.
    observed.setDiagnosticAssertion('layout_no_horizontal_overflow');
    await page.setContent('<div class="visual-dialog-backdrop"><section class="visual-dialog" role="dialog" aria-label="合成图形"><header class="visual-dialog-header"><h2>思维导图</h2><span>synthetic.mindmap.json</span><button type="button">关闭</button></header><div class="visual-map-editor"></div><footer class="visual-dialog-footer"><span>已保存</span><button type="button">保存图形</button></footer></section></div>');
    await page.addStyleTag({ content: await readFile(new URL('../../secondbrain-frontend/src/styles/app.css', import.meta.url), 'utf8') });
    const dialogGeometry = await page.locator('.visual-dialog').evaluate((dialog) => {
      const bounds = dialog.getBoundingClientRect();
      const close = dialog.querySelector('header button')?.getBoundingClientRect();
      return { left: bounds.left, right: bounds.right, top: bounds.top, bottom: bounds.bottom,
        closeLeft: close?.left, closeRight: close?.right, closeTop: close?.top, closeBottom: close?.bottom };
    });
    expect(dialogGeometry.left).toBeGreaterThanOrEqual(20);
    expect(dialogGeometry.right).toBeLessThanOrEqual(viewport.width - 20);
    expect(dialogGeometry.top).toBeGreaterThanOrEqual(20);
    expect(dialogGeometry.bottom).toBeLessThanOrEqual(viewport.height - 20);
    expect(dialogGeometry.closeLeft).toBeGreaterThanOrEqual(dialogGeometry.left);
    expect(dialogGeometry.closeRight).toBeLessThanOrEqual(dialogGeometry.right);
    expect(dialogGeometry.closeTop).toBeGreaterThanOrEqual(dialogGeometry.top);
    expect(dialogGeometry.closeBottom).toBeLessThanOrEqual(dialogGeometry.bottom);

    // Short landscape viewport reproduces the phone keyboard/orientation class
    // of failure where the old 420px minimum height hid the dialog footer.
    await page.setViewportSize({ width: 844, height: 390 });
    const landscapeGeometry = await page.locator('.visual-dialog').evaluate((dialog) => {
      const bounds = dialog.getBoundingClientRect();
      const close = dialog.querySelector('header button')?.getBoundingClientRect();
      const save = dialog.querySelector('footer button')?.getBoundingClientRect();
      return { top: bounds.top, bottom: bounds.bottom, closeTop: close?.top,
        closeBottom: close?.bottom, saveTop: save?.top, saveBottom: save?.bottom };
    });
    expect(landscapeGeometry.top).toBeGreaterThanOrEqual(8);
    expect(landscapeGeometry.bottom).toBeLessThanOrEqual(382);
    expect(landscapeGeometry.closeTop).toBeGreaterThanOrEqual(landscapeGeometry.top);
    expect(landscapeGeometry.closeBottom).toBeLessThanOrEqual(landscapeGeometry.bottom);
    expect(landscapeGeometry.saveTop).toBeGreaterThanOrEqual(landscapeGeometry.top);
    expect(landscapeGeometry.saveBottom).toBeLessThanOrEqual(landscapeGeometry.bottom);

  });
}

test.afterEach(async ({ page }, testInfo) => {
  // Playwright's own trace is post-processed by the runner before artifact upload.
  if (testInfo.status !== testInfo.expectedStatus) {
    const observed = observations.get(testInfo);
    const viewport = viewports.find(({ name }) => testInfo.title.includes(name));
    const errors = testInfo.errors;
    const isTimeout = errors.some((error) => error.name === 'TimeoutError' || /timeout/i.test(error.message));
    const isAssertion = errors.some((error) => /\bexpect(?:\(|\.)|\bExpected:|\bReceived:/i.test(error.message));
    await writeFile(join(testInfo.outputDir, 'failure-summary.json'), JSON.stringify({
      schema_version: 2,
      viewport: viewport?.name ?? 'unknown',
      stage: observed?.failureStage ?? 'login',
      code: isTimeout ? 'timeout' : isAssertion ? 'assertion_failed' : 'test_error',
      assertion_id: observed?.diagnosticAssertion ?? 'test_setup',
      activity_get_statuses: observed?.activityReadStatuses ?? [],
      notes_collection_statuses: observed?.notesCollectionReadStatuses ?? [],
      daily_brief_get_statuses: observed?.dailyBriefReadStatuses ?? [],
    }, null, 2), { mode: 0o600 });
  }
  const observed = observations.get(testInfo);
  if (observed) {
    const viewport = viewports.find(({ name }) => testInfo.title.includes(name));
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth).catch(() => null);
    await testInfo.attach('request-metadata.json', {
      body: JSON.stringify({ viewport: viewport?.name ?? 'unknown', scroll_width: scrollWidth,
        requests: observed.requestRecords, blocked_or_disallowed: observed.blockedOrigins.size > 0 }, null, 2),
      contentType: 'application/json',
    });
  }
});
