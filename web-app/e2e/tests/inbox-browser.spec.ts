import { expect, test, type Page, type Request, type Response, type Route, type TestInfo } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

const baseUrl = process.env.SB_E2E_BASE_URL ?? 'http://127.0.0.1:4173';
const baseOrigin = new URL(baseUrl).origin;
function safePageErrorSummary(value: string): string {
  const missingExport = value.match(/requested module ['\"]([^'\"]+)['\"] does not provide an export named ['\"]([^'\"]+)['\"]/i);
  if (missingExport) {
    const modulePath = missingExport[1].split(/[?#]/, 1)[0].replaceAll('\\', '/');
    const dependencyPath = modulePath.split('/node_modules/', 2)[1] ?? '';
    const dependency = dependencyPath.startsWith('.vite/deps/')
      ? dependencyPath.slice('.vite/deps/'.length).split('/', 1)[0]
      : dependencyPath.startsWith('@')
        ? dependencyPath.split('/', 2).join('_')
        : dependencyPath.split('/', 1)[0];
    const moduleName = dependency.replace(/[^A-Za-z0-9_-]/g, '_').slice(0, 64) || 'unknown';
    const symbol = /^[A-Za-z_$][A-Za-z0-9_$]{0,48}$/.test(missingExport[2]) ? missingExport[2] : 'unknown';
    return `missing_export module_${moduleName} symbol_${symbol}`.slice(0, 120);
  }
  return value
    .replace(/https?:\/\/[^\s)]+/gi, '<url>')
    .replace(/(?:[A-Za-z]:\\|\/(?:Users|home|private|tmp|opt|workspace)\/)[^\s)]+/gi, '<path>')
    .replace(/\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b/gi, '<id>')
    .replace(/\b[A-Za-z0-9_./+=-]{16,}\b/g, '<value>')
    .replace(/(['"`])(?:\\.|(?!\1)[^\\])*\1/g, '<quoted>')
    .replace(/[\u3400-\u9fff]+/g, '<text>')
    .replace(/\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b/g, '<email>')
    .replace(/[^A-Za-z0-9 <>._,:()'-]/g, ' ')
    .replace(/\s+/g, ' ')
    .slice(0, 120);
}
const viewports = [
  { name: 'desktop-1440x1000', width: 1440, height: 1000 },
  { name: 'tablet-820x1180', width: 820, height: 1180 },
  { name: 'mobile-390x844', width: 390, height: 844 },
] as const;
const wp5RoundtripOnly = process.env.SB_E2E_WP5_ROUNDTRIP_ONLY === 'true';
const wp5ConflictOnly = process.env.SB_E2E_WP5_CONFLICT_ONLY === 'true';
const desktopOnly = process.env.SB_E2E_DESKTOP_ONLY === 'true';
const activeViewports = desktopOnly ? [viewports[0]] : viewports;

type RequestRecord = { leg: 'browser' | 'core-upstream'; method: string; path: string; status: number | null; elapsed_ms: number | null; exact_inbox_target?: boolean };
type Wp5ProbeEvent = { marker: 'wp5-conflict-queue'; at_ms: number; event: string; status?: number };
const WP5_PROBE_MARKER = 'wp5-conflict-queue' as const;
function boundedWp5ProbeTimeline(events: Wp5ProbeEvent[]): Wp5ProbeEvent[] {
  const ordered = [...events].sort((left, right) => left.at_ms - right.at_ms);
  if (ordered.length <= 64 && !ordered.some((event) => event.event === 'probe-events-overflow')) return ordered;
  return [...ordered.slice(0, 63), {
    marker: WP5_PROBE_MARKER, at_ms: ordered.at(-1)?.at_ms ?? Date.now(), event: 'probe-events-overflow',
  }].sort((left, right) => left.at_ms - right.at_ms);
}
type FailureStage = 'login' | 'session' | 'first_submit' | 'retry' | 'conflict'
  | 'ordinary_chat' | 'source_protection' | 'daily_brief_read' | 'daily_brief_sources'
  | 'daily_brief_journal' | 'daily_brief_preview' | 'daily_brief_confirm'
  | 'daily_brief_readback' | 'permission_revocation' | 'post_revocation_navigation'
  | 'notes_navigation' | 'notes_create' | 'notes_edit_save' | 'notes_reopen'
  | 'notes_frontmatter_seed' | 'notes_frontmatter_reopen'
  | 'notes_blocksuite_open' | 'notes_blocksuite_edit' | 'notes_blocksuite_conflict' | 'notes_blocksuite_reopen'
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
  | 'journal_append' | 'journal_saved_readback' | 'journal_refresh_readback'
  | 'calendar_navigation' | 'calendar_api_response' | 'home_api_response'
  | 'notes_navigation_link' | 'notes_collections' | 'notes_blocksuite_open'
  | 'notes_blocksuite_edit' | 'notes_blocksuite_edit_focus' | 'notes_blocksuite_edit_end'
  | 'notes_blocksuite_edit_newline' | 'notes_blocksuite_edit_type' | 'notes_blocksuite_edit_save_response'
  | 'notes_blocksuite_edit_response_body' | 'notes_blocksuite_saved_title'
  | 'notes_blocksuite_saved_tag' | 'notes_blocksuite_saved_custom_property'
  | 'notes_blocksuite_saved_edit_text' | 'notes_blocksuite_saved_status'
  | 'notes_blocksuite_conflict_seed' | 'notes_blocksuite_conflict_rejected'
  | 'notes_blocksuite_conflict_editor_enabled' | 'notes_blocksuite_conflict_unsaved_state'
  | 'notes_blocksuite_conflict_ui' | 'notes_blocksuite_conflict_readback'
  | 'notes_blocksuite_conflict_readback_status' | 'notes_blocksuite_conflict_readback_payload'
  | 'notes_blocksuite_reopen_note_selector' | 'notes_blocksuite_reopen_navigation_response' | 'notes_blocksuite_reopen_editor_entry'
  | 'notes_blocksuite_reopen_canvas'
  | 'notes_blocksuite_quick_switch_edit' | 'notes_blocksuite_quick_switch_fallback' | 'notes_blocksuite_quick_switch_save_response'
  | 'notes_blocksuite_reopen_heading' | 'notes_blocksuite_reopen_saved_status' | 'notes_blocksuite_reopen_editor_button'
  | 'notes_setext_seed_status_200' | 'notes_setext_seed_status_401' | 'notes_setext_seed_status_403'
  | 'notes_setext_seed_status_409' | 'notes_setext_seed_status_412' | 'notes_setext_seed_status_422'
  | 'notes_setext_seed_status_428' | 'notes_setext_seed_status_other'
  | 'notes_setext_reopen_read' | 'notes_setext_editor_open' | 'notes_setext_leave_read' | 'notes_setext_fallback' | 'notes_setext_fallback_render'
  | 'notes_attachment_select' | 'notes_attachment_open' | 'notes_attachment_fallback' | 'notes_attachment_render'
  | 'notes_unsafe_select' | 'notes_unsafe_source' | 'notes_unsafe_safety' | 'notes_unsafe_editor_hidden'
  | 'notes_blocksuite_reopen_scrollable' | 'notes_blocksuite_reopen_concurrent_update'
  | 'wp5_unsupported_projection_seed' | 'wp5_unsupported_projection_open'
  | 'wp5_unsupported_projection_rejected' | 'wp5_unsupported_projection_preserved'
  | 'wp5_unsupported_projection_no_core_put'
  | 'notes_conflict_seed_status_200' | 'notes_conflict_seed_status_401'
  | 'notes_conflict_seed_status_403' | 'notes_conflict_seed_status_404'
  | 'notes_conflict_seed_status_409' | 'notes_conflict_seed_status_412'
  | 'notes_conflict_seed_status_422' | 'notes_conflict_seed_status_428'
  | 'notes_conflict_seed_status_other'
  | 'wp5_focus_notes_navigation' | 'wp5_focus_note_seed'
  | 'wp5_resource_focus' | 'wp5_resource_type' | 'wp5_resource_dirty' | 'wp5_resource_save' | 'wp5_resource_saved' | 'wp5_resource_close' | 'wp5_resource_reopen' | 'wp5_resource_checkpoint_001' | 'wp5_resource_checkpoint_002' | 'wp5_resource_checkpoint_003' | 'wp5_resource_checkpoint_004' | 'wp5_resource_checkpoint_005' | 'wp5_resource_checkpoint_006' | 'wp5_resource_checkpoint_007' | 'wp5_resource_checkpoint_008' | 'wp5_resource_checkpoint_009' | 'wp5_resource_checkpoint_010' | 'wp5_resource_checkpoint_011' | 'wp5_resource_checkpoint_012' | 'wp5_resource_checkpoint_013' | 'wp5_resource_checkpoint_014' | 'wp5_resource_checkpoint_015' | 'wp5_resource_checkpoint_016' | 'wp5_resource_checkpoint_017' | 'wp5_resource_checkpoint_018' | 'wp5_resource_checkpoint_019' | 'wp5_resource_checkpoint_020' | 'wp5_resource_checkpoint_021' | 'wp5_resource_checkpoint_022' | 'wp5_resource_checkpoint_023' | 'wp5_resource_checkpoint_024' | 'wp5_resource_checkpoint_025' | 'wp5_resource_checkpoint_026' | 'wp5_resource_checkpoint_027' | 'wp5_resource_checkpoint_028' | 'wp5_resource_checkpoint_029' | 'wp5_resource_checkpoint_030' | 'wp5_resource_checkpoint_031' | 'wp5_resource_checkpoint_032' | 'wp5_resource_checkpoint_033' | 'wp5_resource_checkpoint_034' | 'wp5_resource_checkpoint_035' | 'wp5_resource_checkpoint_036' | 'wp5_resource_checkpoint_037' | 'wp5_resource_checkpoint_038' | 'wp5_resource_checkpoint_039' | 'wp5_resource_checkpoint_040' | 'wp5_resource_checkpoint_041' | 'wp5_resource_checkpoint_042' | 'wp5_resource_checkpoint_043' | 'wp5_resource_checkpoint_044' | 'wp5_resource_checkpoint_045' | 'wp5_resource_checkpoint_046' | 'wp5_resource_checkpoint_047' | 'wp5_resource_checkpoint_048' | 'wp5_resource_checkpoint_049' | 'wp5_resource_checkpoint_050' | 'wp5_resource_checkpoint_051' | 'wp5_resource_checkpoint_052' | 'wp5_resource_checkpoint_053' | 'wp5_resource_checkpoint_054' | 'wp5_resource_checkpoint_055' | 'wp5_resource_checkpoint_056' | 'wp5_resource_checkpoint_057' | 'wp5_resource_checkpoint_058' | 'wp5_resource_checkpoint_059' | 'wp5_resource_checkpoint_060' | 'wp5_resource_checkpoint_061' | 'wp5_resource_checkpoint_062' | 'wp5_resource_checkpoint_063' | 'wp5_resource_checkpoint_064' | 'wp5_resource_checkpoint_065' | 'wp5_resource_dialog_open' | 'wp5_resource_content_visible' | 'wp5_resource_editable' | 'wp5_focus_editor_open' | 'wp5_focus_body_target' | 'wp5_focus_put_received'
  | 'wp5_focus_put_request_content' | 'wp5_focus_put_status' | 'wp5_focus_put_response_content'
  | 'wp5_focus_api_readback' | 'wp5_focus_api_content_equal' | 'wp5_focus_reopen_api'
  | 'wp5_focus_saved_status'
  | 'wp5_focus_reopen_content' | 'notes_blocksuite_reopen' | 'notes_readback_editor_missing'
  | 'wp5_conflict_probe_seed' | 'wp5_conflict_probe_open' | 'wp5_conflict_probe_initial_read'
  | 'wp5_conflict_probe_canvas'
  | 'wp5_conflict_probe_external_write' | 'wp5_conflict_probe_request_path' | 'wp5_conflict_probe_rejected'
  | 'wp5_conflict_probe_hooks_ready' | 'wp5_conflict_probe_timer_scheduled' | 'wp5_conflict_probe_timer_fired'
  | 'wp5_conflict_probe_notes-queue-conflict' | 'wp5_conflict_probe_timeline_bound'
  | 'wp5_conflict_probe_readback' | 'wp5_conflict_probe_reopen' | 'wp5_conflict_probe_recovery_status'
  | 'wp5_conflict_probe_reopen_canvas' | 'wp5_conflict_probe_reopen_ready'
  | 'wp5_conflict_probe_recovery_body' | 'wp5_conflict_probe_recovery_readback'
  | 'notes_frontmatter_seed' | 'notes_frontmatter_reopen' | 'notes_blocksuite_button_click'
  | 'notes_blocksuite_canvas_visible' | 'notes_blocksuite_save_status'
  | 'notes_blocksuite_body_visible' | 'notes_blocksuite_enabled' | 'notes_blocksuite_contenteditable'
  | 'notes_blocksuite_simple_open'
  | 'daily_brief_navigation' | 'daily_brief_heading' | 'daily_brief_saved_readback'
  | 'daily_brief_open_prepare' | 'daily_brief_task_source' | 'daily_brief_project_source'
  | 'daily_brief_project_count' | 'daily_brief_project_label'
  | 'daily_brief_project_click' | 'daily_brief_project_checked'
  | 'daily_brief_sources'
  | 'daily_brief_journal_action'
  | 'daily_brief_journal_source' | 'daily_brief_preview'
  | 'notes_ui_state_unsaved' | 'notes_ui_state_saving' | 'notes_ui_state_conflict'
  | 'notes_ui_state_failed' | 'notes_ui_state_unknown'
  | 'layout_home' | 'layout_projects' | 'layout_activity' | 'layout_agent_health'
  | 'layout_today' | 'layout_journal' | 'layout_calendar' | 'layout_notes' | 'layout_chat'
  | 'chat_session' | 'chat_context_preview' | 'chat_preview_button_visible' | 'chat_preview_button_enabled'
  | 'chat_preview_button_in_viewport' | 'chat_preview_request' | 'chat_preview_result_status' | 'chat_preview_result_source'
  | 'chat_grounding' | 'chat_planning' | 'chat_attachment'
  | 'chat_composer' | 'chat_run' | 'chat_run_waiting' | 'chat_run_completed' | 'chat_run_status_count'
  | 'chat_run_candidates' | 'chat_run_citations' | 'chat_run_citation_panel' | 'chat_run_citation_content' | 'chat_composer_reset'
  | 'chat_reload' | 'chat_stop' | 'chat_return_blank' | 'chat_completion' | 'layout_no_horizontal_overflow';
const observations = new WeakMap<object, Awaited<ReturnType<typeof configurePage>>>();

async function expectNoteSavedStatus(page: Page, observed: Awaited<ReturnType<typeof configurePage>>, assertion: 'wp5_focus_saved_status' | 'notes_blocksuite_saved_status') {
  const status = page.locator('.notes-document-heading [role="status"]');
  observed.setDiagnosticAssertion(assertion);
  try {
    await expect(status).toHaveText('已保存');
  } catch (error) {
    const current = (await status.textContent().catch(() => '')).trim();
    const stateAssertion: DiagnosticAssertion = current === '未保存' ? 'notes_ui_state_unsaved'
      : current === '保存中…' ? 'notes_ui_state_saving'
        : current === '版本冲突' ? 'notes_ui_state_conflict'
          : current === '保存失败' ? 'notes_ui_state_failed' : 'notes_ui_state_unknown';
    observed.setDiagnosticAssertion(stateAssertion);
    throw error;
  }
}

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

async function installChatUiFixtures(page: Page) {
  const firstSession = 'synthetic-layout-session';
  const secondSession = 'synthetic-secondary-session';
  const longHistory = Array.from({ length: 70 }, (_, index) =>
    `synthetic history line ${index + 1} ${'SYNTHETIC '.repeat(10)}`).join('\n');
  const sessions = [
    { session_id: firstSession, title: '合成超长会话标题'.repeat(12), updated_at: '2026-11-04T00:00:00Z' },
    { session_id: secondSession, title: '第二个合成会话', updated_at: '2026-11-03T00:00:00Z' },
  ];
  type SyntheticMessage = { id: string; session_id: string; role: 'user' | 'assistant'; timestamp: string; text: string };
  const messages = new Map<string, SyntheticMessage[]>([
    [firstSession, [
      { id: 'synthetic-history-user-01', session_id: firstSession, role: 'user', timestamp: '2026-11-04T00:00:00Z', text: '合成历史问题：请显示长消息滚动。' },
      { id: 'synthetic-history-assistant-01', session_id: firstSession, role: 'assistant', timestamp: '2026-11-04T00:01:00Z', text: longHistory },
    ]],
    [secondSession, [
      { id: 'synthetic-history-user-02', session_id: secondSession, role: 'user', timestamp: '2026-11-03T00:00:00Z', text: '第二会话合成问题。' },
      { id: 'synthetic-history-assistant-02', session_id: secondSession, role: 'assistant', timestamp: '2026-11-03T00:01:00Z', text: '第二会话合成回答。' },
    ]],
  ]);
  const runStatuses = new Map<string, { status: string; sessionId: string }>();
  let nextOutcome: 'completed' | 'failed' | 'running' = 'completed';
  let runSequence = 0;
  let sessionSequence = 0;
  let releaseFirstRunEvents!: () => void;
  const firstRunEventsGate = new Promise<void>((resolve) => { releaseFirstRunEvents = resolve; });

  const registrations: Array<{ url: string | RegExp; handler: (route: Route) => Promise<void> }> = [];
  const register = async (url: string | RegExp, handler: (route: Route) => Promise<void>) => {
    await page.route(url, handler);
    registrations.push({ url, handler });
  };
  const json = (route: Route, body: unknown, status = 200, headers: Record<string, string> = {}) =>
    route.fulfill({ status, contentType: 'application/json', headers, body: JSON.stringify(body) });

  await register('**/api/chat/sessions?*', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback();
    await json(route, { sessions });
  });
  await register('**/api/chat/sessions', async (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    const sessionId = `synthetic-new-session-${++sessionSequence}`;
    sessions.unshift({ session_id: sessionId, title: `新建合成会话 ${sessionSequence}`, updated_at: '2026-11-04T00:02:00Z' });
    messages.set(sessionId, []);
    await json(route, { session_id: sessionId }, 201);
  });
  await register('**/api/chat/sessions/*/messages', async (route) => {
    const match = new URL(route.request().url()).pathname.match(/\/api\/chat\/sessions\/([^/]+)\/messages$/);
    if (route.request().method() !== 'GET' || !match) return route.fallback();
    await json(route, { messages: messages.get(decodeURIComponent(match[1])) ?? [] });
  });
  await register('**/api/chat/sessions/*/runs', async (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    const match = new URL(route.request().url()).pathname.match(/\/api\/chat\/sessions\/([^/]+)\/runs$/);
    const body = route.request().postDataJSON() as { input?: unknown };
    if (!match || typeof body.input !== 'string') return json(route, { detail: 'invalid synthetic run' }, 400);
    const sessionId = decodeURIComponent(match[1]);
    const runId = `synthetic-ui-run-${++runSequence}`;
    runStatuses.set(runId, { status: nextOutcome, sessionId });
    if (nextOutcome !== 'running') {
      const timestamp = new Date().toISOString();
      const current = messages.get(sessionId) ?? [];
      current.push({ id: `${runId}-user`, session_id: sessionId, role: 'user', timestamp, text: body.input });
      current.push({ id: `${runId}-assistant`, session_id: sessionId, role: 'assistant', timestamp, text: nextOutcome === 'completed' ? '合成完成回复：流式消息已恢复。' : '' });
      messages.set(sessionId, current);
    }
    await json(route, { run_id: runId }, 201);
  });
  await register('**/api/chat/sessions/*/context-preview', async (route) => {
    const match = new URL(route.request().url()).pathname.match(/\/api\/chat\/sessions\/([^/]+)\/context-preview$/);
    if (route.request().method() !== 'POST' || !match) return route.fallback();
    const sessionId = decodeURIComponent(match[1]);
    await json(route, { schema_version: 'context.v1', request_id: 'synthetic-context-request', session_id: sessionId,
      evaluated_at: '2026-11-04T00:00:00Z', status: 'available',
      source_status: { personal_memory: 'available', knowledge: 'none' }, items: [{
        source_kind: 'personal_memory', source_id: 'synthetic-memory-source-01', source_version: 'synthetic-version-1',
        sha256: 'a'.repeat(64), source_timestamp: '2026-11-04T00:00:00Z', fact_kind: 'preference',
        verification_status: 'user_confirmed', state: 'active', expires_at: null,
      }] }, 200, { 'Cache-Control': 'private, no-store' });
  });
  await register('**/api/chat/sessions/*/context-candidates', async (route) => {
    const match = new URL(route.request().url()).pathname.match(/\/api\/chat\/sessions\/([^/]+)\/context-candidates$/);
    if (route.request().method() !== 'POST' || !match) return route.fallback();
    const sessionId = decodeURIComponent(match[1]);
    await json(route, { schema_version: 'context.v1', request_id: 'synthetic-related-request', session_id: sessionId,
      evaluated_at: '2026-11-04T00:00:00Z', status: 'none',
      source_status: { personal_memory: 'none', knowledge: 'none' }, items: [] }, 200,
    { 'Cache-Control': 'private, no-store' });
  });
  await register('**/api/chat/sessions/*/grounding-candidates', async (route) => {
    const match = new URL(route.request().url()).pathname.match(/\/api\/chat\/sessions\/([^/]+)\/grounding-candidates$/);
    if (route.request().method() !== 'POST' || !match) return route.fallback();
    await json(route, { event: 'knowledge.grounding-candidates', version: 1,
      session_id: decodeURIComponent(match[1]), status: 'available', answer_attribution: 'not_established',
      items: [{ citation_id: 'synthetic-citation-01', title: '合成检索来源', sha256: 'b'.repeat(64),
        knowledge_status: 'version_verified', provenance_status: 'verified' }] }, 200,
    { 'Cache-Control': 'private, no-store' });
  });
  await register('**/api/chat/sessions/*/runs/*/knowledge-citations', async (route) => {
    const match = new URL(route.request().url()).pathname.match(/\/api\/chat\/sessions\/([^/]+)\/runs\/([^/]+)\/knowledge-citations$/);
    if (route.request().method() !== 'GET' || !match) return route.fallback();
    await json(route, { event: 'knowledge.citations', version: 1, session_id: decodeURIComponent(match[1]),
      run_id: decodeURIComponent(match[2]), status: 'available', citations: [{ citation_id: 'synthetic-citation-02',
        title: '持久化的合成参考', sha256: 'c'.repeat(64), knowledge_status: 'version_verified', provenance_status: 'verified' }] });
  });
  await register('**/api/tasks?*', async (route) => {
    const url = new URL(route.request().url());
    if (route.request().method() !== 'GET' || url.search !== '?status=all') return route.fallback();
    await json(route, { tasks: [{ source_ref: { id: 'a'.repeat(32), version: 'd'.repeat(64) },
      title: 'Synthetic planning task', status: 'open', due_date: null }] });
  });
  await register('**/api/projects?*', async (route) => {
    const url = new URL(route.request().url());
    if (route.request().method() !== 'GET' || url.search !== '?limit=50&offset=0') return route.fallback();
    await json(route, { status: 'real', items: [{ source_ref: { id: 'synthetic-project-01', version: 'e'.repeat(64) },
      title: 'Synthetic planning project', status: 'active' }] });
  });
  await register('**/api/daily-brief/source-options/journal?*', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback();
    const date = new URL(route.request().url()).searchParams.get('date') ?? '2026-11-04';
    await json(route, { status: 'real', items: [{ id: `${date}:${'f'.repeat(64)}`, version: 'f'.repeat(64), date }] });
  });
  await register('**/api/chat/runs/*/events', async (route) => {
    const runId = new URL(route.request().url()).pathname.split('/').at(-2) ?? '';
    const run = runStatuses.get(runId);
    if (!run) return route.fallback();
    if (runId === 'synthetic-ui-run-1') await firstRunEventsGate;
    if (run.status === 'running') {
      await route.fulfill({ status: 200, contentType: 'text/event-stream', body: 'data: {"event":"tool.started","tool":"synthetic"}\n\n' });
      return;
    }
    if (run.status === 'failed') {
      await route.fulfill({ status: 200, contentType: 'text/event-stream', body: 'data: {"event":"run.failed","error":"Synthetic failure"}\n\n' });
      return;
    }
    const citation = { event: 'knowledge.citations', version: 1, run_id: runId, session_id: run.sessionId,
      status: 'available', citations: [{ citation_id: 'synthetic-citation-03', title: '本轮合成引用', sha256: '9'.repeat(64),
        knowledge_status: 'version_verified', provenance_status: 'verified' }] };
    await route.fulfill({ status: 200, contentType: 'text/event-stream', body: [
      { event: 'message.delta', delta: '合成流式回复。' }, citation,
      { event: 'run.completed', output: '合成完成回复：流式消息已恢复。' },
    ].map((frame) => `data: ${JSON.stringify(frame)}\n\n`).join('') });
  });
  await register('**/api/chat/runs/*/stop', async (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    const runId = new URL(route.request().url()).pathname.split('/').at(-2) ?? '';
    const run = runStatuses.get(runId);
    if (run) run.status = 'cancelled';
    await json(route, { status: 'cancelled' });
  });
  await register('**/api/chat/runs/*', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() !== 'GET' || path.endsWith('/events') || path.endsWith('/stop')) return route.fallback();
    const runId = path.split('/').at(-1) ?? '';
    await json(route, { status: runStatuses.get(runId)?.status ?? 'completed' });
  });

  return {
    firstSession,
    secondSession,
    releaseFirstRunEvents() { releaseFirstRunEvents(); },
    setNextRunOutcome(outcome: 'completed' | 'failed' | 'running') { nextOutcome = outcome; },
    async cleanup() {
      for (const registration of registrations.reverse()) await page.unroute(registration.url, registration.handler);
    },
  };
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
  let wp5BlockSuiteNotePath: string | null = null;
  let notesReadbackFailure: string | null = null;
  let notesSeedStatus: number | null = null;
  const pageErrorNames: string[] = [];
  const pageErrorCategories: string[] = [];
  const pageErrorSources: string[] = [];
  const pageErrorSummaries: string[] = [];
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
  page.on('pageerror', (error) => {
    const allowed = new Set(['Error', 'TypeError', 'ReferenceError', 'RangeError', 'SyntaxError', 'URIError']);
    pageErrorNames.push(allowed.has(error.name) ? error.name : 'unknown');
    const message = error.message.toLowerCase();
    const category = /cannot read properties of (undefined|null)/.test(message) ? 'nullish_property_access'
      : /not a constructor|is not a function/.test(message) ? 'invalid_runtime_symbol'
        : /custom element|already been defined|already registered/.test(message) ? 'custom_element_registration'
          : /failed to fetch dynamically imported module|failed to load (?:module|url)|module script failed|does not provide an export/.test(message) ? 'module_load_failure'
            : /not registered|missing.*extension|unknown block/.test(message) ? 'missing_block_extension'
              : /viewport|service identifier|service not found/.test(message) ? 'view_service_error'
                : /schema|flavour|flavor|block model/.test(message) ? 'block_schema_error'
                  : /workspace|ydoc|y\.doc|document state/.test(message) ? 'document_state_error'
                    : /invalid hook|element type is invalid|suspend|lazy component/.test(message) ? 'react_lazy_error' : 'other';
    pageErrorCategories.push(category);
    const stack = (error.stack ?? '').toLowerCase();
    const source = /blocksuite-markdown-editor|blocksuite/.test(stack) ? 'blocksuite_module'
      : /notespaged|notespage/.test(stack) ? 'notes_page_module'
        : /react-dom/.test(stack) ? 'react_dom'
          : /vite/.test(stack) ? 'vite_runtime' : 'other_module';
    pageErrorSources.push(source);
    pageErrorSummaries.push(safePageErrorSummary(error.message));
  });
  page.on('console', (message) => {
    // Lit catches errors thrown while updating custom elements and logs them,
    // so some BlockSuite initialization faults do not surface as pageerror.
    // Preserve only a fixed category, never the console text or stack.
    if (message.type() === 'error' && /illegal constructor/i.test(message.text())
        && pageErrorSummaries.length < 5) {
      pageErrorNames.push('TypeError');
      pageErrorCategories.push('invalid_runtime_symbol');
      pageErrorSources.push('blocksuite_module');
      pageErrorSummaries.push('illegal_constructor');
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
    const journalAppendPath = route.request().method() === 'POST' && url.pathname === '/api/journal/entries'
      && params.size === 0;
    const taskListPath = route.request().method() === 'GET' && url.pathname === '/api/tasks'
      && exactParams({ status: 'open' });
    const notesPath = params.size === 0 && (
      (url.pathname === '/api/notes' && ['GET', 'POST'].includes(route.request().method()))
      || (route.request().method() === 'GET' && url.pathname === '/api/notes/drafts')
      || (['GET', 'PUT'].includes(route.request().method())
        && /^\/api\/notes\/drafts\/[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(url.pathname))
    );
    const blocksuitePath = (() => {
      if (!wp5BlockSuiteNotePath || params.size !== 0
          || !url.pathname.startsWith(`${wp5BlockSuiteNotePath}/`)) return false;
      const suffix = url.pathname.slice(wp5BlockSuiteNotePath.length);
      const method = route.request().method();
      if (suffix === '/blocksuite/resources') return method === 'POST';
      if (/^\/blocksuite\/resources\/[0-9a-f]{32}$/i.test(suffix)) return ['GET', 'PUT'].includes(method);
      if (/^\/blocksuite\/blobs\/[A-Za-z0-9_-]{43}(?:=|%3D)?$/i.test(suffix)) return ['GET', 'PUT'].includes(method);
      if (suffix === '/blocksuite/snapshots') return method === 'GET';
      if (/^\/blocksuite\/snapshots\/[0-9a-f]{64}$/i.test(suffix)) return method === 'GET';
      if (/^\/blocksuite\/snapshots\/[0-9a-f]{64}\/restore$/i.test(suffix)) return method === 'POST';
      return false;
    })();
    if (url.pathname.startsWith('/api/') && !inboxPath && !authPath
      && !briefPath && !journalSourcePath && !sourceListPath && !homePath && !healthPath
      && !activityPath && !calendarPath && !journalPath && !journalAppendPath && !taskListPath && !notesPath && !blocksuitePath) {
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
    requestRecords, blockedOrigins, wp5AutosaveProbeEvents: [] as Wp5ProbeEvent[],
    setFailureStage(stage: FailureStage) { failureStage = stage; },
    get failureStage() { return failureStage; },
    get inboxPostCount() { return inboxPostCount; },
    allowBlockSuiteNote(path: string) {
      if (!/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(path)) {
        throw new Error('WP5 BlockSuite allowlist requires the synthetic Note UUID');
      }
      wp5BlockSuiteNotePath = `/api/notes/drafts/${path}`;
    },
    get lastInboxBody() { return lastInboxBody; },
    get dailyBriefPostCount() { return dailyBriefPostCount; },
    get lastDailyBriefBody() { return lastDailyBriefBody; },
    get diagnosticAssertion() { return diagnosticAssertion; },
    get activityReadStatuses() { return requestRecords.filter((request) => request.method === 'GET'
      && request.path === '/api/activity').map((request) => request.status).slice(-4); },
    get notesCollectionReadStatuses() { return requestRecords.filter((request) => request.method === 'GET'
      && request.path === '/api/notes').map((request) => request.status).slice(-4); },
    get notesItemReadStatuses() { return requestRecords.filter((request) => request.method === 'GET'
      && /^\/api\/notes\/drafts\/<opaque-id>$/.test(request.path)).map((request) => request.status).slice(-4); },
    get notesWriteStatuses() { return requestRecords.filter((request) => request.method === 'PUT'
      && /^\/api\/notes\/drafts\/<opaque-id>$/.test(request.path)).map((request) => request.status).slice(-8); },
    get notesReadbackFailure() { return notesReadbackFailure; },
    setNotesSeedStatus(status: number) { notesSeedStatus = status; },
    get notesSeedStatus() { return notesSeedStatus; },
    get pageErrorNames() { return pageErrorNames.slice(-5); },
    get pageErrorCategories() { return pageErrorCategories.slice(-5); },
    get pageErrorSources() { return pageErrorSources.slice(-5); },
    get pageErrorSummaries() { return pageErrorSummaries.slice(-1); },
    get dailyBriefReadStatuses() { return requestRecords.filter((request) => request.method === 'GET'
      && request.path === '/api/daily-brief').map((request) => request.status).slice(-4); },
    get inboxId() { return createdInboxId; },
    setDiagnosticAssertion(assertion: DiagnosticAssertion) { diagnosticAssertion = assertion; },
    setNotesReadbackFailure(detail: unknown) {
      const known: Record<string, string> = {
        'App session required': 'session_required',
        'Action is not enabled': 'action_not_enabled',
        'Draft directory permissions are unsafe': 'draft_directory_permissions_unsafe',
        'Directory permissions are unsafe': 'directory_permissions_unsafe',
        'Note file permissions or size are unsafe': 'note_file_permissions_unsafe',
        'Note could not be opened safely': 'note_open_rejected',
        'Note not found': 'note_not_found',
      };
      notesReadbackFailure = typeof detail === 'string' ? known[detail] ?? 'other' : 'other';
    },
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
  const briefHeading = page.locator('#brief-title');
  await expect(briefHeading).toBeVisible({ timeout: 15000 });
  await expect(briefHeading).toHaveText(/每日简报|Daily Brief/);
  const journalSourceReadsBeforeBrief = observed.requestRecords.filter((item) => item.method === 'GET'
    && item.path === '/api/daily-brief/source-options/journal').length;
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
  const taskSourcesResponse = page.waitForResponse((response) => response.request().method() === 'GET'
    && new URL(response.url()).pathname === '/api/tasks'
    && new URL(response.url()).search === '?status=all');
  const projectSourcesResponse = page.waitForResponse((response) => response.request().method() === 'GET'
    && new URL(response.url()).pathname === '/api/projects'
    && new URL(response.url()).search === '?limit=50&offset=0');
  await page.getByRole('button', { name: '手动准备简报' }).click();
  expect((await taskSourcesResponse).status()).toBe(200);
  expect((await projectSourcesResponse).status()).toBe(200);
  observed.setDiagnosticAssertion('daily_brief_task_source');
  await expect(page.getByRole('checkbox', { name: /Synthetic brief task source/ })).toBeVisible();
  observed.setDiagnosticAssertion('daily_brief_project_source');
  await page.waitForFunction(() => document.body.innerText.replace(/[^a-z]/gi, '').toLowerCase()
    .includes('syntheticbriefprojectsource'), undefined, { timeout: 15000 });
  const projectSourceText = page.getByText(/Synthetic brief project source/).last();
  observed.setDiagnosticAssertion('daily_brief_project_count');
  expect(observed.dailyBriefPostCount).toBe(0);
  observed.setDiagnosticAssertion('daily_brief_sources');
  expect(observed.requestRecords.filter((item) => item.method === 'GET'
    && item.path === '/api/daily-brief/source-options/journal')).toHaveLength(journalSourceReadsBeforeBrief);

  observed.setFailureStage('daily_brief_journal');
  observed.setDiagnosticAssertion('daily_brief_journal_action');
  await page.getByRole('button', { name: '加载 Journal 来源' }).click();
  observed.setDiagnosticAssertion('daily_brief_journal_source');
  const journalSource = page.getByRole('checkbox', { name: /Journal 来源 1/ });
  await expect(journalSource).toBeVisible();
  expect(observed.requestRecords.filter((item) => item.method === 'GET'
    && item.path === '/api/daily-brief/source-options/journal').length).toBeGreaterThan(journalSourceReadsBeforeBrief);
  await expect(page.getByText('Synthetic Journal source fixture; never read or published by the UI.')).toHaveCount(0);
  expect(observed.dailyBriefPostCount).toBe(0);

  await page.getByRole('checkbox', { name: /Task · Synthetic brief task source/ }).check();
  observed.setDiagnosticAssertion('daily_brief_project_click');
  await projectSourceText.click({ timeout: 15000 });
  observed.setDiagnosticAssertion('daily_brief_project_checked');
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

for (const viewport of activeViewports) {
  test(`explicit Inbox capture, retry, conflict and source protection at ${viewport.name}`, async ({ page }, testInfo) => {
    // The desktop journey includes the full Core Notes round trip, BlockSuite
    // conflict/recovery, and an unsupported-Markdown preservation probe. Give
    // that composed journey enough total execution budget without extending
    // any individual product wait/assertion or weakening its conditions.
    if (viewport.name === 'desktop-1440x1000') test.setTimeout(60_000);
    if ((wp5RoundtripOnly || wp5ConflictOnly) && viewport.name !== 'desktop-1440x1000') test.skip();
    const observed = await configurePage(page);
    observations.set(testInfo, observed);
    await page.addInitScript((marker) => {
        const state = { marker, active: false, timerHookReady: false, observerReady: false,
          events: [] as { marker: string; at_ms: number; event: string; status?: number }[] };
        const emit = (event: string, status?: number) => {
          if (!state.active) return;
          if (state.events.length >= 64) {
            if (!state.events.some((item) => item.event === 'probe-events-overflow'))
              state.events.push({ marker: state.marker, at_ms: Date.now(), event: 'probe-events-overflow' });
            return;
          }
          state.events.push({ marker: state.marker, at_ms: Date.now(), event, ...(status === undefined ? {} : { status }) });
        };
        Object.defineProperty(window, '__sbWp5AutosaveProbe', { value: state, configurable: true });
        const originalSetTimeout = window.setTimeout.bind(window);
        const originalClearTimeout = window.clearTimeout.bind(window);
        const autosaveTimers = new Set<number>();
        const observedSetTimeout = ((handler: TimerHandler, timeout?: number, ...args: unknown[]) => {
          const isAutosave = state.active && timeout === 900 && typeof handler === 'function';
          if (!isAutosave || typeof handler !== 'function') return originalSetTimeout(handler, timeout, ...args);
          let timerId = 0;
          timerId = originalSetTimeout(() => {
            if (autosaveTimers.delete(timerId)) emit('notes-save-timer-fired');
            handler.apply(window, args);
          }, timeout);
          autosaveTimers.add(timerId);
          emit('notes-save-timer-scheduled');
          return timerId;
        }) as typeof window.setTimeout;
        window.setTimeout = observedSetTimeout;
        state.timerHookReady = window.setTimeout === observedSetTimeout;
        window.clearTimeout = ((timerId?: number) => {
          if (timerId !== undefined && autosaveTimers.delete(timerId)) emit('notes-save-timer-cancelled');
          return originalClearTimeout(timerId);
        }) as typeof window.clearTimeout;
        let previousState = '';
        const observer = new MutationObserver(() => {
          if (!state.active) return;
          const text = document.querySelector('.notes-document-heading [role="status"]')?.textContent?.trim() ?? '';
          const event = text === '未保存' ? 'notes-queue-unsaved'
            : text === '保存中…' ? 'notes-queue-saving'
              : text === '版本冲突' ? 'notes-queue-conflict'
                : text === '已保存' ? 'notes-queue-saved'
                  : text === '保存失败' ? 'notes-queue-failed' : '';
          if (event && event !== previousState) { previousState = event; emit(event); }
        });
        observer.observe(document, { subtree: true, childList: true, characterData: true });
        state.observerReady = true;
      }, WP5_PROBE_MARKER);
    const original = `记一下：合成浏览器验收 ${viewport.name} ${randomUUID()}`;
    await signInAndCreateBlankSession(page, viewport, observed);
    if (wp5RoundtripOnly || wp5ConflictOnly) {
      observed.setFailureStage('notes_navigation');
      observed.setDiagnosticAssertion('wp5_focus_notes_navigation');
      await page.locator('.sidebar nav').getByRole('button', { name: '笔记', exact: true }).click();
      await expect(page).toHaveURL(/\/notes(?:\?.*)?$/);

      if (!wp5ConflictOnly) {
      const title = 'WP5 focused roundtrip';
      const originalBody = `Synthetic body ${randomUUID()}`;
      const markdown = `---\ntitle: ${title}\ntags:\n  - wp5-focused\ncustom: preserve-focused\n---\n\n# ${title}\n\n${originalBody}\n`;
      observed.setFailureStage('notes_frontmatter_seed');
      observed.setDiagnosticAssertion('wp5_focus_note_seed');
      const seeded = await page.evaluate(async (content) => {
        const response = await fetch('/api/notes', { method: 'POST', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content }) });
        return { status: response.status, note: response.ok ? await response.json() : null };
      }, markdown);
      observed.setNotesSeedStatus(seeded.status);
      expect(seeded.status, 'wp5_focus_note_seed').toBe(200);
      const note = seeded.note as { collection: string; path: string };
      expect(note.collection, 'wp5_focus_note_seed_collection').toBe('drafts');
      observed.allowBlockSuiteNote(note.path);

      await page.reload();
      observed.setFailureStage('notes_frontmatter_reopen');
      const noteRead = page.waitForResponse((response) => response.request().method() === 'GET'
        && new URL(response.url()).pathname === `/api/notes/drafts/${note.path}`, { timeout: 5000 });
      await page.getByRole('button', { name: title, exact: true }).click();
      expect((await noteRead).status(), 'wp5_focus_note_open').toBe(200);
      observed.setFailureStage('notes_blocksuite_open');
      const canvas = page.locator('.blocksuite-notes-canvas');
      observed.setDiagnosticAssertion('wp5_focus_editor_open');
      await expect(canvas).toBeVisible({ timeout: 20000 });
      const bodyText = canvas.getByText(originalBody, { exact: true });
      await expect(bodyText, 'wp5_focus_body_target').toBeVisible();
      observed.setDiagnosticAssertion('wp5_focus_api_readback');
      const readback = await page.request.get(`${baseUrl}/api/notes/drafts/${note.path}`);
      expect(readback.status(), 'wp5_focus_api_readback').toBe(200);
      const savedPayload = await readback.json() as { content?: string };
      expect(savedPayload.content, 'wp5_focus_api_content_equal').toContain(originalBody);
      expect(savedPayload.content, 'wp5_focus_frontmatter_preserved').toContain('custom: preserve-focused');

      if (process.env.SB_E2E_WP5_OPEN_ONLY === 'true') return;

      const roundtripResource = async (kind: 'database' | 'edgeless-canvas', buttonName: string, marker: string): Promise<string | undefined> => {
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_001');
        await expect(page.locator('.notes-document-heading [role="status"]'), `wp5_${kind}_note_ready`)
          .toHaveText('已保存', { timeout: 15000 });
        const createButton = page.getByRole('button', { name: buttonName });
        observed.setDiagnosticAssertion('wp5_focus_saved_status');
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_002');
        await expect(createButton, `wp5_${kind}_create_button_enabled`).toBeEnabled();
        const resourcePost = page.waitForResponse((response) => response.request().method() === 'POST'
          && new URL(response.url()).pathname === `/api/notes/drafts/${note.path}/blocksuite/resources`, { timeout: 15000 });
        let resourceRequestFailure: string | null = null;
        const onResourceRequestFailed = (request: import('@playwright/test').Request) => {
          if (request.method() === 'POST' && new URL(request.url()).pathname.endsWith('/blocksuite/resources')) {
            resourceRequestFailure = request.failure()?.errorText ?? 'unknown-request-failure';
          }
        };
        page.on('requestfailed', onResourceRequestFailed);
        const resourceError = page.locator('.notes-document [role="alert"]')
          .filter({ hasText: 'BlockSuite 资源创建失败' });
        const resourceOutcome = Promise.race([
          resourcePost.then(response => ({ response })),
          resourceError.waitFor({ state: 'visible', timeout: 15000 }).then(() => ({ error: true as const }), () => ({ error: false as const })),
        ]);
        const referenceSave = page.waitForResponse((response) => response.request().method() === 'PUT'
          && new URL(response.url()).pathname === `/api/notes/drafts/${note.path}`, { timeout: 15000 });
        observed.setDiagnosticAssertion('wp5_focus_put_received');
        await createButton.click();
        const outcome = await resourceOutcome;
        if ('error' in outcome) {
          const alertText = outcome.error ? await resourceError.textContent() : null;
          page.off('requestfailed', onResourceRequestFailed);
          console.log('WP5_RESOURCE_CREATE_ERROR', JSON.stringify({
            alert: alertText?.slice(0, 240) ?? 'no-response-without-create-error-alert',
            requestFailure: resourceRequestFailure,
          }));
          throw new Error('BlockSuite resource creation failed before the Core POST response');
        }
        page.off('requestfailed', onResourceRequestFailed);
        const created = outcome.response;
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_003');
        expect(created.status(), `wp5_resource_${kind}_create`).toBe(200);
        const resourceInfo = await created.json() as { resource_id: string; filename: string; reference: string; etag: string };
        const resourceDialog = page.getByRole('dialog', { name: kind === 'database' ? 'BlockSuite 数据库资源' : 'BlockSuite Edgeless 资源' });
        observed.setDiagnosticAssertion('wp5_resource_dialog_open');
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_004');
        await expect(resourceDialog).toBeVisible({ timeout: 20000 });
        const referenceResult = await referenceSave;
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_005');
        expect(referenceResult.status(), `wp5_resource_${kind}_reference`).toBe(200);
        let uploadedBlobUrl: string | undefined;
        let uploadedBlobBytes: Buffer | undefined;
        if (kind === 'edgeless-canvas') {
          await expect(resourceDialog.getByRole('status')).toHaveText('BlockSuite Edgeless 画布已就绪', { timeout: 15000 }).catch(async error => {
            console.log('WP5_RESOURCE_CREATE_ERROR', JSON.stringify({ syntheticSetupStatus: (await resourceDialog.getByRole('status').textContent())?.slice(0, 180) }));
            throw error;
          });
          const imageDataUrl = await page.evaluate(() => {
            const canvas = document.createElement('canvas');
            canvas.width = 2; canvas.height = 2;
            const context = canvas.getContext('2d');
            if (!context) throw new Error('Canvas 2D context unavailable');
            context.fillStyle = '#2f80ed'; context.fillRect(0, 0, 2, 2);
            return canvas.toDataURL('image/png');
          });
          uploadedBlobBytes = Buffer.from(imageDataUrl.split(',')[1], 'base64');
          const blobPut = page.waitForResponse((response) => response.request().method() === 'PUT'
            && new URL(response.url()).pathname.includes(`/api/notes/drafts/${note.path}/blocksuite/blobs/`), { timeout: 15000 });
          await resourceDialog.getByLabel('选择 Edgeless 图片').setInputFiles({
            name: 'wp5-edgeless-synthetic.png', mimeType: 'image/png', buffer: uploadedBlobBytes,
          });
          const uploaded = await blobPut;
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_006');
          expect(uploaded.status(), 'wp5_edgeless_blob_create').toBe(201);
          uploadedBlobUrl = uploaded.url();
        }
        const resourceHost = resourceDialog.locator('.blocksuite-resource-host');
        observed.setDiagnosticAssertion('wp5_resource_content_visible');
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_007');
        await expect(resourceHost).toContainText(kind === 'database' ? '测试数据库' : '可编辑测试画布', { timeout: 15000 });
        const editable = resourceHost.locator('[contenteditable="true"]:visible').first();
        observed.setDiagnosticAssertion('wp5_resource_editable');
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_008');
        await expect(editable).toBeVisible().catch(async error => {
          console.log('WP5_RESOURCE_CREATE_ERROR', JSON.stringify(await resourceHost.evaluate(host => {
            const elements: Element[] = [];
            const walk = (root: Element | ShadowRoot) => { for (const child of root.children) { elements.push(child); walk(child); if (child.shadowRoot) walk(child.shadowRoot); } };
            walk(host);
            return { editableTrue: elements.filter(e => e.getAttribute('contenteditable') === 'true').length,
              editableFalse: elements.filter(e => e.getAttribute('contenteditable') === 'false').length,
              richText: elements.filter(e => e.localName === 'rich-text').length,
              hostHeight: Math.round(host.getBoundingClientRect().height),
              connected: host.isConnected,
              readonly: Boolean((host as HTMLElement & { __sbBlockSuiteStore?: { readonly: boolean } }).__sbBlockSuiteStore?.readonly) };
          })));
          throw error;
        });
        observed.setDiagnosticAssertion('wp5_resource_focus');
        await editable.click();
        observed.setDiagnosticAssertion('wp5_resource_type');
        await page.keyboard.press('End');
        await page.keyboard.press('Enter');
        await page.keyboard.insertText(marker);
        observed.setDiagnosticAssertion('wp5_resource_dirty');
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_009');
        await expect(resourceDialog.getByText('有未保存的资源修改')).toBeVisible();
        const resourcePut = page.waitForResponse((response) => response.request().method() === 'PUT'
          && new URL(response.url()).pathname === `/api/notes/drafts/${note.path}/blocksuite/resources/${resourceInfo.resource_id}`, { timeout: 15000 });
        observed.setDiagnosticAssertion('wp5_resource_save');
        await resourceDialog.getByRole('button', { name: '保存资源' }).click();
        const savedResource = await resourcePut;
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_010');
        expect(savedResource.status(), `wp5_resource_${kind}_save`).toBe(200);
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_011');
        expect((await savedResource.json() as { etag: string }).etag).not.toBe(resourceInfo.etag);
        observed.setDiagnosticAssertion('wp5_resource_saved');
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_012');
        await expect(resourceDialog.getByRole('status')).toHaveText('BlockSuite 资源已保存');
        const readResource = await page.request.get(`${baseUrl}/api/notes/drafts/${note.path}/blocksuite/resources/${resourceInfo.resource_id}`);
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_013');
        expect(readResource.status(), `wp5_resource_${kind}_readback`).toBe(200);
        const readPayload = await readResource.json() as { updateB64: string; snapshot: Record<string, unknown> };
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_014');
        expect(readPayload.updateB64.length).toBeGreaterThan(4);
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_015');
        expect(JSON.stringify(readPayload.snapshot)).toContain(marker);
        if (uploadedBlobUrl && uploadedBlobBytes) {
          const blobRead = await page.request.get(uploadedBlobUrl);
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_016');
          expect(blobRead.status(), 'wp5_edgeless_blob_readback').toBe(200);
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_017');
          expect(Buffer.from(await blobRead.body()), 'wp5_edgeless_blob_bytes').toEqual(uploadedBlobBytes);
          const blobId = decodeURIComponent(new URL(uploadedBlobUrl).pathname.split('/').pop() ?? '');
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_018');
          expect(JSON.stringify(readPayload.snapshot), 'wp5_edgeless_blob_reference').toContain(blobId);
        }
        observed.setDiagnosticAssertion('wp5_resource_close');
        await resourceDialog.getByRole('button', { name: '关闭' }).click();
        const resourceLink = page.locator('.blocksuite-notes-canvas a').filter({ hasText: 'BlockSuite resource' }).last();
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_019');
        await expect(resourceLink).toHaveAttribute('href', new RegExp(resourceInfo.filename.replaceAll('.', '\\.')));
        observed.setDiagnosticAssertion('wp5_resource_reopen');
        console.log('WP5_RESOURCE_CREATE_ERROR', JSON.stringify(await resourceLink.evaluate(anchor => ({
          anchorPointer: getComputedStyle(anchor).pointerEvents,
          canvasDisabled: anchor.closest('.blocksuite-notes-canvas')?.getAttribute('data-disabled'),
          width: Math.round(anchor.getBoundingClientRect().width), height: Math.round(anchor.getBoundingClientRect().height),
        }))));
        await resourceLink.click();
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_020');
        await expect(page.getByRole('dialog', { name: kind === 'database' ? 'BlockSuite 数据库资源' : 'BlockSuite Edgeless 资源' })).toBeVisible({ timeout: 15000 });
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_021');
        await expect(page.getByRole('dialog').locator('.blocksuite-resource-host')).toContainText(marker, { timeout: 15000 });
        await page.getByRole('dialog').getByRole('button', { name: '关闭' }).click();
        await page.reload();
        const refreshedNoteRead = page.waitForResponse((response) => response.request().method() === 'GET'
          && new URL(response.url()).pathname === `/api/notes/drafts/${note.path}`, { timeout: 10000 });
        await page.getByRole('button', { name: title, exact: true }).click();
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_022');
        expect((await refreshedNoteRead).status(), `wp5_resource_${kind}_refresh_note`).toBe(200);
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_023');
        await expect(page.locator('.blocksuite-notes-canvas')).toBeVisible({ timeout: 20000 });
        const refreshedLink = page.locator('.blocksuite-notes-canvas a').filter({ hasText: 'BlockSuite resource' }).last();
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_024');
        await expect(refreshedLink).toHaveAttribute('href', new RegExp(resourceInfo.filename.replaceAll('.', '\\.')));
        await refreshedLink.click();
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_025');
        await expect(page.getByRole('dialog').locator('.blocksuite-resource-host')).toContainText(marker, { timeout: 15000 });
        const reopenedDialog = page.getByRole('dialog');
        if (kind === 'edgeless-canvas' && uploadedBlobUrl) {
          const currentNoteResponse = await page.request.get(`${baseUrl}/api/notes/drafts/${note.path}`);
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_026');
          expect(currentNoteResponse.status()).toBe(200);
          const currentNote = await currentNoteResponse.json() as { etag: string };
          const currentResourceResponse = await page.request.get(`${baseUrl}/api/notes/drafts/${note.path}/blocksuite/resources/${resourceInfo.resource_id}`);
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_027');
          expect(currentResourceResponse.status()).toBe(200);
          const currentResource = await currentResourceResponse.json() as {
            schemaVersion: number; resourceId: string; resourceKind: string; docId: string;
            updateB64: string; snapshot: Record<string, unknown>; etag: string; artifact_set_etag: string;
          };
          const laterSnapshot = { ...currentResource.snapshot, e2eExternalEdgelessMutation: randomUUID() };
          const externalWrite = await page.request.put(`${baseUrl}/api/notes/drafts/${note.path}/blocksuite/resources/${resourceInfo.resource_id}`, {
            headers: { Origin: baseOrigin, 'Sec-Fetch-Site': 'same-origin', 'If-Match': `"${currentNote.etag}"`, 'If-Resource-Match': `"${currentResource.etag}"`,
              'If-Artifact-Set-Match': `"${currentResourceResponse.headers()['x-artifact-set-etag']?.replace(/^"|"$/g, '') ?? currentResource.artifact_set_etag}"` },
            data: { schemaVersion: currentResource.schemaVersion, resourceId: currentResource.resourceId,
              resourceKind: currentResource.resourceKind, docId: currentResource.docId,
              updateB64: currentResource.updateB64, snapshot: laterSnapshot },
          });
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_028');
          expect(externalWrite.status(), 'wp5_edgeless_external_change').toBe(200);
        }
        if (kind === 'database') {
          const currentNoteResponse = await page.request.get(`${baseUrl}/api/notes/drafts/${note.path}`);
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_029');
          expect(currentNoteResponse.status()).toBe(200);
          const currentNote = await currentNoteResponse.json() as { etag: string };
          const currentResourceResponse = await page.request.get(`${baseUrl}/api/notes/drafts/${note.path}/blocksuite/resources/${resourceInfo.resource_id}`);
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_030');
          expect(currentResourceResponse.status()).toBe(200);
          const currentResource = await currentResourceResponse.json() as {
            schemaVersion: number; resourceId: string; resourceKind: string; docId: string;
            updateB64: string; snapshot: Record<string, unknown>; etag: string; artifact_set_etag: string;
          };
          const changedSnapshot = { ...currentResource.snapshot, e2eExternalResourceChange: randomUUID() };
          const externalWrite = await page.request.put(`${baseUrl}/api/notes/drafts/${note.path}/blocksuite/resources/${resourceInfo.resource_id}`, {
            headers: { Origin: baseOrigin, 'Sec-Fetch-Site': 'same-origin', 'If-Match': `"${currentNote.etag}"`, 'If-Resource-Match': `"${currentResource.etag}"`,
              'If-Artifact-Set-Match': `"${currentResourceResponse.headers()['x-artifact-set-etag']?.replace(/^"|"$/g, '') ?? currentResource.artifact_set_etag}"` },
            data: { schemaVersion: currentResource.schemaVersion, resourceId: currentResource.resourceId,
              resourceKind: currentResource.resourceKind, docId: currentResource.docId,
              updateB64: currentResource.updateB64, snapshot: changedSnapshot },
          });
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_031');
          console.log('WP5_RESOURCE_CREATE_ERROR', JSON.stringify({ externalStatus: externalWrite.status(), resourceIdentityPresent: Boolean(currentResource.resourceId), artifactHeaderPresent: Boolean(currentResourceResponse.headers()['x-artifact-set-etag']), noteEtagMatches: currentNote.etag === currentResourceResponse.headers()['x-note-etag']?.replace(/^"|"$/g, '') }));
          expect(externalWrite.status(), 'wp5_resource_external_change').toBe(200);
          const conflictEditor = reopenedDialog.locator('.blocksuite-resource-host [contenteditable="true"]:visible').first();
          await conflictEditor.click();
          await page.keyboard.press('End');
          await page.keyboard.press('Enter');
          await page.keyboard.insertText(' unsaved resource conflict');
          await reopenedDialog.getByRole('button', { name: '保存资源' }).click();
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_032');
          await expect(reopenedDialog.getByRole('status')).toContainText('版本冲突（412）；Core 未覆盖现有资源。当前修改仍保留');
          const close = reopenedDialog.getByRole('button', { name: '关闭' });
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_033');
          await expect(close).toBeDisabled();
          const firstDownloadPromise = page.waitForEvent('download');
          await reopenedDialog.getByRole('button', { name: '下载未保存恢复副本' }).click();
          const firstDownload = await firstDownloadPromise;
          const firstCopyPath = await firstDownload.path();
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_034');
          expect(firstCopyPath).toBeTruthy();
          const firstCopy = JSON.parse(await readFile(firstCopyPath!, 'utf8')) as { updateB64: string; snapshot: Record<string, unknown>; complete: boolean };
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_035');
          expect(firstCopy.updateB64.length).toBeGreaterThan(4);
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_036');
          expect(JSON.stringify(firstCopy.snapshot)).toContain('unsaved resource conflict');
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_037');
          expect(firstCopy.complete).toBe(true);
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_038');
          await expect(close).toBeEnabled();
          const conflictEditorAgain = reopenedDialog.locator('.blocksuite-resource-host [contenteditable="true"]:visible').first();
          await conflictEditorAgain.click();
          await page.keyboard.press('End');
          await page.keyboard.press('Enter');
          await page.keyboard.insertText(' later unsaved resource conflict');
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_039');
          await expect(close).toBeDisabled();
          const secondDownloadPromise = page.waitForEvent('download');
          await reopenedDialog.getByRole('button', { name: '下载未保存恢复副本' }).click();
          const secondDownload = await secondDownloadPromise;
          const secondCopyPath = await secondDownload.path();
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_040');
          expect(secondCopyPath).toBeTruthy();
          const secondCopy = JSON.parse(await readFile(secondCopyPath!, 'utf8')) as { updateB64: string; snapshot: Record<string, unknown> };
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_041');
          expect(JSON.stringify(secondCopy.snapshot)).toContain('later unsaved resource conflict');
        }
        if (kind === 'edgeless-canvas' && uploadedBlobUrl) {
          const conflictEditor = reopenedDialog.locator('.blocksuite-resource-host [contenteditable="true"]:visible').first();
          await conflictEditor.click();
          await page.keyboard.press('End');
          await page.keyboard.press('Enter');
          await page.keyboard.insertText(' unsaved image conflict');
          await reopenedDialog.getByRole('button', { name: '保存资源' }).click();
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_042');
          await expect(reopenedDialog.getByRole('status')).toContainText('412');
          const close = reopenedDialog.getByRole('button', { name: '关闭' });
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_043');
          await expect(close).toBeDisabled();
          const copyPromise = page.waitForEvent('download');
          await reopenedDialog.getByRole('button', { name: '下载未保存恢复副本' }).click();
          const copyPath = await (await copyPromise).path();
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_044');
          expect(copyPath).toBeTruthy();
          const recovery = JSON.parse(await readFile(copyPath!, 'utf8')) as {
            updateB64: string; snapshot: Record<string, unknown>; complete: boolean;
            blobs: Array<{ id: string; base64: string }>; missingBlobs: string[];
          };
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_045');
          expect(recovery.complete, 'wp5_edgeless_conflict_copy_complete').toBe(true);
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_046');
          expect(recovery.missingBlobs, 'wp5_edgeless_conflict_missing_blobs').toEqual([]);
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_047');
          expect(recovery.updateB64.length).toBeGreaterThan(4);
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_048');
          expect(JSON.stringify(recovery.snapshot)).toContain('unsaved image conflict');
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_049');
          expect(Buffer.from(recovery.blobs[0].base64, 'base64'), 'wp5_edgeless_conflict_cached_blob').toEqual(uploadedBlobBytes);
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_050');
          await expect(close).toBeEnabled();
        }
        await reopenedDialog.getByRole('button', { name: /关闭/ }).click();
        return uploadedBlobUrl;
      };

      observed.setFailureStage('notes_blocksuite_edit');
      await roundtripResource('database', '新建 BlockSuite Database', 'DB persistence marker');
      await page.reload();
      const beforeEdgelessNoteRead = page.waitForResponse((response) => response.request().method() === 'GET'
        && new URL(response.url()).pathname === `/api/notes/drafts/${note.path}`, { timeout: 10000 });
      await page.getByRole('button', { name: title, exact: true }).click();
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_051');
      expect((await beforeEdgelessNoteRead).status(), 'wp5_before_edgeless_note_read').toBe(200);
      const edgelessBlobUrl = await roundtripResource('edgeless-canvas', '新建 BlockSuite Edgeless 画布', 'Canvas persistence marker');

      observed.setFailureStage('notes_blocksuite_snapshot_restore');
      await page.reload();
      const historyNoteRead = page.waitForResponse((response) => response.request().method() === 'GET'
        && new URL(response.url()).pathname === `/api/notes/drafts/${note.path}`, { timeout: 10000 });
      await page.getByRole('button', { name: title, exact: true }).click();
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_052');
      expect((await historyNoteRead).status(), 'wp5_snapshot_restore_note_read').toBe(200);
      await page.getByRole('button', { name: '查看可恢复版本' }).click();
      const snapshotRows = page.getByRole('list', { name: '可恢复 BlockSuite 快照' }).getByRole('button', { name: '选择并预览' });
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_053');
      expect(await snapshotRows.count(), 'wp5_snapshot_restore_rows').toBeGreaterThan(0);
      const latestSnapshotRead = page.waitForResponse((response) => response.request().method() === 'GET'
        && new URL(response.url()).pathname.includes(`/api/notes/drafts/${note.path}/blocksuite/snapshots/`), { timeout: 15000 });
      await snapshotRows.last().click();
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_054');
      expect((await latestSnapshotRead).status(), 'wp5_snapshot_restore_detail').toBe(200);
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_055');
      await expect(page.getByLabel('BlockSuite 快照预览')).toContainText('图片 · image/png', { timeout: 15000 });
      page.once('dialog', (dialog) => dialog.accept());
      const restoreResponse = page.waitForResponse((response) => response.request().method() === 'POST'
        && new URL(response.url()).pathname.endsWith('/restore'), { timeout: 20000 });
      await page.getByRole('button', { name: '确认恢复此 BlockSuite 快照' }).click();
      const restored = await restoreResponse;
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_056');
      expect(restored.status(), 'wp5_snapshot_restore_status').toBe(200);
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_057');
      expect((await restored.json() as { restored: boolean }).restored, 'wp5_snapshot_restore_ack').toBe(true);
      if (edgelessBlobUrl) {
        const restoredBlob = await page.request.get(edgelessBlobUrl);
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_058');
        expect(restoredBlob.status(), 'wp5_snapshot_restored_blob').toBe(200);
      }
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_059');
      await expect(page.getByText('BlockSuite 快照已恢复，并重新验证了正文与引用资源。')).toBeVisible({ timeout: 15000 });

      observed.setFailureStage('notes_blocksuite_reopen');
      await page.reload();
      const reopenedRead = page.waitForResponse((response) => response.request().method() === 'GET'
        && new URL(response.url()).pathname === `/api/notes/drafts/${note.path}`, { timeout: 5000 });
      await page.getByRole('button', { name: title, exact: true }).click();
      const reopened = await reopenedRead;
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_060');
      expect(reopened.status(), 'wp5_focus_reopen_api').toBe(200);
      const reopenedPayload = await reopened.json() as { content?: string };
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_061');
      expect(reopenedPayload.content, 'wp5_focus_reopen_api').toContain(originalBody);
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_062');
      expect(reopenedPayload.content, 'wp5_focus_reopen_frontmatter').toContain('custom: preserve-focused');
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_063');
      expect((reopenedPayload.content?.match(/\]\(attachments\/[0-9a-f]{32}\.blocksuite\.json\)/g) ?? []).length,
        'wp5_focus_reopen_resource_references').toBe(2);
      observed.setDiagnosticAssertion('wp5_focus_reopen_content');
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_064');
      await expect(page.locator('.notes-raw-source')).toContainText(originalBody, { timeout: 20000 });
      const rawSource = page.locator('.notes-raw-source');
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_065');
      await expect(rawSource).toContainText('custom: preserve-focused');
      }

      // Focused concurrency probe: only synthetic Notes, real Core PUT/If-Match,
      // and the BlockSuite -> Notes autosave queue are exercised here.
      observed.setFailureStage('notes_blocksuite_conflict');
      const conflictTitle = 'WP5 conflict queue probe';
      const baselineText = `Conflict baseline ${randomUUID()}`;
      const baselineMarkdown = `# ${conflictTitle}\n\n${baselineText}\n`;
      observed.setDiagnosticAssertion('wp5_conflict_probe_seed');
      const conflictSeed = await page.evaluate(async (content) => {
        const response = await fetch('/api/notes', { method: 'POST', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content }) });
        return { status: response.status, note: response.ok ? await response.json() as { path: string } : null };
      }, baselineMarkdown);
      expect(conflictSeed.status, 'wp5_conflict_probe_seed').toBe(200);
      const conflictPath = conflictSeed.note!.path;
      const conflictUrlPath = `/api/notes/drafts/${conflictPath}`;
      await page.reload();
      const conflictRead = page.waitForResponse((response) => response.request().method() === 'GET'
        && new URL(response.url()).pathname === conflictUrlPath);
      await page.getByRole('button', { name: conflictTitle, exact: true }).click();
      expect((await conflictRead).status(), 'wp5_conflict_probe_open').toBe(200);
      const conflictCanvas = page.locator('.blocksuite-notes-canvas');
      observed.setDiagnosticAssertion('wp5_conflict_probe_canvas');
      await expect(conflictCanvas).toBeVisible({ timeout: 20000 });
      const baselineBlock = conflictCanvas.getByText(baselineText, { exact: true });
      await expect(baselineBlock).toBeVisible();
      const initialRead = await page.request.get(`${baseUrl}${conflictUrlPath}`);
      expect(initialRead.status(), 'wp5_conflict_probe_initial_read').toBe(200);
      const initialNote = await initialRead.json() as { content: string };
      const externalText = 'WP5 Core concurrent update';
      const externalWrite = await page.evaluate(async ({ path, content, etag }) => {
        const response = await fetch(path, { method: 'PUT', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json', 'If-Match': etag }, body: JSON.stringify({ content }) });
        return response.status;
      }, { path: conflictUrlPath, content: `${initialNote.content}\n${externalText}\n`, etag: initialRead.headers()['etag'] ?? '' });
      expect(externalWrite, 'wp5_conflict_probe_external_write').toBe(200);

      let probeActive = false;
      const recordProbe = (event: string, status?: number) => {
        if (observed.wp5AutosaveProbeEvents.length >= 64) {
          if (!observed.wp5AutosaveProbeEvents.some((item) => item.event === 'probe-events-overflow'))
            observed.wp5AutosaveProbeEvents.push({ marker: WP5_PROBE_MARKER, at_ms: Date.now(), event: 'probe-events-overflow' });
          return;
        }
        observed.wp5AutosaveProbeEvents.push({ marker: WP5_PROBE_MARKER, at_ms: Date.now(), event,
          ...(status === undefined ? {} : { status }) });
      };
      await page.route('**/api/notes/drafts/*', async (route) => {
        const request = route.request();
        const requestUrl = new URL(request.url());
        if (probeActive && request.method() === 'PUT' && requestUrl.pathname === conflictUrlPath) {
          requestUrl.searchParams.set('wp5_probe', WP5_PROBE_MARKER);
          await route.continue({ url: requestUrl.toString() });
          return;
        }
        await route.fallback();
      });
      page.on('request', (request) => {
        if (probeActive && request.method() === 'PUT' && new URL(request.url()).pathname === conflictUrlPath)
          recordProbe('browser-put-request');
      });
      page.on('response', (response) => {
        const request = response.request();
        if (probeActive && request.method() === 'PUT' && new URL(request.url()).pathname === conflictUrlPath)
          recordProbe('browser-put-response', response.status());
      });
      page.on('requestfailed', (request) => {
        if (probeActive && request.method() === 'PUT' && new URL(request.url()).pathname === conflictUrlPath)
          recordProbe('browser-put-requestfailed');
      });
      page.on('requestfinished', (request) => {
        if (probeActive && request.method() === 'PUT' && new URL(request.url()).pathname === conflictUrlPath)
          recordProbe('browser-put-requestfinished');
      });
      const probeReady = await page.evaluate((marker) => {
        const probe = (window as Window & { __sbWp5AutosaveProbe?: {
          marker: string; active: boolean; timerHookReady: boolean; observerReady: boolean;
          events: Wp5ProbeEvent[];
        } }).__sbWp5AutosaveProbe;
        if (!probe || probe.marker !== marker) return { found: false, timerHookReady: false, observerReady: false };
        probe.active = true;
        probe.events.push({ marker: probe.marker, at_ms: Date.now(), event: 'probe-armed' });
        return { found: true, timerHookReady: probe.timerHookReady, observerReady: probe.observerReady };
      }, WP5_PROBE_MARKER);
      observed.setDiagnosticAssertion('wp5_conflict_probe_hooks_ready');
      expect(probeReady, 'wp5_conflict_probe_hooks_ready').toEqual({ found: true, timerHookReady: true, observerReady: true });
      probeActive = true;
      recordProbe('probe-armed');

      const staleRequestPromise = page.waitForRequest((request) => request.method() === 'PUT'
        && new URL(request.url()).pathname === conflictUrlPath, { timeout: 5000 });
      const staleResponsePromise = page.waitForResponse((response) => response.request().method() === 'PUT'
        && new URL(response.url()).pathname === conflictUrlPath, { timeout: 5000 }).then((response) => {
          recordProbe('test-response-matcher-accepted', response.status());
          return response;
        });
      await expect(conflictCanvas).toHaveAttribute('data-disabled', 'false');
      await baselineBlock.click();
      await page.keyboard.press('End');
      await page.keyboard.press('Enter');
      const staleText = 'WP5 stale browser edit must not replace Core';
      await page.keyboard.insertText(staleText);
      observed.setDiagnosticAssertion('notes_blocksuite_conflict_unsaved_state');
      await page.waitForFunction(() => {
        const probe = (window as Window & { __sbWp5AutosaveProbe?: { events: Wp5ProbeEvent[] } }).__sbWp5AutosaveProbe;
        return probe?.events.some((event) => event.event === 'notes-queue-unsaved') ?? false;
      }, { timeout: 5000 });
      recordProbe('notes-queue-unsaved');
      const staleRequest = await staleRequestPromise;
      expect(new URL(staleRequest.url()).pathname, 'wp5_conflict_probe_request_path').toBe(conflictUrlPath);
      recordProbe('test-request-matcher-accepted');
      const staleResponse = await staleResponsePromise;
      expect(staleResponse.status(), 'wp5_conflict_probe_rejected').toBe(412);
      const statusAfterConflict = await page.locator('.notes-document-heading [role="status"]').innerText();
      expect(statusAfterConflict, 'wp5_conflict_probe_rejected').toBe('版本冲突');
      const coreAfterConflict = await page.evaluate(async (path) => {
        const response = await fetch(path, { credentials: 'same-origin' });
        return { status: response.status, content: response.ok ? (await response.json() as { content: string }).content : '' };
      }, conflictUrlPath);
      expect(coreAfterConflict.status, 'wp5_conflict_probe_readback').toBe(200);
      expect(coreAfterConflict.content, 'wp5_conflict_probe_readback').toContain(externalText);
      expect(coreAfterConflict.content, 'wp5_conflict_probe_readback').not.toContain(staleText);

      if (wp5ConflictOnly) {
        const beforeReloadEvents = await page.evaluate(() => {
          const probe = (window as Window & { __sbWp5AutosaveProbe?: { events: Wp5ProbeEvent[] } }).__sbWp5AutosaveProbe;
          return probe?.events ?? [];
        });
        observed.wp5AutosaveProbeEvents.push(...beforeReloadEvents);
        observed.wp5AutosaveProbeEvents.sort((left, right) => left.at_ms - right.at_ms);
      }

      // Leaving the conflict revision clears the blocked queue; a fresh reopen/edit must save normally.
      page.once('dialog', (dialog) => void dialog.accept());
      if (wp5ConflictOnly) {
        recordProbe('probe-reload-start');
        await page.reload();
      }
      else await page.getByRole('button', { name: 'WP5 focused roundtrip', exact: true }).click();
      if (wp5ConflictOnly) {
        const reopenedProbe = await page.evaluate((marker) => {
          const probe = (window as Window & { __sbWp5AutosaveProbe?: {
            marker: string; active: boolean; timerHookReady: boolean; observerReady: boolean;
            events: Wp5ProbeEvent[];
          } }).__sbWp5AutosaveProbe;
          if (!probe || probe.marker !== marker) return { found: false, timerHookReady: false, observerReady: false };
          probe.active = true;
          probe.events.push({ marker: probe.marker, at_ms: Date.now(), event: 'browser-probe-armed' });
          return { found: true, timerHookReady: probe.timerHookReady, observerReady: probe.observerReady };
        }, WP5_PROBE_MARKER);
        observed.setDiagnosticAssertion('wp5_conflict_probe_hooks_ready');
        expect(reopenedProbe, 'wp5_conflict_probe_hooks_ready').toEqual({ found: true, timerHookReady: true, observerReady: true });
        recordProbe('probe-rearmed');
      }
      observed.setDiagnosticAssertion('wp5_conflict_probe_reopen');
      const conflictReopenResponse = page.waitForResponse((response) => response.request().method() === 'GET'
        && new URL(response.url()).pathname === conflictUrlPath);
      await page.getByRole('button', { name: conflictTitle, exact: true }).click();
      await expect(page.locator('.notes-document-heading')).toContainText(conflictPath);
      expect((await conflictReopenResponse).status(), 'wp5_conflict_probe_reopen').toBe(200);
      const reopenedCanvas = page.locator('.blocksuite-notes-canvas');
      observed.setDiagnosticAssertion('wp5_conflict_probe_reopen_canvas');
      await expect(reopenedCanvas).toBeVisible({ timeout: 20000 });
      await expect(reopenedCanvas).toContainText(externalText);
      observed.setDiagnosticAssertion('wp5_conflict_probe_reopen_ready');
      await expect(reopenedCanvas).toHaveAttribute('aria-busy', 'false');
      await expect(reopenedCanvas).toHaveAttribute('data-disabled', 'false');
      const recoveryText = 'WP5 autosave queue recovery';
      observed.setDiagnosticAssertion('wp5_conflict_probe_recovery_status');
      const recoveryResponsePromise = page.waitForResponse((response) => response.request().method() === 'PUT'
        && new URL(response.url()).pathname === conflictUrlPath, { timeout: 5000 }).then((response) => {
          recordProbe('recovery-response-matcher-accepted', response.status());
          return response;
        });
      const recoveryBlock = reopenedCanvas.getByText(externalText, { exact: true });
      await recoveryBlock.click();
      await page.keyboard.press('End');
      await page.keyboard.press('Enter');
      await page.keyboard.insertText(recoveryText);
      const recoveryResponse = await recoveryResponsePromise;
      expect(recoveryResponse.status(), 'wp5_conflict_probe_recovery_status').toBe(200);
      const recoveryBody = await recoveryResponse.json() as { content: string };
      expect(recoveryBody.content, 'wp5_conflict_probe_recovery_body').toContain(recoveryText);
      const recoveredReadback = await page.evaluate(async (path) => {
        const response = await fetch(path, { credentials: 'same-origin' });
        return { status: response.status, content: response.ok ? (await response.json() as { content: string }).content : '' };
      }, conflictUrlPath);
      expect(recoveredReadback.status, 'wp5_conflict_probe_recovery_readback').toBe(200);
      expect(recoveredReadback.content, 'wp5_conflict_probe_recovery_readback').toBe(recoveryBody.content);
      const browserProbeEvents = await page.evaluate(() => {
        const probe = (window as Window & { __sbWp5AutosaveProbe?: { events: Wp5ProbeEvent[] } }).__sbWp5AutosaveProbe;
        return probe?.events ?? [];
      });
      observed.wp5AutosaveProbeEvents.push(...browserProbeEvents);
      observed.wp5AutosaveProbeEvents.sort((left, right) => left.at_ms - right.at_ms);
      for (const [requiredEvent, assertion] of [
        ['notes-save-timer-scheduled', 'wp5_conflict_probe_timer_scheduled'],
        ['notes-save-timer-fired', 'wp5_conflict_probe_timer_fired'],
        ['notes-queue-conflict', 'wp5_conflict_probe_notes-queue-conflict'],
      ] as const) {
        observed.setDiagnosticAssertion(assertion);
        // The conflict is observed before the deliberate reload; the timer and
        // conflict events from that document were copied into the test-level
        // timeline above. The reopened document only contains recovery events.
        expect(observed.wp5AutosaveProbeEvents.some((event) => event.event === requiredEvent), assertion).toBe(true);
      }
      observed.setDiagnosticAssertion('wp5_conflict_probe_timeline_bound');
      observed.wp5AutosaveProbeEvents = boundedWp5ProbeTimeline(observed.wp5AutosaveProbeEvents);
      expect(observed.wp5AutosaveProbeEvents.some((event) => event.event === 'probe-events-overflow'),
        'wp5_conflict_probe_timeline_bound').toBe(false);
      const browserLog = process.env.SB_E2E_WP5_AUTOSAVE_BROWSER_LOG;
      if (browserLog) {
        await writeFile(browserLog, JSON.stringify(observed.wp5AutosaveProbeEvents), { mode: 0o600 });
      }
      return;
    }
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
    // Exercise the regular Chat page in the same Linux Chromium journeys, using
    // session-, Run-, context-, planning- and citation-only synthetic fixtures.
    const chat = await installChatUiFixtures(page);
    observed.setFailureStage('ordinary_chat');
    observed.setDiagnosticAssertion('layout_chat');
    await page.goto('/chat');
    const sessionButtons = page.locator('.chat-session-list button');
    const longTitle = sessionButtons.first().locator('strong');
    await expect(longTitle).toBeVisible();
    const titleLayout = await longTitle.evaluate((element) => ({
      overflow: element.scrollWidth > element.clientWidth,
      ellipsis: getComputedStyle(element).textOverflow,
      whitespace: getComputedStyle(element).whiteSpace,
      date: element.parentElement?.querySelector('small')?.textContent?.trim() ?? '',
      expectedDate: new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric' }).format(new Date('2026-11-04T00:00:00Z')),
    }));
    expect(titleLayout).toEqual({ overflow: true, ellipsis: 'ellipsis', whitespace: 'nowrap', date: titleLayout.expectedDate, expectedDate: titleLayout.expectedDate });
    const secondDate = await sessionButtons.nth(1).locator('small').textContent();
    expect(secondDate?.trim()).toMatch(/^\d{1,2}\/\d{1,2}$/);
    expect(await sessionButtons.first().locator('small').textContent()).toMatch(/^\d{1,2}\/\d{1,2}$/);

    const toolsPanel = page.locator('.chat-context-tools');
    const messages = page.locator('.chat-message-list');
    const input = page.locator('.chat-composer textarea');
    const chatComposer = page.locator('.chat-composer');
    const conversationTitle = page.locator('.chat-conversation > header h2');
    await expect(conversationTitle).toBeVisible();
    expect(await conversationTitle.evaluate((element) => ({
      overflow: element.scrollWidth > element.clientWidth,
      ellipsis: getComputedStyle(element).textOverflow,
      whitespace: getComputedStyle(element).whiteSpace,
    }))).toEqual({ overflow: true, ellipsis: 'ellipsis', whitespace: 'nowrap' });
    await expect(toolsPanel).toBeVisible();
    await expect(toolsPanel).not.toHaveAttribute('open', '');
    await expect(toolsPanel.locator('summary')).toHaveText('上下文与工具');
    await expect(input).toHaveAttribute('rows', '1');
    const collapsed = await page.evaluate(() => {
      const messages = document.querySelector('.chat-message-list')!.getBoundingClientRect();
      const context = document.querySelector('.chat-context-tools')!.getBoundingClientRect();
      const composer = document.querySelector('.chat-composer')!.getBoundingClientRect();
      const title = document.querySelector('.chat-session-list strong')!;
      return { viewport: { width: innerWidth, height: innerHeight }, messageHeight: messages.height,
        contextHeight: context.height, messageScrollHeight: document.querySelector('.chat-message-list')!.scrollHeight,
        messageClientHeight: document.querySelector('.chat-message-list')!.clientHeight,
        ordered: messages.bottom <= context.top && context.bottom <= composer.top,
        titleOverflow: title.scrollWidth > title.clientWidth,
        titleTextOverflow: getComputedStyle(title).textOverflow, titleWhiteSpace: getComputedStyle(title).whiteSpace };
    });
    expect(collapsed.messageHeight, 'chat_messages_remain_primary').toBeGreaterThan(180);
    expect(collapsed.contextHeight, 'chat_context_collapsed_height').toBeLessThan(80);
    expect(collapsed.ordered, 'chat_grid_visual_order').toBe(true);
    expect(collapsed.messageScrollHeight, 'chat_long_history_scrollable').toBeGreaterThan(collapsed.messageClientHeight);
    await messages.evaluate((element) => { element.scrollTop = element.scrollHeight; });
    expect(await messages.evaluate((element) => element.scrollTop), 'chat_history_scroll_position').toBeGreaterThan(0);
    await page.getByText('synthetic history line 70', { exact: false }).last().scrollIntoViewIfNeeded();
    await expect(page.getByText(/synthetic history line 70/).last()).toBeInViewport();
    await messages.evaluate((element) => { element.scrollTop = 0; });
    console.info(`CHAT_UI_COLLAPSED ${JSON.stringify(collapsed)}`);

    observed.setDiagnosticAssertion('chat_session');
    await sessionButtons.nth(1).click();
    await expect(page.getByText('第二会话合成回答。')).toBeVisible();
    await expect(page.getByText(/synthetic history line 70/)).toHaveCount(0);
    await sessionButtons.first().click();
    await expect(page.getByText(/synthetic history line 70/)).toBeVisible();

    await toolsPanel.locator('summary').click();
    await expect(toolsPanel).toHaveAttribute('open', '');
    observed.setDiagnosticAssertion('chat_context_preview');
    const preview = toolsPanel.locator('.chat-context-preview[aria-label="上下文预览"]');
    const grounding = toolsPanel.locator('.chat-context-preview[aria-label="检索参考"]');
    const planning = toolsPanel.locator('.planning-panel');
    await preview.scrollIntoViewIfNeeded();
    await expect(preview).toBeVisible();
    await grounding.scrollIntoViewIfNeeded();
    await expect(grounding).toBeVisible();
    observed.setDiagnosticAssertion('chat_planning');
    await planning.scrollIntoViewIfNeeded();
    await expect(planning).toBeVisible();
    await expect(input).toBeVisible();
    const query = '这是一条仅供浏览器验收的合成问题';
    await input.fill(query);
    const previewButton = preview.getByRole('button', { name: '检索可用上下文' });
    observed.setDiagnosticAssertion('chat_preview_button_visible');
    await expect(previewButton).toBeVisible();
    observed.setDiagnosticAssertion('chat_preview_button_enabled');
    await expect(previewButton).toBeEnabled();
    observed.setDiagnosticAssertion('chat_preview_button_in_viewport');
    const previewButtonRight = await previewButton.evaluate((element) => element.getBoundingClientRect().right);
    expect(previewButtonRight, 'chat_context_action_in_viewport').toBeLessThanOrEqual(await page.evaluate(() => innerWidth));
    observed.setDiagnosticAssertion('chat_preview_request');
    const previewResponsePromise = page.waitForResponse((response) => {
      const request = response.request();
      return request.method() === 'POST' && new URL(response.url()).pathname.endsWith('/context-preview');
    });
    await previewButton.click();
    const previewResponse = await previewResponsePromise;
    expect(previewResponse.status(), 'chat_preview_http_status').toBe(200);
    observed.setDiagnosticAssertion('chat_preview_result_status');
    await expect(preview.locator('[role="status"]').filter({ hasText: '找到可展示的来源元数据' }).first()).toBeVisible();
    observed.setDiagnosticAssertion('chat_preview_result_source');
    await expect(preview.getByText('synthetic-memory-source-01')).toBeVisible();
    observed.setDiagnosticAssertion('chat_grounding');
    await grounding.getByRole('button', { name: '核对 Knowledge 来源' }).click();
    await expect(grounding.getByText('找到已核验来源。')).toBeVisible();
    await expect(grounding.getByText('合成检索来源')).toBeVisible();

    observed.setDiagnosticAssertion('chat_planning');
    await planning.getByRole('button', { name: '开始规划' }).click();
    await planning.getByRole('button', { name: '读取待办和项目候选' }).click();
    const planningTask = planning.getByText('Synthetic planning task');
    await planningTask.scrollIntoViewIfNeeded();
    await expect(planningTask).toBeVisible();
    const planningProject = planning.getByText('Synthetic planning project');
    await planningProject.scrollIntoViewIfNeeded();
    await expect(planningProject).toBeVisible();
    await planning.getByRole('button', { name: '读取获准 Journal 来源' }).click();
    const journalSources = planning.locator('fieldset').filter({ hasText: 'Journal 来源' });
    await journalSources.scrollIntoViewIfNeeded();
    await expect(journalSources).toContainText(/\d{4}-\d{2}-\d{2}/);
    const toolsScroll = await toolsPanel.evaluate((element) => {
      element.scrollTop = element.scrollHeight;
      return { top: element.scrollTop, height: element.clientHeight, content: element.scrollHeight };
    });
    expect(toolsScroll.content, 'chat_tools_panel_content_exceeds_view').toBeGreaterThan(toolsScroll.height);
    expect(toolsScroll.top, 'chat_tools_panel_internal_scroll').toBeGreaterThan(0);
    const opened = await page.evaluate(() => {
      const panel = document.querySelector('.chat-context-tools')!.getBoundingClientRect();
      const messages = document.querySelector('.chat-message-list')!;
      const composer = document.querySelector('.chat-composer')!.getBoundingClientRect();
      const textarea = document.querySelector('.chat-composer textarea')!.getBoundingClientRect();
      return { panelHeight: panel.height, messageHeight: messages.getBoundingClientRect().height,
        messageScrollHeight: messages.scrollHeight, messageClientHeight: messages.clientHeight,
        composerTop: composer.top, composerBottom: composer.bottom, inputTop: textarea.top, inputBottom: textarea.bottom,
        viewportHeight: innerHeight, documentScrollHeight: document.documentElement.scrollHeight,
        composerVisible: composer.bottom > 0 && composer.top < innerHeight };
    });
    expect(opened.panelHeight, 'chat_tools_opened_height').toBeGreaterThan(collapsed.contextHeight);
    expect(opened.messageHeight, 'chat_messages_remain_visible_when_tools_open').toBeGreaterThan(100);
    expect(opened.messageScrollHeight, 'chat_history_remains_scrollable_when_tools_open').toBeGreaterThan(opened.messageClientHeight);
    expect(opened.composerVisible, 'chat_composer_available_when_open').toBe(true);
    await input.scrollIntoViewIfNeeded();
    await expect(input).toBeInViewport();
    console.info(`CHAT_UI_EXPANDED ${JSON.stringify(opened)}`);

    observed.setDiagnosticAssertion('chat_attachment');
    await page.locator('.chat-composer input[type="file"]').setInputFiles({
      name: 'synthetic-chat-attachment.txt', mimeType: 'text/plain', buffer: Buffer.from('synthetic attachment only'),
    });
    await page.getByRole('button', { name: '切换到收录' }).click();
    const captureComposer = page.getByRole('region', { name: '快速收录' });
    await expect(captureComposer.locator('.unified-attachment')).toContainText('synthetic-chat-attachment.txt');
    await captureComposer.getByRole('button', { name: '移除附件' }).click();
    await expect(captureComposer.locator('.unified-attachment')).toHaveCount(0);
    await page.getByRole('group', { name: '输入去向' }).getByRole('button', { name: '对话' }).click();
    await expect(input).toBeVisible();

    observed.setDiagnosticAssertion('chat_composer');
    const singleLineHeight = await input.evaluate((element) => element.getBoundingClientRect().height);
    await input.fill('第一行\n第二行\n第三行');
    const expandedInputHeight = await input.evaluate((element) => element.getBoundingClientRect().height);
    expect(expandedInputHeight, 'chat_composer_auto_grows').toBeGreaterThan(singleLineHeight + 8);
    await page.context().grantPermissions(['clipboard-read', 'clipboard-write'], { origin: baseOrigin });
    const pastedText = Array.from({ length: 24 }, (_, index) => `合成粘贴行 ${index + 1}`).join('\n');
    await input.fill('');
    await page.evaluate(async (text) => navigator.clipboard.writeText(text), pastedText);
    await input.click();
    await input.press('Control+V');
    await expect(input).toHaveValue(pastedText);
    const capped = await input.evaluate((element) => ({ height: element.getBoundingClientRect().height,
      scrollHeight: element.scrollHeight, clientHeight: element.clientHeight, overflowY: getComputedStyle(element).overflowY,
      maxHeight: getComputedStyle(element).maxHeight }));
    expect(capped.height, 'chat_composer_max_height').toBeLessThanOrEqual(161);
    expect(capped.scrollHeight, 'chat_composer_internal_scroll').toBeGreaterThan(capped.clientHeight);
    expect(capped.overflowY, 'chat_composer_overflow_style').toBe('auto');
    expect(capped.maxHeight, 'chat_composer_css_cap').toBe('160px');
    await chatComposer.getByRole('button', { name: '发送', exact: true }).scrollIntoViewIfNeeded();
    await expect(chatComposer.getByRole('button', { name: '发送', exact: true })).toBeInViewport();

    observed.setDiagnosticAssertion('chat_run');
    await page.getByRole('button', { name: '发送', exact: true }).click();
    await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible();
    observed.setDiagnosticAssertion('chat_run_waiting');
    await expect(page.getByText('正在等待回复…', { exact: true })).toHaveCount(1);
    chat.releaseFirstRunEvents();
    observed.setDiagnosticAssertion('chat_run_completed');
    await expect(page.locator('.chat-progress')).toHaveText('已完成');
    observed.setDiagnosticAssertion('chat_run_status_count');
    await expect(page.getByText('已完成', { exact: true })).toHaveCount(1);
    observed.setDiagnosticAssertion('chat_run_candidates');
    await expect(toolsPanel.getByRole('region', { name: '可能相关的来源' })).toContainText('没有匹配的来源');
    observed.setDiagnosticAssertion('chat_run_citation_panel');
    await expect(toolsPanel.locator('.chat-knowledge-citations')).toBeVisible();
    observed.setDiagnosticAssertion('chat_run_citation_content');
    await expect(toolsPanel.locator('.chat-knowledge-citations')).toContainText(/本轮合成引用|持久化的合成参考/);
    observed.setDiagnosticAssertion('chat_composer_reset');
    await expect.poll(() => input.evaluate((element) => element.getBoundingClientRect().height)).toBeLessThanOrEqual(singleLineHeight + 1);

    observed.setDiagnosticAssertion('layout_chat');
    await chat.setNextRunOutcome('failed');
    const failedPrompt = '失败后可恢复的合成问题';
    await input.fill(failedPrompt);
    await page.getByRole('button', { name: '发送', exact: true }).click();
    await expect(page.getByRole('alert')).toBeVisible();
    const failureText = (await page.getByRole('alert').textContent())?.trim() ?? '';
    expect(failureText, 'chat_failure_message_present').not.toBe('');
    await expect(page.getByText(failureText, { exact: true }), 'chat_failure_not_duplicated').toHaveCount(1);
    await expect(page.getByRole('button', { name: '发送', exact: true })).toBeVisible();
    await expect(input).toHaveValue(failedPrompt);

    await chat.setNextRunOutcome('running');
    await input.fill('合成取消测试');
    await page.getByRole('button', { name: '发送', exact: true }).click();
    await expect(page.getByRole('button', { name: '停止', exact: true })).toBeEnabled();
    await page.getByRole('button', { name: '停止', exact: true }).click();
    await expect(page.getByRole('button', { name: '发送', exact: true })).toBeVisible();
    await expect(page.locator('.chat-progress')).toHaveText('已停止');
    await expect(input).toHaveValue('');

    await chat.setNextRunOutcome('completed');
    await input.fill('取消后可继续的合成消息');
    await page.getByRole('button', { name: '发送', exact: true }).click();
    await expect(page.locator('.chat-progress')).toHaveText('已完成');

    observed.setDiagnosticAssertion('chat_reload');
    await page.reload();
    await expect(page.locator('.chat-context-tools')).not.toHaveAttribute('open', '');
    await expect(page.locator('.chat-session-list button').first()).toContainText('合成超长会话标题');
    await expect(page.getByText('取消后可继续的合成消息')).toBeVisible();
    await expect(page.getByText('合成完成回复：流式消息已恢复。').last()).toBeVisible();
    await expect(page.locator('.chat-knowledge-citations')).toContainText('持久化的合成参考');

    await page.locator('.chat-session-heading').getByRole('button', { name: '新对话' }).click();
    await expect(page.getByRole('heading', { name: '新建合成会话 1' })).toBeVisible();
    await expect(page.locator('.chat-empty')).toBeVisible();
    await page.locator('.chat-session-list button').filter({ hasText: '第二个合成会话' }).click();
    await expect(page.getByText('第二会话合成回答。')).toBeVisible();
    await page.locator('.chat-session-list button').filter({ hasText: '合成超长会话标题' }).click();
    await expect(page.getByText('取消后可继续的合成消息')).toBeVisible();
    await page.reload();
    await expect(page.getByText('取消后可继续的合成消息')).toBeVisible();
    await expectNoHorizontalOverflow(page, observed, viewport, 'layout_chat');
    await chat.cleanup();
    observed.setDiagnosticAssertion('layout_chat');
    await page.goto('/chat/blank');
    await expect(page.getByRole('heading', { name: '合成会话 2' })).toBeVisible();
    observed.setDiagnosticAssertion('chat_completion');
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

    const journalDate = page.getByLabel('日期');
    const day = await journalDate.inputValue();
    const syntheticJournalText = `记一下：合成浏览器追加 ${viewport.name} ${randomUUID()}`;
    await page.getByLabel('自然语言记录').fill(syntheticJournalText);
    const refreshedAfterAppend = waitForGetResponse(page, `/api/journal/${day}`);
    const appendResponsePromise = page.waitForResponse((response) =>
      response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/journal/entries',
    { timeout: 5000 });
    observed.setDiagnosticAssertion('journal_append');
    await page.getByRole('button', { name: '追加原话', exact: true }).click();
    const appendResponse = await appendResponsePromise;
    expect(appendResponse.status(), 'journal_append').toBe(200);
    expect((await appendResponse.json()).status, 'journal_append_receipt').toBe('created');
    observed.setDiagnosticAssertion('journal_saved_readback');
    await expect(page.getByText(syntheticJournalText, { exact: true })).toBeVisible();
    expect(await refreshedAfterAppend, 'journal_saved_readback_request').not.toBeNull();

    const reloadReadback = page.waitForResponse((response) => response.request().method() === 'GET'
      && new URL(response.url()).pathname === `/api/journal/${day}`, { timeout: 5000 });
    await page.reload();
    observed.setDiagnosticAssertion('journal_refresh_readback');
    expect((await reloadReadback).status(), 'journal_refresh_readback').toBe(200);
    await expect(page.getByText(syntheticJournalText, { exact: true })).toBeVisible();
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
    let activeNotePath = createdNote.path;
    const editor = page.locator('.blocksuite-notes-canvas [contenteditable="true"]').first();
    await expect(editor).toBeVisible();

    const syntheticNoteBody = `Synthetic mobile note round trip ${viewport.name}`;
    observed.setFailureStage('notes_edit_save');
    const saveNoteResponsePromise = page.waitForResponse((response) => {
      const request = response.request();
      return request.method() === 'PUT' && new URL(response.url()).pathname === `/api/notes/drafts/${activeNotePath}`;
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
      return request.method() === 'GET' && new URL(response.url()).pathname === `/api/notes/drafts/${activeNotePath}`;
    }, { timeout: 5000 });
    observed.setDiagnosticAssertion('notes_readback');
    await page.getByRole('button', { name: syntheticNoteBody, exact: true }).click();
    const readNoteResponse = await readNoteResponsePromise;
    if (readNoteResponse.status() !== 200) {
      const payload = await readNoteResponse.json().catch(() => ({})) as { detail?: unknown };
      observed.setNotesReadbackFailure(payload.detail);
    }
    expect(readNoteResponse.status(), 'notes_readback').toBe(200);
    const persistedNote = await readNoteResponse.json() as { content?: unknown };
    observed.setDiagnosticAssertion('notes_readback_payload');
    expect(typeof persistedNote.content === 'string' && persistedNote.content.includes(syntheticNoteBody),
      'notes_readback_payload').toBe(true);
    const renderedNote = await page.locator('.blocksuite-notes-canvas').innerText();
    const editorContainsReadback = renderedNote.includes(syntheticNoteBody);
    observed.setDiagnosticAssertion(editorContainsReadback ? 'notes_readback' : 'notes_readback_editor_missing');
    expect(editorContainsReadback, 'notes_readback').toBe(true);
    if (viewport.name === 'desktop-1440x1000') {
      // Seed only the isolated synthetic Draft with metadata via the same
      // authenticated Core Notes API, then refresh and exercise the real
      // BlockSuite editor once with the complete Markdown compatibility fixture.
      const syntheticFrontmatter = `---\ntitle: WP5 synthetic note\ntags:\n  - wp5-synthetic\ncustom: preserve-me\n---\n\n# WP5 synthetic note\n\n${syntheticNoteBody}\n`;
      observed.setFailureStage('notes_frontmatter_seed');
      observed.setDiagnosticAssertion('notes_frontmatter_seed');
      const seededResult = await page.evaluate(async (content) => {
        const response = await fetch('/api/notes', { method: 'POST', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content }) });
        return { status: response.status, note: response.ok ? await response.json() : null };
      }, syntheticFrontmatter);
      const seededStatus = seededResult.status;
      observed.setNotesSeedStatus(seededStatus);
      expect(seededStatus, 'notes_seed_synthetic_frontmatter').toBe(200);
      const seededNote = seededResult.note as { collection?: unknown; path?: unknown };
      expect(seededNote.collection).toBe('drafts');
      expect(typeof seededNote.path).toBe('string');
      activeNotePath = seededNote.path as string;
      observed.setFailureStage('notes_frontmatter_reopen');
      observed.setDiagnosticAssertion('notes_frontmatter_reopen');
      await page.reload();
      const frontmatterRead = page.waitForResponse((response) => response.request().method() === 'GET'
        && new URL(response.url()).pathname === `/api/notes/drafts/${activeNotePath}`, { timeout: 5000 });
      await page.getByRole('button', { name: 'WP5 synthetic note', exact: true }).click();
      const rereadFrontmatter = await frontmatterRead;
      expect(rereadFrontmatter.status(), 'notes_frontmatter_read').toBe(200);

      observed.setFailureStage('notes_blocksuite_open');
      observed.setDiagnosticAssertion('notes_blocksuite_default_entry');
      const canvas = page.locator('.blocksuite-notes-canvas');
      observed.setDiagnosticAssertion('notes_blocksuite_canvas_visible');
      // The editor is a large lazy-loaded chunk; do not apply the
      // default 5s assertion timeout to its first mount in CI Chromium.
      await expect(canvas).toBeVisible({ timeout: 20000 });
      observed.setDiagnosticAssertion('notes_blocksuite_save_status');
      await expect(page.getByRole('status').filter({ hasText: 'BlockSuite Page · Core Notes 保存' })).toBeVisible();
      observed.setDiagnosticAssertion('notes_blocksuite_body_visible');
      await expect(canvas).toContainText(syntheticNoteBody);
      observed.setDiagnosticAssertion('notes_blocksuite_enabled');
      await expect(canvas).toHaveAttribute('data-disabled', 'false');
      const tableCell = canvas.locator('affine-table').getByText('synthetic', { exact: true }).last();
      await expect(tableCell, 'notes_blocksuite_table_cell').toBeVisible();
      const tableEditMarker = 'WP5 table cell edit';
      const tableSave = page.waitForResponse((response) => response.request().method() === 'PUT'
        && new URL(response.url()).pathname === `/api/notes/drafts/${activeNotePath}`
        && (response.request().postData() ?? '').includes(tableEditMarker), { timeout: 10000 });
      await tableCell.click();
      await page.keyboard.press('End');
      await page.keyboard.insertText(` ${tableEditMarker}`);
      const tableSaved = await tableSave;
      expect(tableSaved.status(), 'notes_blocksuite_table_save').toBe(200);
      expect((await tableSaved.json() as { content: string }).content).toContain(tableEditMarker);
      // Click the body text itself, rather than the center of its potentially
      // full-page contenteditable ancestor (which can land on the first heading).
      const block = canvas.getByText(syntheticNoteBody, { exact: false });
      observed.setDiagnosticAssertion('notes_blocksuite_contenteditable');
      await expect(block).toContainText(syntheticNoteBody);

      observed.setFailureStage('notes_blocksuite_edit');
      const browserProbeReady = await page.evaluate((marker) => {
        const probe = (window as Window & { __sbWp5AutosaveProbe?: {
          marker: string; active: boolean; timerHookReady: boolean; observerReady: boolean;
          events: Wp5ProbeEvent[];
        } }).__sbWp5AutosaveProbe;
        if (!probe || probe.marker !== marker) return { found: false, timerHookReady: false, observerReady: false };
        probe.active = true;
        probe.events.push({ marker: probe.marker, at_ms: Date.now(), event: 'browser-probe-armed' });
        return { found: true, timerHookReady: probe.timerHookReady, observerReady: probe.observerReady };
      }, WP5_PROBE_MARKER);
      observed.wp5AutosaveProbeEvents.push({ marker: WP5_PROBE_MARKER, at_ms: Date.now(), event: 'browser-probe-armed' });
      observed.setDiagnosticAssertion('wp5_conflict_probe_hooks_ready');
      expect(browserProbeReady, 'wp5_conflict_probe_hooks_ready').toEqual({ found: true, timerHookReady: true, observerReady: true });
      const updatedBody = `WP5 BlockSuite 保存 ${viewport.name}`;
      const blocksuiteSave = page.waitForResponse((response) => response.request().method() === 'PUT'
        && new URL(response.url()).pathname === `/api/notes/drafts/${activeNotePath}`
        && (response.request().postData() ?? '').includes(updatedBody), { timeout: 10000 });
      observed.setDiagnosticAssertion('notes_blocksuite_edit_focus');
      await block.click();
      observed.setDiagnosticAssertion('notes_blocksuite_edit_end');
      await page.keyboard.press('End');
      observed.setDiagnosticAssertion('notes_blocksuite_edit_newline');
      await page.keyboard.press('Enter');
      observed.setDiagnosticAssertion('notes_blocksuite_edit_type');
      await page.keyboard.insertText(updatedBody);
      observed.setDiagnosticAssertion('notes_blocksuite_edit_save_response');
      const saved = await blocksuiteSave;
      expect(saved.status(), 'notes_blocksuite_save').toBe(200);
      const requestedContent = JSON.parse(saved.request().postData() ?? '{}') as { content?: unknown };
      observed.setDiagnosticAssertion('notes_blocksuite_request_content');
      expect(typeof requestedContent.content === 'string' && requestedContent.content.includes(updatedBody),
        'notes_blocksuite_request_content').toBe(true);
      observed.setDiagnosticAssertion('notes_blocksuite_edit_response_body');
      const savedPayload = await saved.json() as { content: string };
      observed.setDiagnosticAssertion('notes_blocksuite_response_matches_request');
      expect(savedPayload.content, 'notes_blocksuite_response_matches_request').toBe(requestedContent.content);
      observed.setDiagnosticAssertion('notes_blocksuite_saved_title');
      expect(savedPayload.content).toContain('title: WP5 synthetic note');
      observed.setDiagnosticAssertion('notes_blocksuite_saved_custom_property');
      expect(savedPayload.content).toContain('custom: preserve-me');
      observed.setDiagnosticAssertion('notes_blocksuite_saved_tag');
      expect(savedPayload.content).toContain('wp5-synthetic');
      observed.setDiagnosticAssertion('notes_blocksuite_saved_edit_text');
      expect(savedPayload.content).toContain(updatedBody);
      await expectNoteSavedStatus(page, observed, 'notes_blocksuite_saved_status');

      // Exercise unsupported syntax introduced during an active BlockSuite
      // session. Preserve the projection through fallback without a Core PUT.
      observed.setFailureStage('notes_blocksuite_edit');
      observed.setDiagnosticAssertion('wp5_unsupported_projection_seed');
      const projectionSeed = page.waitForResponse((response) => response.request().method() === 'POST'
        && new URL(response.url()).pathname === '/api/notes', { timeout: 5000 });
      await page.getByRole('button', { name: '新建 Draft', exact: true }).click();
      const projectionCreated = await projectionSeed;
      expect(projectionCreated.status(), 'wp5_unsupported_projection_seed').toBe(200);
      const projectionNote = await projectionCreated.json() as { path: string };
      const projectionUrl = `/api/notes/drafts/${projectionNote.path}`;
      const projectionCanvas = page.locator('.blocksuite-notes-canvas');
      observed.setDiagnosticAssertion('wp5_unsupported_projection_open');
      await expect(projectionCanvas).toBeVisible({ timeout: 20000 });
      const baseline = projectionCanvas.getByText('未命名笔记', { exact: true });
      await expect(baseline).toBeVisible();
      let projectionPutCount = 0;
      const countProjectionPut = (request: Request) => {
        if (request.method() === 'PUT' && new URL(request.url()).pathname === projectionUrl) projectionPutCount += 1;
      };
      page.on('request', countProjectionPut);
      await baseline.click();
      await page.keyboard.press('End');
      // Paste one literal two-line Markdown fragment; separate Enter actions
      // create independent Page blocks and do not represent Setext source.
      await page.keyboard.insertText('Dynamic Setext heading\n===');
      observed.setDiagnosticAssertion('wp5_unsupported_projection_rejected');
      await expect(page.getByRole('alert')).toContainText('Markdown 原文', { timeout: 5000 });
      const fallbackProjection = page.locator('.notes-raw-source');
      await expect(fallbackProjection).toContainText('Dynamic Setext heading');
      await expect(fallbackProjection).toContainText('===');
      observed.setDiagnosticAssertion('wp5_unsupported_projection_preserved');
      await page.waitForTimeout(1000);
      observed.setDiagnosticAssertion('wp5_unsupported_projection_no_core_put');
      expect(projectionPutCount, 'wp5_unsupported_projection_no_core_put').toBe(0);
      page.off('request', countProjectionPut);
      // Discard this synthetic unsaved projection before continuing the main
      // conflict/recovery journey on its original note.
      page.once('dialog', (dialog) => void dialog.accept());
      const restoreMainNote = page.waitForResponse((response) => response.request().method() === 'GET'
        && new URL(response.url()).pathname === `/api/notes/drafts/${activeNotePath}`, { timeout: 5000 });
      await page.getByRole('button', { name: 'WP5 synthetic note', exact: true }).click();
      expect((await restoreMainNote).status(), 'notes_blocksuite_reopen_navigation_response').toBe(200);
      await expect(page.locator('.blocksuite-notes-canvas')).toBeVisible({ timeout: 20000 });
      await expect(page.locator('.blocksuite-notes-canvas')).toHaveAttribute('data-disabled', 'false');


      // A concurrent Core edit advances the ETag. The stale editor must receive
      // 412 and leave that external content intact rather than overwrite it.
      observed.setFailureStage('notes_blocksuite_conflict');
      const concurrentText = 'WP5 synthetic concurrent Core update';
      observed.setDiagnosticAssertion('notes_blocksuite_conflict_seed');
      const concurrentResult = await page.evaluate(async ({ path, content, etag }) => {
        const response = await fetch(`/api/notes/drafts/${path}`, {
          method: 'PUT', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json', 'If-Match': etag },
          body: JSON.stringify({ content }),
        });
        return { status: response.status };
      }, { path: activeNotePath, content: `${savedPayload.content}\n${concurrentText}\n`, etag: saved.headers()['etag'] ?? '' });
      const concurrentStatus = concurrentResult.status;
      observed.setDiagnosticAssertion(concurrentStatus === 200 ? 'notes_conflict_seed_status_200'
        : concurrentStatus === 401 ? 'notes_conflict_seed_status_401'
          : concurrentStatus === 403 ? 'notes_conflict_seed_status_403'
            : concurrentStatus === 404 ? 'notes_conflict_seed_status_404'
              : concurrentStatus === 409 ? 'notes_conflict_seed_status_409'
                : concurrentStatus === 412 ? 'notes_conflict_seed_status_412'
                  : concurrentStatus === 422 ? 'notes_conflict_seed_status_422'
                    : concurrentStatus === 428 ? 'notes_conflict_seed_status_428' : 'notes_conflict_seed_status_other');
      expect(concurrentStatus, 'notes_seed_concurrent_update').toBe(200);
      observed.setDiagnosticAssertion('notes_blocksuite_conflict_rejected');
      const staleWrite = page.waitForResponse((response) => response.request().method() === 'PUT'
        && new URL(response.url()).pathname === `/api/notes/drafts/${activeNotePath}`, { timeout: 10000 });
      observed.setDiagnosticAssertion('notes_blocksuite_conflict_editor_enabled');
      await expect(page.locator('.blocksuite-notes-canvas')).toHaveAttribute('data-disabled', 'false');
      await block.click();
      await page.keyboard.press('End');
      await page.keyboard.press('Enter');
      await page.keyboard.insertText('WP5 stale browser edit must not replace Core');
      observed.setDiagnosticAssertion('notes_blocksuite_conflict_unsaved_state');
      await expect(page.locator('.notes-document-heading [role="status"]')).toHaveText('未保存', { timeout: 5000 });
      observed.setDiagnosticAssertion('notes_blocksuite_conflict_rejected');
      const rejected = await staleWrite;
      expect(rejected.status(), 'notes_blocksuite_conflict').toBe(412);
      observed.setDiagnosticAssertion('notes_blocksuite_conflict_ui');
      await expect(page.getByRole('status').filter({ hasText: '版本冲突' })).toBeVisible();
      observed.setDiagnosticAssertion('notes_blocksuite_conflict_readback');
      const afterConflict = await page.evaluate(async (path) => {
        const response = await fetch(`/api/notes/drafts/${path}`, { credentials: 'same-origin' });
        return { status: response.status, note: response.ok ? await response.json() as { content: string } : null };
      }, activeNotePath);
      expect(afterConflict.status, 'notes_blocksuite_conflict_readback_status').toBe(200);
      const currentAfterConflict = afterConflict.note;
      expect(currentAfterConflict, 'notes_blocksuite_conflict_readback_payload').not.toBeNull();
      observed.setDiagnosticAssertion('notes_blocksuite_conflict_readback');
      expect(currentAfterConflict?.content).toContain(concurrentText);
      expect(currentAfterConflict?.content).toContain('custom: preserve-me');
      expect(currentAfterConflict?.content).not.toContain('WP5 stale browser edit must not replace Core');

      observed.setFailureStage('notes_blocksuite_reopen');
      page.once('dialog', (dialog) => void dialog.accept());
      const closeRead = page.waitForResponse((response) => response.request().method() === 'GET'
        && new URL(response.url()).pathname === `/api/notes/drafts/${createdNote.path}`, { timeout: 5000 });
      observed.setDiagnosticAssertion('notes_blocksuite_reopen_note_selector');
      await page.getByRole('button', { name: syntheticNoteBody, exact: true }).click();
      observed.setDiagnosticAssertion('notes_blocksuite_reopen_navigation_response');
      expect((await closeRead).status(), 'notes_blocksuite_close_read').toBe(200);
      const blockSuiteRead = page.waitForResponse((response) => response.request().method() === 'GET'
        && new URL(response.url()).pathname === `/api/notes/drafts/${activeNotePath}`, { timeout: 5000 });
      await page.getByRole('button', { name: 'WP5 synthetic note', exact: true }).click();
      const reread = await blockSuiteRead;
      expect(reread.status(), 'notes_blocksuite_reopen').toBe(200);
      const reopenedPayload = await reread.json() as { content: string };
      expect(reopenedPayload.content).toContain(concurrentText);
      expect(reopenedPayload.content).toContain('custom: preserve-me');
      expect(reopenedPayload.content).not.toContain('WP5 stale browser edit must not replace Core');
      observed.setDiagnosticAssertion('notes_blocksuite_reopen_editor_entry');
      const noteHeading = page.locator('.notes-document-heading');
      observed.setDiagnosticAssertion('notes_blocksuite_reopen_heading');
      await expect(noteHeading).toContainText(activeNotePath);
      observed.setDiagnosticAssertion('notes_blocksuite_reopen_saved_status');
      await expect(noteHeading.getByRole('status')).toHaveText('已保存');
      observed.setDiagnosticAssertion('notes_blocksuite_reopen_default_entry');
      observed.setDiagnosticAssertion('notes_blocksuite_reopen_canvas');
      const reopenedCanvas = page.locator('.blocksuite-notes-canvas');
      // Match the first-open lazy chunk gate; the view has been recreated
      // after selecting another Note without repeating the full page reload.
      await expect(reopenedCanvas).toBeVisible({ timeout: 20000 });
      await expect(reopenedCanvas).toContainText(updatedBody, { timeout: 20000 });
      observed.setDiagnosticAssertion('notes_blocksuite_table_reopen');
      await expect(reopenedCanvas).toContainText(tableEditMarker, { timeout: 20000 });
      const reopenScrollMetrics = await reopenedCanvas.evaluate((element) => ({
        scrollHeight: element.scrollHeight, clientHeight: element.clientHeight,
      }));
      observed.setDiagnosticAssertion('notes_blocksuite_reopen_scrollable');
      expect(reopenScrollMetrics.scrollHeight).toBeGreaterThan(reopenScrollMetrics.clientHeight);
      await reopenedCanvas.evaluate((element) => { element.scrollTop = element.scrollHeight; });
      observed.setDiagnosticAssertion('notes_blocksuite_reopen_concurrent_update');
      await expect(reopenedCanvas).toContainText(concurrentText, { timeout: 20000 });
      const quickSwitchEdit = 'WP5 quick fallback edit preserved';
      const quickSwitchSave = page.waitForResponse((response) => response.request().method() === 'PUT'
        && new URL(response.url()).pathname === `/api/notes/drafts/${activeNotePath}`, { timeout: 10000 });
      const reopenedBlock = page.locator('.blocksuite-notes-canvas').getByText(updatedBody, { exact: false });
      observed.setDiagnosticAssertion('notes_blocksuite_quick_switch_edit');
      await reopenedBlock.click();
      await page.keyboard.press('End');
      await page.keyboard.press('Enter');
      await page.keyboard.insertText(quickSwitchEdit);
      observed.setDiagnosticAssertion('notes_blocksuite_quick_switch_fallback');
      await page.getByRole('button', { name: '查看 Markdown 原文' }).click();
      observed.setDiagnosticAssertion('notes_blocksuite_quick_switch_save_response');
      const quickSaved = await quickSwitchSave;
      expect(quickSaved.status(), 'notes_blocksuite_quick_fallback_save').toBe(200);
      await expect(page.locator('.notes-raw-source')).toContainText(updatedBody);
      await expect(page.locator('.notes-raw-source')).toContainText(quickSwitchEdit);
      await expect(page.locator('.notes-raw-source')).toContainText('preserve-me');

      // Setext is accepted by Core but may not be preserved by this Page
      // adapter. If round-trip comparison rejects it, the UI must keep the
      // legacy editor and source text available.
      const latest = await page.request.get(`${baseUrl}/api/notes/drafts/${activeNotePath}`);
      const latestNote = await latest.json() as { content: string };
      const setextContent = `${latestNote.content}\nSetext compatibility heading\n===\n`;
      const setextStatus = await page.evaluate(async ({ path, content, etag }) => {
        const response = await fetch(`/api/notes/drafts/${path}`, {
          method: 'PUT', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json', 'If-Match': etag },
          body: JSON.stringify({ content }),
        });
        return response.status;
      }, { path: activeNotePath, content: setextContent, etag: latest.headers()['etag'] ?? '' });
      observed.setDiagnosticAssertion(setextStatus === 200 ? 'notes_setext_seed_status_200'
        : setextStatus === 401 ? 'notes_setext_seed_status_401'
          : setextStatus === 403 ? 'notes_setext_seed_status_403'
            : setextStatus === 409 ? 'notes_setext_seed_status_409'
              : setextStatus === 412 ? 'notes_setext_seed_status_412'
                : setextStatus === 422 ? 'notes_setext_seed_status_422'
                  : setextStatus === 428 ? 'notes_setext_seed_status_428' : 'notes_setext_seed_status_other');
      expect(setextStatus, 'notes_seed_setext_fallback').toBe(200);
      // The simple Notes roundtrip above already verifies full page refresh.
      // Switch away and reopen here so the focused compatibility check reuses
      // the loaded optional editor chunk instead of depending on a second cold
      // lazy-module load after the refresh.
      await expect(page.locator('.notes-document-heading [role="status"]')).toHaveText('已保存');
      const attachmentRead = page.waitForResponse((response) => response.request().method() === 'GET'
        && /^\/api\/notes\/drafts\/[0-9a-f-]{36}$/i.test(new URL(response.url()).pathname), { timeout: 5000 });
      observed.setDiagnosticAssertion('notes_setext_leave_read');
      await page.getByRole('button', { name: 'WP5 attachment fallback fixture', exact: true }).click();
      expect((await attachmentRead).status(), 'notes_setext_leave_read').toBe(200);
      const fallbackRead = page.waitForResponse((response) => response.request().method() === 'GET'
        && new URL(response.url()).pathname === `/api/notes/drafts/${activeNotePath}`, { timeout: 5000 });
      observed.setDiagnosticAssertion('notes_setext_editor_open');
      await page.getByRole('button', { name: 'WP5 synthetic note', exact: true }).click();
      observed.setDiagnosticAssertion('notes_setext_reopen_read');
      expect((await fallbackRead).status()).toBe(200);
      observed.setDiagnosticAssertion('notes_setext_fallback');
      await expect(page.getByRole('alert')).toContainText('Markdown 原文');
      observed.setDiagnosticAssertion('notes_setext_fallback_render');
      // The Markdown source view preserves syntax that the BlockSuite adapter
      // cannot safely round-trip.
      await expect(page.locator('.notes-raw-source')).toContainText('Setext compatibility heading');

      observed.setFailureStage('notes_blocksuite_reopen');
      observed.setDiagnosticAssertion('notes_attachment_select');
      await page.getByRole('button', { name: 'WP5 attachment fallback fixture', exact: true }).click();
      observed.setDiagnosticAssertion('notes_attachment_open');
      observed.setDiagnosticAssertion('notes_attachment_fallback');
      await expect(page.getByRole('alert')).toContainText('Markdown 原文');
      observed.setDiagnosticAssertion('notes_attachment_render');
      await expect(page.locator('.notes-raw-source')).toContainText('attachments/synthetic-attachment.png');

      observed.setDiagnosticAssertion('notes_unsafe_select');
      await page.getByRole('button', { name: 'WP5 unsafe Markdown fixture', exact: true }).click();
      observed.setDiagnosticAssertion('notes_unsafe_source');
      await expect(page.locator('.notes-raw-source')).toContainText('[[Synthetic Wiki Target]]');
      await expect(page.locator('.notes-raw-source')).toContainText('![[synthetic-embed.png]]');
      await expect(page.locator('.notes-raw-source')).toContainText('<details>');
      await expect(page.locator('.notes-raw-source')).toContainText('> > [!NOTE]');
      observed.setDiagnosticAssertion('notes_unsafe_safety');
      await expect(page.locator('.notes-safety')).toBeVisible();
      observed.setDiagnosticAssertion('notes_unsafe_editor_hidden');
      await expect(page.locator('.notes-raw-source')).toBeVisible();

    }
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
    const notesUiState = await page.evaluate(() => {
      const visible = (element: Element | null) => Boolean(element && (element as HTMLElement).getClientRects().length);
      if (visible(document.querySelector('vite-error-overlay'))) return 'vite_error';
      const fallback = document.querySelector('.notes-document [role="alert"]');
      if (visible(fallback)) {
        const reason = fallback.getAttribute('data-fallback-reason');
        const diagnostic = fallback.getAttribute('data-fallback-diagnostic');
        const stage = fallback.getAttribute('data-fallback-stage');
        if (reason && ['invalid_frontmatter', 'unsupported_syntax', 'markdown_conversion_error', 'unsafe_roundtrip', 'content_mismatch', 'view_initialization_error'].includes(reason)) {
          if (diagnostic && ['illegal_constructor', 'missing_custom_element', 'custom_element_conflict', 'duplicate_root', 'duplicate_note', 'duplicate_paragraph', 'duplicate_database', 'duplicate_data_view', 'duplicate_edgeless_text', 'duplicate_other', 'missing_root', 'blocksuite_error', 'other'].includes(diagnostic)) {
            if (stage && ['extension_setup', 'scope_create', 'host_render', 'host_mount', 'host_update'].includes(stage)) return `fallback_${diagnostic}_${stage}`;
            return `fallback_${diagnostic}`;
          }
          return `fallback_${reason}`;
        }
        return 'fallback_message';
      }
      if (visible(document.querySelector('.blocksuite-notes-canvas'))) return 'blocksuite_canvas';
      if (visible(document.querySelector('.notes-document .ProseMirror'))) return 'unexpected_legacy_editor';
      const root = document.querySelector('#root');
      if (!document.body.childElementCount || (root && !root.childElementCount)) return 'app_blank';
      return 'canvas_missing';
    }).catch(() => 'unavailable');
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
      notes_item_read_statuses: observed?.notesItemReadStatuses ?? [],
      notes_write_statuses: observed?.notesWriteStatuses ?? [],
      notes_readback_failure: observed?.notesReadbackFailure ?? null,
      notes_seed_status: observed?.notesSeedStatus ?? null,
      notes_ui_state: notesUiState,
      page_error_names: observed?.pageErrorNames ?? [],
      page_error_categories: observed?.pageErrorCategories ?? [],
      page_error_sources: observed?.pageErrorSources ?? [],
      page_error_summaries: observed?.pageErrorSummaries ?? [],
      blocksuite_module_statuses: observed?.requestRecords.filter((record) => record.method === 'GET'
        && /blocksuite|node_modules\/\.vite/i.test(record.path)).map((record) => record.status).slice(-8) ?? [],
      daily_brief_get_statuses: observed?.dailyBriefReadStatuses ?? [],
      ...(observed?.wp5AutosaveProbeEvents.length ? {
        wp5_autosave_events: await page.evaluate(() => {
          const probe = (window as Window & { __sbWp5AutosaveProbe?: { events: Wp5ProbeEvent[] } }).__sbWp5AutosaveProbe;
          return probe?.events ?? [];
        }).catch(() => []).then((browserEvents) => boundedWp5ProbeTimeline([...observed.wp5AutosaveProbeEvents, ...browserEvents])),
      } : {}),
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
