import { expect, test, type Page, type Request } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { writeFile } from 'node:fs/promises';
import { join } from 'node:path';

const baseUrl = process.env.SB_E2E_BASE_URL ?? 'http://127.0.0.1:4173';
const baseOrigin = new URL(baseUrl).origin;
const viewports = [
  { name: 'desktop-1440x1000', width: 1440, height: 1000 },
  { name: 'tablet-820x1180', width: 820, height: 1180 },
  { name: 'mobile-390x844', width: 390, height: 844 },
] as const;

type RequestRecord = { leg: 'browser' | 'core-upstream'; method: string; path: string; status: number | null; elapsed_ms: number | null; exact_inbox_target?: boolean };
const observations = new WeakMap<object, Awaited<ReturnType<typeof configurePage>>>();

function safePath(value: string): string {
  const url = new URL(value, baseUrl);
  return url.pathname.replace(/[0-9a-f]{32}/g, '<opaque-id>');
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

  page.on('request', (request) => {
    pending.set(request, Date.now());
    const url = new URL(request.url());
    if (url.pathname === '/api/inbox/entries' && request.method() === 'POST') {
      inboxPostCount += 1;
      try { lastInboxBody = JSON.parse(request.postData() ?? 'null') as Record<string, unknown>; }
      catch { lastInboxBody = null; }
    }
  });
  page.on('requestfinished', async (request) => {
    const started = pending.get(request) ?? Date.now();
    pending.delete(request);
    let status: number | null = null;
    try { status = (await request.response())?.status() ?? null; } catch { /* response may be intentionally lost */ }
    const path = new URL(request.url()).pathname;
    requestRecords.push({ leg: 'browser', method: request.method(), path: safePath(request.url()), status,
      elapsed_ms: Date.now() - started,
      exact_inbox_target: request.method() === 'GET' && Boolean(createdInboxId)
        && path === `/api/inbox/entries/${createdInboxId}` });
  });
  page.on('requestfailed', (request) => {
    const started = pending.get(request) ?? Date.now();
    pending.delete(request);
    requestRecords.push({ leg: 'browser', method: request.method(), path: safePath(request.url()), status: null, elapsed_ms: Date.now() - started });
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
    const inboxPath = /^\/api\/inbox\/entries(?:\/[0-9a-f]{32})?$/.test(url.pathname);
    const authPath = ['/api/auth/session', '/api/auth/login', '/api/auth/logout'].includes(url.pathname);
    if (url.pathname.startsWith('/api/') && !inboxPath && !authPath) {
      blockedOrigins.add('<disallowed-business-api>');
      await route.abort('blockedbyclient');
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
    get inboxPostCount() { return inboxPostCount; },
    get lastInboxBody() { return lastInboxBody; },
    get inboxId() { return createdInboxId; },
  };
}

async function signInAndCreateBlankSession(page: Page, viewport: { width: number; height: number }, observed: Awaited<ReturnType<typeof configurePage>>) {
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
  await page.getByRole('button', { name: '创建合成会话' }).click();
  await expect(page.getByRole('heading', { name: '合成会话 1' })).toBeVisible();
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
    await page.getByRole('button', { name: '发送' }).click();

    await expect(page.getByRole('button', { name: '使用同一请求重试' })).toBeVisible();
    expect(observed.inboxPostCount).toBe(1);
    const firstBody = observed.lastInboxBody;
    expect(firstBody).toMatchObject({ original_text: original, source_channel: 'web', intent: 'journal_intent' });
    expect(firstBody?.source_event_id).toEqual(expect.any(String));
    expect(firstBody?.occurred_at).toEqual(expect.any(String));
    await page.getByRole('button', { name: '使用同一请求重试' }).click();

    await expect(page.getByRole('heading', { name: '原文已保存到 Inbox' })).toBeVisible();
    await expect(page.getByText('已核验 Inbox 状态')).toBeVisible();
    expect(observed.inboxPostCount).toBe(2);
    expect(observed.inboxId).toMatch(/^[0-9a-f]{32}$/);
    const replayBody = observed.lastInboxBody;
    expect(replayBody).toEqual(firstBody);

    const changedText = `记一下：冲突保护合成测试 ${randomUUID()}`;
    await composer.fill(changedText);
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
    await page.getByRole('button', { name: '创建合成会话' }).click();
    await expect(page.getByRole('heading', { name: '合成会话 2' })).toBeVisible();
    const postsBeforeOrdinaryChat = observed.inboxPostCount;
    await composer.fill(`普通聊天合成文本 ${randomUUID()}`);
    await page.getByRole('button', { name: '发送' }).click();
    await expect(page.getByText('Synthetic completion')).toBeVisible();
    expect(observed.inboxPostCount).toBe(postsBeforeOrdinaryChat);
    expect(observed.blockedOrigins.size).toBe(0);

    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(scrollWidth).toBeLessThanOrEqual(viewport.width);
  });
}

test.afterEach(async ({ page }, testInfo) => {
  // Playwright's own trace is post-processed by the runner before artifact upload.
  if (testInfo.status !== testInfo.expectedStatus) {
    await writeFile(join(testInfo.outputDir, 'failure-summary.json'), JSON.stringify({
      test: testInfo.titlePath().join(' / '), status: testInfo.status, expected: testInfo.expectedStatus,
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
