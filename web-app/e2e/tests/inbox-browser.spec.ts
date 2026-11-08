import { expect, test, type Locator, type Page, type Request, type Response, type Route, type TestInfo } from '@playwright/test';
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
const wp5RichPageModeOnly = process.env.SB_E2E_WP5_RICH_PAGE_MODE_ONLY === 'true';
const wp5ArchiveUxOnly = process.env.SB_E2E_WP5_ARCHIVE_UX_ONLY === 'true';
const desktopOnly = process.env.SB_E2E_DESKTOP_ONLY === 'true';
const activeViewports = desktopOnly ? [viewports[0]] : viewports;

type RequestRecord = { leg: 'browser' | 'core-upstream'; method: string; path: string; status: number | null; elapsed_ms: number | null; exact_inbox_target?: boolean };
type Wp5ProbeEvent = { marker: 'wp5-conflict-queue'; at_ms: number; event: string; status?: number };
type Wp5DiagnosticStep = 'not_started' | 'rich_page_create' | 'rich_page_open' | 'rich_page_seed_read'
  | 'rich_page_body_edit' | 'rich_page_enter' | 'rich_page_enter_verify' | 'rich_page_ime'
  | 'rich_page_backspace_undo' | 'rich_page_title_boundary' | 'rich_page_title_boundary_before_backspace'
  | 'rich_page_title_boundary_after_backspace' | 'rich_page_title_boundary_state_read' | 'rich_page_title_boundary_title'
  | 'rich_page_title_boundary_body' | 'rich_page_title_boundary_block' | 'rich_page_title_boundary_state_wait_title_mismatch'
  | 'rich_page_title_boundary_state_wait_body_mismatch' | 'rich_page_title_boundary_state_wait_block_mismatch'
  | 'rich_page_title_boundary_state_wait_read_error' | 'rich_page_title_boundary_state_wait_host_missing'
  | 'rich_page_title_boundary_state_wait_store_missing' | 'rich_page_title_boundary_state_wait_store_error'
  | 'rich_page_title_boundary_state_wait_match'
  | 'rich_page_ready_measurement'
  | 'rich_page_first_save' | 'rich_page_first_readback' | 'rich_page_close'
  | 'rich_page_reopen' | 'rich_page_nested_canvas_create' | 'rich_page_nested_canvas_open'
  | 'rich_page_nested_canvas_button_visible' | 'rich_page_nested_canvas_pointer_hit'
  | 'rich_page_nested_canvas_pointer_dispatch' | 'rich_page_nested_canvas_resource_read'
  | 'rich_page_nested_canvas_dialog_ready'
  | 'rich_page_nested_blob_upload' | 'rich_page_nested_canvas_save' | 'rich_page_parent_save'
  | 'rich_page_mode_edgeless' | 'rich_page_mode_edgeless_ready' | 'rich_page_mode_page' | 'rich_page_backup_preview'
  | 'rich_page_snapshot_restore' | 'rich_page_post_restore_reopen' | 'rich_page_conflict'
  | 'rich_page_recovery_copy' | 'rich_page_explicit_fork' | 'archive_ux_style_check'
  | 'archive_ux_toolbar_select' | 'archive_ux_bold' | 'archive_ux_alignment' | 'archive_ux_table' | 'archive_ux_emoji';
type BlockSuiteRequestDiagnostic = { endpoint: 'resource_collection' | 'resource' | 'blob' | 'snapshot' | 'snapshot_restore'; method: 'GET' | 'POST' | 'PUT'; status: number | null };
type CanvasSaveDiagnostic = { checkpoint: 'layout_poll' | 'first_status' | 'second_save_response' | 'readback' | 'saved_status' | 'close_enabled';
  status: 'saved' | 'previous_dirty' | 'unsaved' | 'saving' | 'other'; close_enabled: boolean | null;
  readback_status: number | null; snapshot_matches_readback: boolean | null;
  live_text_bounds: number[][]; saved_text_bounds: number[][]; layout_samples: number[][] };
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
  | 'wp5_canvas_layout_stable'
  | 'notes_conflict_seed_status_200' | 'notes_conflict_seed_status_401'
  | 'notes_conflict_seed_status_403' | 'notes_conflict_seed_status_404'
  | 'notes_conflict_seed_status_409' | 'notes_conflict_seed_status_412'
  | 'notes_conflict_seed_status_422' | 'notes_conflict_seed_status_428'
  | 'notes_conflict_seed_status_other'
  | 'wp5_focus_notes_navigation' | 'wp5_focus_note_seed'
  | 'wp5_resource_checkpoint_066' | 'wp5_resource_checkpoint_067' | 'wp5_resource_checkpoint_068'
  | 'wp5_resource_checkpoint_069' | 'wp5_resource_checkpoint_070' | 'wp5_resource_checkpoint_071' | 'wp5_resource_checkpoint_072' | 'wp5_resource_checkpoint_073' | 'wp5_resource_checkpoint_074' | 'wp5_resource_checkpoint_075'
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
  | 'wp5_archive_align_no_selection' | 'wp5_archive_align_wrong_target' | 'wp5_archive_align_empty_selection'
  | 'wp5_archive_align_cross_block' | 'wp5_archive_align_model_range_missing' | 'wp5_archive_align_native_range_missing'
  | 'wp5_archive_align_native_conversion_missing' | 'wp5_archive_align_logical_selection_mismatch'
  | 'wp5_archive_alignment_selection_ready' | 'wp5_archive_align_action_click'
  | 'wp5_archive_table_vertical_menu_action'
  | 'wp5_archive_database_kanban' | 'wp5_archive_database_seed' | 'wp5_archive_database_add_view'
  | 'wp5_archive_database_menu' | 'wp5_archive_database_group' | 'wp5_archive_database_card'
  | 'wp5_archive_database_reopen_group' | 'wp5_archive_database_reopen_card'
  | 'wp5_archive_database_refresh_group' | 'wp5_archive_database_refresh_card'
  | 'wp5_archive_canvas_reference_lifecycle'
  | 'wp5_archive_emoji_command_visible' | 'wp5_archive_emoji_picker_visible'
  | 'wp5_archive_emoji_search_results' | 'wp5_archive_emoji_dom_target_present'
  | 'wp5_archive_emoji_dom_target_missing' | 'wp5_archive_emoji_insert'
  | 'wp5_archive_html_export' | 'wp5_archive_pdf_preview' | 'wp5_archive_pdf_frame_attached'
  | 'wp5_archive_pdf_body_text' | 'wp5_archive_pdf_export_error' | 'wp5_archive_pdf_no_frame'
  | 'wp5_archive_save_close'
  | 'wp5_archive_saved_reopen' | 'wp5_archive_table_state_reopened'
  | 'wp5_archive_align_model_center' | 'wp5_archive_grip_visibility'
  | 'wp5_archive_drag_geometry' | 'wp5_archive_drag_order' | 'wp5_archive_drag_result'
  | 'wp5_archive_resource_save_status_saved' | 'wp5_archive_resource_save_status_unsaved'
  | 'wp5_archive_resource_save_status_pending' | 'wp5_archive_resource_save_status_error'
  | 'wp5_archive_resource_save_status_other' | 'wp5_archive_resource_save_status_missing'
  | 'wp5_archive_drag_source_not_unique' | 'wp5_archive_drag_target_not_unique'
  | 'wp5_archive_drag_anchor_match' | 'wp5_archive_drag_pointer_routing'
  | 'wp5_archive_drag_source_match' | 'wp5_archive_drag_hit_match'
  | 'wp5_archive_drag_target_locator_match' | 'wp5_archive_drag_hit_source'
  | 'wp5_archive_drag_hit_other_block' | 'wp5_archive_drag_hit_no_block'
  | 'wp5_archive_drag_drop_target_match' | 'wp5_archive_drag_drop_boundary_match'
  | 'wp5_archive_drag_capture_match'
  | 'wp5_archive_drag_parent_missing' | 'wp5_archive_drag_different_parents'
  | 'wp5_archive_drag_same_block' | 'wp5_archive_drag_source_missing_from_parent'
  | 'wp5_archive_drag_target_missing_from_parent' | 'wp5_archive_drag_child_index_mismatch'
  | 'wp5_archive_drag_source_after' | 'wp5_archive_drag_source_before'
  | 'wp5_archive_fixture_split'
  | 'wp5_archive_fixture_click_complete' | 'wp5_archive_fixture_caret_ready'
  | 'wp5_archive_cell_rich_text_missing' | 'wp5_archive_cell_editor_missing' | 'wp5_archive_cell_click_complete'
  | 'wp5_archive_cell_readonly' | 'wp5_archive_cell_caret_not_in_cell' | 'wp5_archive_cell_focus_ready'
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

async function expectEdgelessTextLayoutSettled(dialog: Locator, report: (samples: number[][]) => void) {
  await expect.poll(async () => {
    const result = await dialog.locator('affine-edgeless-text').evaluate(async (element) => {
    const block = element as HTMLElement & { model?: { xywh?: string }; gfx?: { viewport?: { zoom?: number } } };
    const container = block.querySelector('.edgeless-text-block-container');
    const content = block.querySelector('.affine-block-children-container');
    const sample = () => {
      const zoom = block.gfx?.viewport?.zoom;
      const xywh = block.model?.xywh;
      if (!container || !content || typeof zoom !== 'number' || !Number.isFinite(zoom) || zoom <= 0 || typeof xywh !== 'string') return null;
      let bounds: unknown;
      try { bounds = JSON.parse(xywh); } catch { return null; }
      if (!Array.isArray(bounds) || bounds.length !== 4 || !Number.isFinite(bounds[3])) return null;
      const style = getComputedStyle(container);
      const verticalInsets = Number.parseFloat(style.borderTopWidth) + Number.parseFloat(style.borderBottomWidth)
        + Number.parseFloat(style.paddingTop) + Number.parseFloat(style.paddingBottom);
      const paragraph = content.querySelector('affine-paragraph');
      const richText = paragraph?.querySelector('rich-text') ?? null;
      const inlineEditor = richText?.querySelector('.inline-editor') ?? null;
      const height = (target: Element | null) => target ? target.getBoundingClientRect().height / zoom : -1;
      return { measuredHeight: (content.getBoundingClientRect().height + verticalInsets) / zoom, modelHeight: bounds[3], zoom,
        layout: [block.getBoundingClientRect().height / zoom, height(container), height(content),
          height(paragraph), height(richText), height(inlineEditor), Number.parseFloat(style.borderTopWidth), Number.parseFloat(style.borderBottomWidth)] };
    };
    const nextFrame = () => new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
    await nextFrame();
    const first = sample();
    await nextFrame();
    const second = sample();
    if (!first || !second) return { settled: false, samples: [] as number[][] };
    const stable = (left: number, right: number) => Math.abs(left - right) <= 0.25;
    return { settled: stable(first.measuredHeight, first.modelHeight)
      && stable(second.measuredHeight, second.modelHeight)
      && stable(first.measuredHeight, second.measuredHeight)
      && stable(first.modelHeight, second.modelHeight)
      && stable(first.zoom, second.zoom),
      samples: [[first.measuredHeight, first.modelHeight, first.zoom, ...first.layout],
        [second.measuredHeight, second.modelHeight, second.zoom, ...second.layout]] };
    });
    report(result.samples);
    return result.settled;
  }).toBe(true);
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
  const wp5BlockSuiteNotePaths = new Set<string>();
  let wp5BlockSuiteForkCapturePending = false;
  let notesReadbackFailure: string | null = null;
  let notesSeedStatus: number | null = null;
  let wp5Step: Wp5DiagnosticStep = 'not_started';
  let wp5CanvasSaveDiagnostic: CanvasSaveDiagnostic | null = null;
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
      if (params.size !== 0) return false;
      const notePath = [...wp5BlockSuiteNotePaths].find(path => url.pathname.startsWith(`${path}/`));
      if (!notePath) return false;
      const suffix = url.pathname.slice(notePath.length);
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
    if (wp5BlockSuiteForkCapturePending && route.request().method() === 'POST'
        && url.pathname === '/api/notes' && params.size === 0) {
      wp5BlockSuiteForkCapturePending = false;
      const response = await route.fetch();
      const created = await response.json().catch(() => null) as null | { collection?: unknown; path?: unknown };
      if (response.status() === 200 && created?.collection === 'drafts' && typeof created.path === 'string'
          && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(created.path)) {
        // Add only the synthetic fork returned by this one explicitly armed
        // create, before the application can issue its first Blob request.
        wp5BlockSuiteNotePaths.add(`/api/notes/drafts/${created.path}`);
      }
      await route.fulfill({ response });
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
      wp5BlockSuiteNotePaths.add(`/api/notes/drafts/${path}`);
    },
    captureNextBlockSuiteFork() { wp5BlockSuiteForkCapturePending = true; },
    get lastInboxBody() { return lastInboxBody; },
    get dailyBriefPostCount() { return dailyBriefPostCount; },
    get lastDailyBriefBody() { return lastDailyBriefBody; },
    get diagnosticAssertion() { return diagnosticAssertion; },
    get wp5Step() { return wp5Step; },
    setWp5Step(step: Wp5DiagnosticStep) { wp5Step = step; },
    get blockSuiteRequestStatuses(): BlockSuiteRequestDiagnostic[] {
      return requestRecords.filter((request) => request.path.includes('/blocksuite/')).slice(-24).map((request) => ({
        endpoint: request.path.endsWith('/blocksuite/resources') ? 'resource_collection'
          : request.path.includes('/blocksuite/blobs/') ? 'blob'
            : request.path.includes('/blocksuite/snapshots/')
              ? request.path.endsWith('/restore') ? 'snapshot_restore' : 'snapshot'
              : 'resource',
        method: ['GET', 'POST', 'PUT'].includes(request.method) ? request.method as 'GET' | 'POST' | 'PUT' : 'GET',
        status: request.status,
      }));
    },
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
    setWp5CanvasSaveDiagnostic(value: CanvasSaveDiagnostic) { wp5CanvasSaveDiagnostic = value; },
    get wp5CanvasSaveDiagnostic() { return wp5CanvasSaveDiagnostic; },
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
    if (viewport.name === 'desktop-1440x1000') test.setTimeout(wp5ArchiveUxOnly ? 360_000 : wp5RichPageModeOnly ? 120_000 : wp5RoundtripOnly ? 300_000 : 60_000);
    if ((wp5RoundtripOnly || wp5ConflictOnly || wp5RichPageModeOnly || wp5ArchiveUxOnly) && viewport.name !== 'desktop-1440x1000') test.skip();
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
    if (wp5RoundtripOnly || wp5ConflictOnly || wp5RichPageModeOnly || wp5ArchiveUxOnly) {
      observed.setFailureStage('notes_navigation');
      observed.setDiagnosticAssertion('wp5_focus_notes_navigation');
      await page.locator('.sidebar nav').getByRole('button', { name: '笔记', exact: true }).click();
      await expect(page).toHaveURL(/\/notes(?:\?.*)?$/);

      if (!wp5ConflictOnly) {
      if (!wp5RichPageModeOnly && !wp5ArchiveUxOnly) {
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
          await expect(resourceDialog.getByLabel('选择 Edgeless 图片')).toBeEnabled({ timeout: 15000 });
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
          const uploaded = await blobPut.catch(async error => {
            console.log('WP5_RESOURCE_CREATE_ERROR', JSON.stringify({ syntheticUploadStatus: (await resourceDialog.getByRole('status').textContent())?.slice(0, 180) }));
            throw error;
          });
          observed.setDiagnosticAssertion('wp5_resource_checkpoint_006');
          expect(uploaded.status(), 'wp5_edgeless_blob_create').toBe(201);
          uploadedBlobUrl = uploaded.url();
        }
        const resourceHost = resourceDialog.locator('.blocksuite-resource-host');
        observed.setDiagnosticAssertion('wp5_resource_content_visible');
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_007');
        await expect(resourceHost.getByText(kind === 'database' ? '测试数据库' : '独立 Edgeless 便签', { exact: true }).first()).toBeVisible({ timeout: 15000 });
        observed.setDiagnosticAssertion('wp5_resource_focus');
        if (kind === 'edgeless-canvas') {
          // The gfx tool owns pointer events; the rendered text is pointer-events:none.
          const bounds = await resourceHost.getByText('独立 Edgeless 便签', { exact: true }).first().boundingBox();
          expect(bounds).not.toBeNull();
          await page.mouse.dblclick(bounds!.x + bounds!.width / 2, bounds!.y + bounds!.height / 2);
        }
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
        if (kind === 'database') await editable.click();
        observed.setDiagnosticAssertion('wp5_resource_type');
        await page.keyboard.press('End');
        await page.keyboard.press('Enter');
        await page.keyboard.insertText(marker);
        observed.setDiagnosticAssertion('wp5_resource_dirty');
        if (kind === 'database') {
          observed.setDiagnosticAssertion('wp5_archive_database_seed');
          const database = resourceHost.locator('affine-database').first();
          const seededGroup = await database.evaluate(element => {
            const component = element as HTMLElement & { dataSource?: { value?: {
              propertyAdd?: (position: string, options: { type: string; name: string }) => string | undefined;
              propertyDataSet?: (id: string, data: Record<string, unknown>) => void;
              cellValueChange?: (rowId: string, propertyId: string, value: unknown) => void;
            } }; model?: { children?: Array<{ id: string }> } };
            const source = component.dataSource?.value;
            const columnId = source?.propertyAdd?.('end', { type: 'select', name: '状态' });
            // DatabaseBlockDataSource exposes cell/property APIs, while row
            // models remain children of the affine:database block.
            const rowId = component.model?.children?.[0]?.id;
            if (!source || !columnId || !rowId) return false;
            source.propertyDataSet?.(columnId, { options: [{ id: 'wp5-in-progress', value: '进行中', color: '#3b82f6' }] });
            source.cellValueChange?.(rowId, columnId, 'wp5-in-progress');
            return true;
          });
          expect(seededGroup, 'wp5_archive_database_seed').toBe(true);
          const addView = resourceHost.getByTestId('database-add-view-button');
          observed.setDiagnosticAssertion('wp5_archive_database_add_view');
          await expect(addView, 'wp5_archive_database_add_view_button').toBeVisible();
          await addView.click();
          const kanbanMenuItem = page.getByText('看板视图', { exact: true }).last();
          observed.setDiagnosticAssertion('wp5_archive_database_menu');
          await expect(kanbanMenuItem, 'wp5_archive_database_menu').toBeVisible();
          await kanbanMenuItem.click();
          const kanban = resourceHost.locator('affine-data-view-kanban-group');
          observed.setDiagnosticAssertion('wp5_archive_database_group');
          await expect(kanban.first(), 'wp5_archive_database_group').toBeVisible({ timeout: 10000 });
          observed.setDiagnosticAssertion('wp5_archive_database_card');
          await expect(resourceHost.locator('affine-data-view-kanban-card').filter({ hasText: '测试记录' }).first(), 'wp5_archive_database_card')
            .toContainText('测试记录');
        }
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_009');
        await expect(resourceDialog.getByRole('button', { name: '保存资源' })).toBeEnabled();
        const resourcePut = page.waitForResponse((response) => response.request().method() === 'PUT'
          && new URL(response.url()).pathname === `/api/notes/drafts/${note.path}/blocksuite/resources/${resourceInfo.resource_id}`, { timeout: 15000 });
        observed.setDiagnosticAssertion('wp5_resource_save');
        await resourceDialog.getByRole('button', { name: '保存资源' }).click();
        const savedResource = await resourcePut.catch(async error => {
          console.log('WP5_RESOURCE_CREATE_ERROR', JSON.stringify({ syntheticSaveStatus: (await resourceDialog.getByRole('status').textContent())?.slice(0, 180) }));
          throw error;
        });
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_010');
        expect(savedResource.status(), `wp5_resource_${kind}_save`).toBe(200);
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_011');
        expect((await savedResource.json() as { etag: string }).etag).not.toBe(resourceInfo.etag);
        observed.setDiagnosticAssertion('wp5_resource_saved');
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_012');
        for (let retry = 0; retry < 2; retry += 1) {
          await expect(resourceDialog.getByRole('status')).toHaveText(/^(BlockSuite 资源已保存|先前版本已保存；有未保存的资源修改|有未保存的资源修改)$/);
          if ((await resourceDialog.getByRole('status').textContent()) === 'BlockSuite 资源已保存') break;
          const latestPut = page.waitForResponse(response => response.request().method() === 'PUT'
            && new URL(response.url()).pathname === `/api/notes/drafts/${note.path}/blocksuite/resources/${resourceInfo.resource_id}`);
          await resourceDialog.getByRole('button', { name: '保存资源' }).click();
          expect((await latestPut).status()).toBe(200);
        }
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
        const sameResourceDialog = page.getByRole('dialog', { name: kind === 'database' ? 'BlockSuite 数据库资源' : 'BlockSuite Edgeless 资源' });
        if (kind === 'database') {
          observed.setDiagnosticAssertion('wp5_archive_database_reopen_group');
          await expect(sameResourceDialog.locator('affine-data-view-kanban-group').first(), 'wp5_archive_database_reopen_group')
            .toBeVisible({ timeout: 10000 });
          observed.setDiagnosticAssertion('wp5_archive_database_reopen_card');
          await expect(sameResourceDialog.locator('affine-data-view-kanban-card').filter({ hasText: '测试记录' }).first(), 'wp5_archive_database_reopen_card')
            .toContainText('测试记录');
        }
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_021');
        await expect(page.getByRole('dialog').locator('.blocksuite-resource-host').getByText(marker, { exact: false }).first()).toBeVisible({ timeout: 15000 });
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
        if (kind === 'database') {
          const refreshedDatabaseDialog = page.getByRole('dialog', { name: 'BlockSuite 数据库资源' });
          observed.setDiagnosticAssertion('wp5_archive_database_refresh_group');
          await expect(refreshedDatabaseDialog.locator('affine-data-view-kanban-group').first(), 'wp5_archive_database_refresh_group')
            .toBeVisible({ timeout: 10000 });
          observed.setDiagnosticAssertion('wp5_archive_database_refresh_card');
          await expect(refreshedDatabaseDialog.locator('affine-data-view-kanban-card').filter({ hasText: '测试记录' }).first(), 'wp5_archive_database_refresh_card')
            .toContainText('测试记录');
        }
        await expect(page.getByRole('dialog').locator('.blocksuite-resource-host').getByText(marker, { exact: false }).first()).toBeVisible({ timeout: 15000 });
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
          const bounds = await reopenedDialog.locator('affine-edgeless-text').first().boundingBox();
          expect(bounds).not.toBeNull();
          await page.mouse.click(bounds!.x + 10, bounds!.y + 10);
          await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => resolve())));
          await page.mouse.dblclick(bounds!.x + 10, bounds!.y + 10, { delay: 100 });
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

      if (process.env.SB_E2E_WP5_OPEN_ONLY !== 'true') {
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
      await expect(snapshotRows.first(), 'wp5_snapshot_restore_rows').toBeVisible({ timeout: 15000 });
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
      await expect(page.locator('.blocksuite-notes-canvas').getByText(originalBody, { exact: true })).toBeVisible({ timeout: 20000 });
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_065');
      await expect(page.locator('.blocksuite-notes-canvas a').filter({ hasText: 'BlockSuite resource' })).toHaveCount(2);
      }
      }

      // Rich Page uses a dedicated synthetic Draft. This covers its controlled
      // Yjs + snapshot + Markdown receipt path without changing the seed Note.
      observed.setFailureStage('notes_blocksuite_open');
      observed.setWp5Step('rich_page_create');
      const richNoteCreate = page.waitForResponse(response => response.request().method() === 'POST'
        && new URL(response.url()).pathname === '/api/notes', { timeout: 15000 });
      await page.addInitScript(() => { (window as Window & { __wp5ReadyEvents?: unknown[] }).__wp5ReadyEvents = [];
        window.addEventListener('sb:blocksuite-editor-ready', event => (window as Window & { __wp5ReadyEvents?: unknown[] }).__wp5ReadyEvents?.push((event as CustomEvent).detail)); });
      await page.evaluate(() => { (window as Window & { __wp5ReadyEvents?: unknown[] }).__wp5ReadyEvents = [];
        window.addEventListener('sb:blocksuite-editor-ready', event => (window as Window & { __wp5ReadyEvents?: unknown[] }).__wp5ReadyEvents?.push((event as CustomEvent).detail)); });
      await page.getByRole('button', { name: '新建笔记', exact: true }).click();
      const richCreatedResponse = await richNoteCreate;
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_001');
      expect(richCreatedResponse.status(), 'wp5_rich_page_note_created').toBe(200);
      const richCreated = await richCreatedResponse.json() as { collection: string; path: string; content: string };
      expect(richCreated.collection, 'wp5_rich_page_synthetic_draft').toBe('drafts');
      observed.allowBlockSuiteNote(richCreated.path);
      observed.setWp5Step('rich_page_open');
      const richResourceCreate = page.waitForResponse(response => response.request().method() === 'POST'
        && new URL(response.url()).pathname === `/api/notes/drafts/${richCreated.path}/blocksuite/resources`, { timeout: 20000 });
      const richDialog = page.locator('.blocksuite-resource-inline');
      await expect(richDialog).toBeVisible({ timeout: 25000 });
      await expect(page.getByRole('dialog', { name: '笔记编辑器' })).toHaveCount(0);
      observed.setDiagnosticAssertion('wp5_resource_dialog_open');
      const richResourceResponse = await richResourceCreate;
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_002');
      expect(richResourceResponse.status(), 'wp5_rich_page_resource_created').toBe(200);
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_003');
      const richResourceInfo = await richResourceResponse.json() as { resource_id: string };
      await expect(richDialog.locator('.blocksuite-resource-host.sb-archive-surface')).toBeVisible({ timeout: 15000 });
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_004');
      await expect(richDialog.getByRole('button', { name: '导出 HTML' })).toBeVisible();
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_005');
      await expect(richDialog.locator('.blocksuite-resource-host .affine-page-viewport')).toBeVisible();
      const richText = 'Synthetic rich page round trip';
      observed.setWp5Step('rich_page_seed_read');
      const richParagraphTexts = await richDialog.locator('.blocksuite-resource-host').evaluate(host => {
        const store = (host as HTMLDivElement & { __sbBlockSuiteStore?: { getBlocksByFlavour: (flavour: string) => Array<{ model: { props: { text?: { toString: () => string } } } }> } }).__sbBlockSuiteStore;
        return store?.getBlocksByFlavour('affine:paragraph').map(({ model }) => model.props.text?.toString() ?? '') ?? [];
      });
      expect(richParagraphTexts).toEqual(['新建笔记', '']);
      await expect(richDialog.locator('[data-sb-document-title-block="true"]')).toBeHidden();
      await expect(richDialog.locator('.document-heading')).toHaveCount(1);
      const richBody = richDialog.locator('.affine-page-viewport affine-paragraph').nth(1);
      await expect(richBody).toBeVisible({ timeout: 15000 });
      observed.setDiagnosticAssertion('wp5_resource_content_visible');
      observed.setWp5Step('rich_page_body_edit');
      await richBody.click();
      await expect.poll(() => richBody.locator('rich-text .inline-editor').evaluate(editor => {
        const selection = window.getSelection();
        return editor.getAttribute('contenteditable') === 'true' && Boolean(selection?.anchorNode && editor.contains(selection.anchorNode));
      })).toBe(true);
      await page.keyboard.insertText(richText);
      observed.setWp5Step('rich_page_enter');
      await page.keyboard.press('Enter');
      const secondRichLine = 'Second paragraph after Enter';
      await page.keyboard.insertText(secondRichLine);
      const liveEnterEvidence = await richDialog.locator('.blocksuite-resource-host').evaluate(host => {
        const store = (host as HTMLDivElement & { __sbBlockSuiteStore?: any }).__sbBlockSuiteStore;
        const blocks = (store?.getBlocksByFlavour('affine:paragraph') ?? []).map(({ model }: any, index: number) => ({
          id: model.id, parentId: store.getParent(model)?.id, index,
          text: model.props.text?.toString?.() ?? '', type: model.props.type,
        }));
        const active = document.activeElement as HTMLElement | null;
        const selection = window.getSelection();
        const editor = active?.getAttribute('contenteditable') === 'true' ? active : selection?.anchorNode?.parentElement?.closest('[contenteditable="true"]');
        return { activeTag: active?.tagName ?? null, activeRole: active?.getAttribute('role') ?? null,
          editorTag: editor?.tagName ?? null, contenteditable: editor?.getAttribute('contenteditable') ?? null,
          selectionText: selection?.toString() ?? '', anchorOffset: selection?.anchorOffset ?? null,
          anchorInsideEditor: Boolean(selection?.anchorNode && editor?.contains(selection.anchorNode)), blocks };
      });
      console.log(`WP5_NATIVE_ENTER_DOM ${JSON.stringify(liveEnterEvidence)}`);
      const firstEnterBlock = liveEnterEvidence.blocks.find(block => block.text.includes(richText));
      const secondEnterBlock = liveEnterEvidence.blocks.find(block => block.text.includes(secondRichLine));
      expect(firstEnterBlock?.text, 'wp5_rich_page_enter_first_paragraph_exact').toBe(richText);
      expect(secondEnterBlock?.text, 'wp5_rich_page_enter_second_paragraph_content').toContain(secondRichLine);
      expect(firstEnterBlock?.id, 'wp5_rich_page_enter_distinct_block_ids').toBeTruthy();
      expect(secondEnterBlock?.id, 'wp5_rich_page_enter_distinct_block_ids').toBeTruthy();
      expect(firstEnterBlock?.id, 'wp5_rich_page_enter_distinct_block_ids').not.toBe(secondEnterBlock?.id);
      expect(firstEnterBlock?.parentId, 'wp5_rich_page_enter_same_parent').toBe(secondEnterBlock?.parentId);
      expect(firstEnterBlock!.index, 'wp5_rich_page_enter_order').toBeLessThan(secondEnterBlock!.index);
      expect(liveEnterEvidence.anchorInsideEditor).toBe(true);
      observed.setWp5Step('rich_page_enter_verify');
      await expect(richDialog.locator('affine-paragraph').filter({ hasText: richText })).toBeVisible();
      await expect(richDialog.locator('affine-paragraph').filter({ hasText: secondRichLine })).toBeVisible();
      const secondLineEditor = richDialog.locator('affine-paragraph').filter({ hasText: secondRichLine }).last().locator('rich-text .inline-editor');
      observed.setWp5Step('rich_page_ime');
      await secondLineEditor.evaluate(editor => editor.dispatchEvent(new CompositionEvent('compositionstart', { bubbles: true, data: '' })));
      await page.keyboard.insertText(' 中文输入法内容');
      await secondLineEditor.evaluate(editor => editor.dispatchEvent(new CompositionEvent('compositionend', { bubbles: true, data: '中文输入法内容' })));
      await expect(richDialog.locator('affine-paragraph').filter({ hasText: '中文输入法内容' })).toBeVisible();
      const backspaceProbe = ` backspace-probe-${randomUUID()}`;
      await page.keyboard.insertText(backspaceProbe);
      await page.keyboard.press('Backspace');
      await expect(richDialog.locator('affine-paragraph').filter({ hasText: backspaceProbe.slice(0, -1) })).toBeVisible();
      const undoProbe = ` undo-probe-${randomUUID()}`;
      observed.setWp5Step('rich_page_backspace_undo');
      await page.keyboard.insertText(undoProbe);
      await page.keyboard.press('Control+z');
      await expect(richDialog.locator('affine-paragraph').filter({ hasText: undoProbe })).toHaveCount(0);
      await page.keyboard.press('Control+Shift+z');
      await expect(richDialog.locator('affine-paragraph').filter({ hasText: undoProbe })).toBeVisible();
      const firstBodyBlock = richDialog.locator('affine-paragraph').filter({ hasText: richText }).first();
      observed.setWp5Step('rich_page_title_boundary');
      await firstBodyBlock.click(); await page.keyboard.press('Home');
      observed.setWp5Step('rich_page_title_boundary_before_backspace');
      await expect.poll(() => firstBodyBlock.locator('rich-text').evaluate(node => {
        const inlineEditor = (node as HTMLElement & { inlineEditor?: { getInlineRange: () => { index: number; length: number } | null } }).inlineEditor;
        return inlineEditor?.getInlineRange()?.index ?? null;
      })).toBe(0);
      await page.keyboard.press('Backspace');
      observed.setWp5Step('rich_page_title_boundary_after_backspace');
      let firstParagraphBackspace: { title: string; firstBody: { id: string; text: string; type: string } | null; titleId?: string } | null = null;
      const readFirstParagraphBackspace = () => page.evaluate((targetText) => {
        const host = document.querySelector('.blocksuite-resource-host') as (HTMLDivElement & { __sbBlockSuiteStore?: any }) | null;
        if (!host) return { status: 'host_missing' as const, title: '', firstBody: null, titleId: undefined };
        const store = host.__sbBlockSuiteStore;
        if (!store || typeof store.getBlocksByFlavour !== 'function') {
          return { status: 'store_missing' as const, title: '', firstBody: null, titleId: undefined };
        }
        try {
          const blocks = store.getBlocksByFlavour('affine:paragraph').map(({ model }: any) => ({
            id: model.id, text: model.props.text?.toString?.() ?? '', type: model.props.type,
          }));
          const title = blocks.find((block: any) => block.type === 'h1');
          return { status: 'ready' as const, title: title?.text ?? '',
            firstBody: blocks.find((block: any) => block.text.includes(targetText)) ?? null, titleId: title?.id };
        } catch {
          return { status: 'store_error' as const, title: '', firstBody: null, titleId: undefined };
        }
      }, richText);
      await expect.poll(async () => {
        let state: Awaited<ReturnType<typeof readFirstParagraphBackspace>>;
        try {
          state = await readFirstParagraphBackspace();
        } catch {
          observed.setWp5Step('rich_page_title_boundary_state_wait_read_error');
          return { titleMatches: false, bodyMatches: false, blocksDistinct: false };
        }
        if (state.status === 'host_missing') {
          observed.setWp5Step('rich_page_title_boundary_state_wait_host_missing');
          return { titleMatches: false, bodyMatches: false, blocksDistinct: false };
        }
        if (state.status === 'store_missing') {
          observed.setWp5Step('rich_page_title_boundary_state_wait_store_missing');
          return { titleMatches: false, bodyMatches: false, blocksDistinct: false };
        }
        if (state.status === 'store_error') {
          observed.setWp5Step('rich_page_title_boundary_state_wait_store_error');
          return { titleMatches: false, bodyMatches: false, blocksDistinct: false };
        }
        const status = { titleMatches: state.title === '新建笔记', bodyMatches: state.firstBody?.text === richText,
          blocksDistinct: Boolean(state.firstBody?.id && state.titleId && state.firstBody.id !== state.titleId) };
        if (status.titleMatches && status.bodyMatches && status.blocksDistinct) firstParagraphBackspace = state;
        observed.setWp5Step(!status.titleMatches ? 'rich_page_title_boundary_state_wait_title_mismatch'
          : !status.bodyMatches ? 'rich_page_title_boundary_state_wait_body_mismatch'
            : !status.blocksDistinct ? 'rich_page_title_boundary_state_wait_block_mismatch' : 'rich_page_title_boundary_state_wait_match');
        return status;
      }, { timeout: 5000 }).toEqual({ titleMatches: true, bodyMatches: true, blocksDistinct: true });
      if (!firstParagraphBackspace) throw new Error('Expected verified Yjs title boundary state');
      observed.setWp5Step('rich_page_title_boundary_state_read');
      observed.setWp5Step('rich_page_title_boundary_title');
      expect(firstParagraphBackspace.title, 'wp5_rich_page_backspace_title_boundary').toBe('新建笔记');
      observed.setWp5Step('rich_page_title_boundary_body');
      expect(firstParagraphBackspace.firstBody?.text, 'wp5_rich_page_backspace_keeps_first_paragraph').toBe(richText);
      observed.setWp5Step('rich_page_title_boundary_block');
      expect(firstParagraphBackspace.firstBody?.id, 'wp5_rich_page_backspace_keeps_first_paragraph_id').not.toBe(firstParagraphBackspace.titleId);
      const readyMetrics = await page.evaluate(() => (window as Window & { __wp5ReadyEvents?: Array<{ durationMs: number; viewport: string }> }).__wp5ReadyEvents ?? []);
      observed.setWp5Step('rich_page_ready_measurement');
      expect(readyMetrics.length).toBeGreaterThan(0);
      expect(readyMetrics.at(-1)?.viewport).toBe('1440x1000');
      const firstRichResourceSave = page.waitForResponse(response => response.request().method() === 'PUT'
        && new URL(response.url()).pathname === `/api/notes/drafts/${richCreated.path}/blocksuite/resources/${richResourceInfo.resource_id}`, { timeout: 20000 });
      const firstRichMarkdownSave = page.waitForResponse(response => response.request().method() === 'PUT'
        && new URL(response.url()).pathname === `/api/notes/drafts/${richCreated.path}`, { timeout: 20000 });
      observed.setWp5Step('rich_page_first_save');
      await richDialog.getByRole('button', { name: '保存笔记', exact: true }).click();
      expect((await firstRichResourceSave).status(), 'wp5_rich_page_first_native_save').toBe(200);
      expect((await firstRichMarkdownSave).status(), 'wp5_rich_page_first_projection_save').toBe(200);
      await expect(richDialog.getByRole('status').first()).toContainText('已保存', { timeout: 15000 });
      observed.setWp5Step('rich_page_first_readback');
      const firstMarkdownRead = await page.request.get(`${baseUrl}/api/notes/drafts/${richCreated.path}`);
      expect(firstMarkdownRead.status(), 'wp5_rich_page_first_markdown_readback').toBe(200);
      expect((await firstMarkdownRead.json() as { content: string }).content, 'wp5_rich_page_first_projection_content').toContain(richText);
      expect((await firstMarkdownRead.json() as { content: string }).content, 'wp5_rich_page_placeholder_not_persisted').not.toContain('在这里开始编辑');
      expect((await firstMarkdownRead.json() as { content: string }).content, 'wp5_rich_page_neutral_reference_label').toContain('[笔记数据]');
      const firstNativeRead = await page.request.get(`${baseUrl}/api/notes/drafts/${richCreated.path}/blocksuite/resources/${richResourceInfo.resource_id}`);
      expect(firstNativeRead.status(), 'wp5_rich_page_first_native_readback').toBe(200);
      expect(JSON.stringify((await firstNativeRead.json() as { snapshot: unknown }).snapshot), 'wp5_rich_page_first_native_content').toContain(richText);
      observed.setWp5Step('rich_page_close');
      await richDialog.getByRole('button', { name: '返回笔记列表' }).click();
      await expect(richDialog).toHaveCount(0, { timeout: 15000 });
      observed.setWp5Step('rich_page_reopen');
      await page.locator('.notes-sidebar li button').filter({ hasText: '新建笔记' }).last().click();
      await expect(richDialog).toBeVisible({ timeout: 20000 });
      await expect(richDialog.locator('.blocksuite-resource-host .affine-page-viewport')).toBeVisible({ timeout: 15000 });
      const reopenedRichParagraphs = await richDialog.locator('.blocksuite-resource-host').evaluate(host => {
        const store = (host as HTMLDivElement & { __sbBlockSuiteStore?: { getBlocksByFlavour: (flavour: string) => Array<{ model: { props: { text?: { toString: () => string } } } }> } }).__sbBlockSuiteStore;
        return store?.getBlocksByFlavour('affine:paragraph').map(({ model }) => model.props.text?.toString() ?? '') ?? [];
      });
      expect(reopenedRichParagraphs.join('\n'), 'wp5_rich_page_close_reopen_content').toContain(richText);
      expect(reopenedRichParagraphs.join('\n'), 'wp5_rich_page_enter_persisted').toContain(secondRichLine);
      const discardedMarker = `Discard guard ${randomUUID()}`;
      const reopenedBody = richDialog.locator('affine-paragraph').filter({ hasText: secondRichLine }).last();
      await reopenedBody.click(); await page.keyboard.press('End'); await page.keyboard.insertText(` ${discardedMarker}`);
      await richDialog.getByRole('button', { name: '返回笔记列表' }).click();
      const exitPrompt = page.getByRole('alertdialog', { name: '未保存修改' });
      await expect(exitPrompt).toBeVisible();
      await exitPrompt.getByRole('button', { name: '取消' }).click();
      await expect(richDialog.getByText(discardedMarker)).toBeVisible();
      await richDialog.getByRole('button', { name: '返回笔记列表' }).click();
      await exitPrompt.getByRole('button', { name: '放弃本次修改' }).click();
      await expect(richDialog).toHaveCount(0);
      await page.locator('.notes-sidebar li button').filter({ hasText: '新建笔记' }).last().click();
      await expect(richDialog.getByText(secondRichLine, { exact: false })).toBeVisible();
      await expect(richDialog.getByText(discardedMarker, { exact: false })).toHaveCount(0);
      const desktopSize = page.viewportSize();
      await page.setViewportSize({ width: 390, height: 844 });
      const mobileLayout = await page.locator('.notes-layout').evaluate(layout => {
        const rect = layout.getBoundingClientRect();
        const controls = [...layout.querySelectorAll<HTMLElement>('.document-controls button, .blocksuite-resource-toolbar button, .document-back-action')]
          .map(control => { const box = control.getBoundingClientRect(); return { left: box.left, right: box.right, top: box.top, bottom: box.bottom, visible: box.width > 0 && box.height > 0 }; });
        return { viewportWidth: window.innerWidth, scrollWidth: document.documentElement.scrollWidth,
          layoutLeft: rect.left, layoutRight: rect.right, controls };
      });
      expect(mobileLayout.scrollWidth, 'wp5_notes_mobile_no_horizontal_overflow').toBeLessThanOrEqual(mobileLayout.viewportWidth);
      expect(mobileLayout.controls.every(control => control.visible && control.left >= 0 && control.right <= mobileLayout.viewportWidth),
        'wp5_notes_mobile_controls_inside_viewport').toBe(true);
      await page.setViewportSize(desktopSize ?? { width: 1440, height: 1000 });
      await page.reload();
      await expect(richDialog).toBeVisible({ timeout: 30000 });
      await expect(richDialog).toHaveAttribute('aria-busy', 'false', { timeout: 30000 });
      const warmReadyMetrics = await page.evaluate(() => (window as Window & { __wp5ReadyEvents?: Array<{ durationMs: number; viewport: string }> }).__wp5ReadyEvents ?? []);
      expect(warmReadyMetrics.length, 'wp5_notes_warm_open_measurement_present').toBeGreaterThan(0);
      console.log(`WP5_NOTES_OPEN_TIMINGS ${JSON.stringify({ firstOpen: readyMetrics.at(-1), warmOpen: warmReadyMetrics.at(-1) })}`);
      await expect(richDialog.getByText(richText, { exact: false })).toBeVisible();
      if (process.env.SB_E2E_WP5_OPEN_ONLY === 'true') return;

      // Keep archive-only UI checks independent from the separate resource
      // lifecycle and Page/Edgeless mode journeys. The synthetic Rich Page is
      // already saved and reopened above, so the controls can be exercised
      // without paying for a nested canvas/blob round trip first.
      let nestedCanvasResourceId: string | null = null;
      if (!wp5ArchiveUxOnly) {
      await richDialog.locator('.blocksuite-canvas-tools > summary').click();
      const canvasGallery = richDialog.getByRole('region', { name: '独立画布资源' });
      observed.setWp5Step('rich_page_nested_canvas_create');
      const nestedCanvasCreate = page.waitForResponse(response => response.request().method() === 'POST'
        && new URL(response.url()).pathname === `/api/notes/drafts/${richCreated.path}/blocksuite/resources`, { timeout: 20000 });
      await canvasGallery.getByRole('button', { name: '新建独立画布' }).click();
      const nestedCanvasResponse = await nestedCanvasCreate;
      expect(nestedCanvasResponse.status(), 'wp5_rich_page_nested_canvas_create').toBe(200);
      const nestedCanvasInfo = await nestedCanvasResponse.json() as { resource_id: string };
      nestedCanvasResourceId = nestedCanvasInfo.resource_id;
      const nestedCanvasCard = canvasGallery.locator('.canvas-b-card').filter({ hasText: nestedCanvasInfo.resource_id });
      await expect(nestedCanvasCard).toBeVisible({ timeout: 15000 });
      observed.setWp5Step('rich_page_nested_canvas_open');
      const nestedCanvasOpenButton = nestedCanvasCard.getByRole('button', { name: '打开编辑' });
      await nestedCanvasOpenButton.scrollIntoViewIfNeeded();
      await expect(nestedCanvasOpenButton).toBeVisible();
      const nestedCanvasOpenBox = await nestedCanvasOpenButton.boundingBox();
      expect(nestedCanvasOpenBox, 'wp5_nested_canvas_open_button_geometry').not.toBeNull();
      observed.setWp5Step('rich_page_nested_canvas_button_visible');
      const nestedCanvasButtonReceivesPointer = await nestedCanvasOpenButton.evaluate(button => {
        const rect = button.getBoundingClientRect();
        const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
        return hit === button || (hit instanceof Node && button.contains(hit));
      });
      observed.setWp5Step('rich_page_nested_canvas_pointer_hit');
      expect(nestedCanvasButtonReceivesPointer, 'wp5_nested_canvas_open_button_hit_test').toBe(true);
      observed.setWp5Step('rich_page_nested_canvas_pointer_dispatch');
      await page.mouse.click(nestedCanvasOpenBox!.x + nestedCanvasOpenBox!.width / 2,
        nestedCanvasOpenBox!.y + nestedCanvasOpenBox!.height / 2);
      observed.setWp5Step('rich_page_nested_canvas_resource_read');
      const nestedCanvasDialog = page.getByRole('dialog', { name: 'BlockSuite Edgeless 资源' });
      await expect(nestedCanvasDialog).toBeVisible({ timeout: 15000 });
      observed.setWp5Step('rich_page_nested_canvas_dialog_ready');
      const nestedImageDataUrl = await page.evaluate(() => {
        const canvas = document.createElement('canvas'); canvas.width = 2; canvas.height = 2;
        const context = canvas.getContext('2d'); if (!context) throw new Error('Canvas 2D context unavailable');
        context.fillStyle = '#2f80ed'; context.fillRect(0, 0, 2, 2); return canvas.toDataURL('image/png');
      });
      const nestedBlobPut = page.waitForResponse(response => response.request().method() === 'PUT'
        && new URL(response.url()).pathname.includes(`/api/notes/drafts/${richCreated.path}/blocksuite/blobs/`), { timeout: 20000 });
      observed.setWp5Step('rich_page_nested_blob_upload');
      await nestedCanvasDialog.getByLabel('选择 Edgeless 图片').setInputFiles({ name: 'nested-canvas.png', mimeType: 'image/png',
        buffer: Buffer.from(nestedImageDataUrl.split(',')[1], 'base64') });
      expect((await nestedBlobPut).status(), 'wp5_rich_page_nested_canvas_blob').toBe(201);
      observed.setDiagnosticAssertion('wp5_canvas_layout_stable');
      await expectEdgelessTextLayoutSettled(nestedCanvasDialog, (samples) => observed.setWp5CanvasSaveDiagnostic({
        checkpoint: 'layout_poll', status: 'other', close_enabled: null, readback_status: null,
        snapshot_matches_readback: null, live_text_bounds: [], saved_text_bounds: [], layout_samples: samples,
      }));
      const nestedCanvasSave = page.waitForResponse(response => response.request().method() === 'PUT'
        && new URL(response.url()).pathname === `/api/notes/drafts/${richCreated.path}/blocksuite/resources/${nestedCanvasInfo.resource_id}`, { timeout: 20000 });
      observed.setWp5Step('rich_page_nested_canvas_save');
      await nestedCanvasDialog.getByRole('button', { name: '保存资源' }).click();
      expect((await nestedCanvasSave).status(), 'wp5_rich_page_nested_canvas_save').toBe(200);
      const nestedCanvasStatus = nestedCanvasDialog.getByRole('status');
      const nestedCanvasClose = nestedCanvasDialog.getByRole('button', { name: '关闭', exact: true });
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_010');
      const canvasStatusState = (value: string): CanvasSaveDiagnostic['status'] => value === 'BlockSuite 资源已保存' ? 'saved'
        : value === '先前版本已保存；有未保存的资源修改' ? 'previous_dirty'
          : value === '有未保存的资源修改' ? 'unsaved' : value === '保存中…' ? 'saving' : 'other';
      const recordCanvasSave = (diagnostic: CanvasSaveDiagnostic) => observed.setWp5CanvasSaveDiagnostic(diagnostic);
      recordCanvasSave({ checkpoint: 'first_status', status: canvasStatusState(await nestedCanvasStatus.innerText()),
        close_enabled: await nestedCanvasClose.isEnabled(), readback_status: null, snapshot_matches_readback: null,
        live_text_bounds: [], saved_text_bounds: [], layout_samples: [] });
      await expect(nestedCanvasStatus).toHaveText(/^(BlockSuite 资源已保存|先前版本已保存；有未保存的资源修改)$/);
      if (await nestedCanvasStatus.innerText() !== 'BlockSuite 资源已保存') {
        const nestedCanvasResave = page.waitForResponse(response => response.request().method() === 'PUT'
          && new URL(response.url()).pathname === `/api/notes/drafts/${richCreated.path}/blocksuite/resources/${nestedCanvasInfo.resource_id}`, { timeout: 20000 });
        await nestedCanvasDialog.getByRole('button', { name: '保存资源' }).click();
        expect((await nestedCanvasResave).status(), 'wp5_rich_page_nested_canvas_resave').toBe(200);
        recordCanvasSave({ checkpoint: 'second_save_response', status: canvasStatusState(await nestedCanvasStatus.innerText()),
          close_enabled: await nestedCanvasClose.isEnabled(), readback_status: null, snapshot_matches_readback: null,
          live_text_bounds: [], saved_text_bounds: [], layout_samples: [] });
        const nestedCanvasReadback = await page.request.get(`${baseUrl}/api/notes/drafts/${richCreated.path}/blocksuite/resources/${nestedCanvasInfo.resource_id}`);
        const nestedCanvasPersisted = nestedCanvasReadback.ok()
          ? await nestedCanvasReadback.json() as { snapshot?: Record<string, unknown> } : null;
        const nestedCanvasLive = await nestedCanvasDialog.locator('.blocksuite-resource-host').evaluate((element) => {
          const store = (element as HTMLDivElement & { __sbBlockSuiteStore?: any }).__sbBlockSuiteStore;
          if (!store) return null;
          const snapshot = store.getTransformer().docToSnapshot(store) as Record<string, unknown>;
          const textBounds: number[][] = [];
          const visit = (value: unknown) => {
            if (!value || typeof value !== 'object') return;
            const record = value as Record<string, unknown>;
            const props = record.props && typeof record.props === 'object' ? record.props as Record<string, unknown> : null;
            if (record.flavour === 'affine:edgeless-text' && typeof props?.xywh === 'string') {
              try {
                const bounds = JSON.parse(props.xywh);
                if (Array.isArray(bounds) && bounds.length === 4 && bounds.every(Number.isFinite)) textBounds.push(bounds as number[]);
              } catch { /* bounded diagnostic omits invalid geometry */ }
            }
            for (const child of Object.values(record)) {
              if (Array.isArray(child)) child.forEach(visit);
              else if (child && typeof child === 'object') visit(child);
            }
          };
          visit(snapshot);
          return { snapshot, textBounds };
        });
        const readEdgelessTextBounds = (value: unknown): number[][] => {
          const bounds: number[][] = [];
          const visit = (item: unknown) => {
            if (!item || typeof item !== 'object') return;
            const record = item as Record<string, unknown>;
            const props = record.props && typeof record.props === 'object' ? record.props as Record<string, unknown> : null;
            if (record.flavour === 'affine:edgeless-text' && typeof props?.xywh === 'string') {
              try {
                const value = JSON.parse(props.xywh);
                if (Array.isArray(value) && value.length === 4 && value.every(Number.isFinite)) bounds.push(value as number[]);
              } catch { /* bounded diagnostic omits invalid geometry */ }
            }
            for (const child of Object.values(record)) {
              if (Array.isArray(child)) child.forEach(visit);
              else if (child && typeof child === 'object') visit(child);
            }
          };
          visit(value);
          return bounds;
        };
        const canonicalJson = (value: unknown): string => {
          if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
          if (!value || typeof value !== 'object') return JSON.stringify(value) ?? 'undefined';
          return `{${Object.entries(value as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b))
            .map(([key, child]) => `${JSON.stringify(key)}:${canonicalJson(child)}`).join(',')}}`;
        };
        recordCanvasSave({ checkpoint: 'readback', status: canvasStatusState(await nestedCanvasStatus.innerText()),
          close_enabled: await nestedCanvasClose.isEnabled(), readback_status: nestedCanvasReadback.status(),
          snapshot_matches_readback: null, live_text_bounds: [], saved_text_bounds: [], layout_samples: [] });
        const readbackMatchesLive = !!nestedCanvasLive && !!nestedCanvasPersisted
          && canonicalJson(nestedCanvasLive.snapshot) === canonicalJson(nestedCanvasPersisted.snapshot);
        const liveTextBounds = nestedCanvasLive?.textBounds ?? [];
        const savedTextBounds = nestedCanvasPersisted ? readEdgelessTextBounds(nestedCanvasPersisted.snapshot) : [];
        recordCanvasSave({ checkpoint: 'saved_status', status: canvasStatusState(await nestedCanvasStatus.innerText()),
          close_enabled: await nestedCanvasClose.isEnabled(), readback_status: nestedCanvasReadback.status(),
          snapshot_matches_readback: readbackMatchesLive, live_text_bounds: liveTextBounds,
          saved_text_bounds: savedTextBounds, layout_samples: [] });
        await expect(nestedCanvasStatus).toHaveText('BlockSuite 资源已保存');
      }
      recordCanvasSave({ checkpoint: 'close_enabled', status: canvasStatusState(await nestedCanvasStatus.innerText()),
        close_enabled: await nestedCanvasClose.isEnabled(), readback_status: null, snapshot_matches_readback: null,
        live_text_bounds: [], saved_text_bounds: [], layout_samples: [] });
      await expect(nestedCanvasClose).toBeEnabled();
      await nestedCanvasClose.click();
      await expect(nestedCanvasCard.getByText(/自动裁剪预览 · 1 个对象/)).toBeVisible({ timeout: 15000 });
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_010');
      await expect(richDialog.getByRole('button', { name: '保存笔记', exact: true })).toBeEnabled();
      const richResourceSave = page.waitForResponse(response => response.request().method() === 'PUT'
        && new URL(response.url()).pathname === `/api/notes/drafts/${richCreated.path}/blocksuite/resources/${richResourceInfo.resource_id}`, { timeout: 20000 });
      const richMarkdownSave = page.waitForResponse(response => response.request().method() === 'PUT'
        && new URL(response.url()).pathname === `/api/notes/drafts/${richCreated.path}`, { timeout: 20000 });
      observed.setWp5Step('rich_page_parent_save');
      await richDialog.getByRole('button', { name: '保存笔记', exact: true }).click();
      expect((await richResourceSave).status(), 'wp5_rich_page_native_save').toBe(200);
      expect((await richMarkdownSave).status(), 'wp5_rich_page_projection_save').toBe(200);
      await expect(richDialog.getByRole('status').first()).toContainText('已保存', { timeout: 15000 });
      const richNoteRead = await page.request.get(`${baseUrl}/api/notes/drafts/${richCreated.path}`);
      expect(richNoteRead.status(), 'wp5_rich_page_markdown_readback').toBe(200);
      const richNote = await richNoteRead.json() as { content: string; etag: string };
      expect(richNote.content, 'wp5_rich_page_readable_projection').toContain(richText);
      const richResourceRead = await page.request.get(`${baseUrl}/api/notes/drafts/${richCreated.path}/blocksuite/resources/${richResourceInfo.resource_id}`);
      expect(richResourceRead.status(), 'wp5_rich_page_native_readback').toBe(200);
      const richResource = await richResourceRead.json() as { updateB64: string; snapshot: Record<string, unknown>; note_etag: string };
      expect(richResource.updateB64.length, 'wp5_rich_page_yjs_persisted').toBeGreaterThan(4);
      expect(JSON.stringify(richResource.snapshot), 'wp5_rich_page_native_text').toContain(richText);
      expect(richResource.note_etag, 'wp5_rich_page_receipt_bound').toBe(richNote.etag);
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_013');

      // Page/Edgeless mode changes save first, then remount from the exact Yjs
      // update. Switching back proves the text survives both view lifecycles.
      observed.setWp5Step('rich_page_mode_edgeless');
      await richDialog.getByText('属性', { exact: true }).click();
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_069');
      await richDialog.getByRole('group', { name: '文档模式' }).getByRole('button', { name: '画布', exact: true }).click();
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_070');
      await expect(richDialog.locator('.affine-edgeless-viewport')).toBeVisible({ timeout: 20000 });
      observed.setWp5Step('rich_page_mode_edgeless_ready');
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_071');
      observed.setWp5Step('rich_page_mode_page');
      const propertiesPanel = richDialog.locator('details.sb-properties-info');
      if (!await propertiesPanel.evaluate(details => (details as HTMLDetailsElement).open)) {
        await propertiesPanel.locator('summary').click();
      }
      const modeGroup = richDialog.getByRole('group', { name: '文档模式' });
      await expect(modeGroup).toBeVisible();
      const pageModeButton = modeGroup.locator('button').filter({ hasText: /^页面$/ });
      await expect(pageModeButton).toHaveCount(1);
      await expect(pageModeButton).toBeVisible();
      await expect(pageModeButton).toBeEnabled();
      await expect(pageModeButton).toHaveAttribute('aria-pressed', 'false');
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_075');
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_066');
      await pageModeButton.click({ timeout: 5000 });
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_067');
      await expect(richDialog.locator('.affine-page-viewport')).toBeVisible({ timeout: 20000 });
      await expect(richDialog).toHaveAttribute('aria-busy', 'false', { timeout: 20000 });
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_068');
      await expect(richDialog.getByText(richText, { exact: false })).toBeVisible({ timeout: 15000 });
      observed.setDiagnosticAssertion('wp5_resource_checkpoint_018');
      if (wp5RichPageModeOnly) return;
      }
      if (wp5ArchiveUxOnly) {
        observed.setFailureStage('notes_blocksuite_open');
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_019');
        const richHost = richDialog.locator('.blocksuite-resource-host.sb-archive-surface');
        const archiveViewport = richHost.locator('.sb-archive-viewport');
        await expect(archiveViewport).toBeVisible();
        await expect(archiveViewport).toHaveClass(/affine-page-viewport/);
        observed.setWp5Step('archive_ux_style_check');
        const archivedPageStyle = await richHost.evaluate(host => {
          const style = getComputedStyle(host);
          return { fontFamily: style.fontFamily, fontSize: style.fontSize, lineHeight: style.lineHeight };
        });
        expect(archivedPageStyle.fontFamily, 'wp5_archive_page_font_family').toMatch(/Inter|ui-sans-serif|system-ui/i);
        expect(archivedPageStyle.fontSize, 'wp5_archive_page_font_size').toBe('15px');
        expect(Number.parseFloat(archivedPageStyle.lineHeight), 'wp5_archive_page_line_height').toBeCloseTo(24.75, 1);
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_020');
        // Keep the paragraph locator rooted at the active Rich Page host;
        // its content is rendered through BlockSuite's nested Shadow DOM.
        const bodyParagraph = richHost.locator('affine-paragraph').filter({ hasText: richText });
        await expect(bodyParagraph).toHaveCount(1);
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_021');
        await expect(bodyParagraph).toBeVisible();
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_022');
        const readBlockOrder = () => archiveViewport.evaluate(root => {
          const host = root.closest('.blocksuite-resource-host') as (HTMLElement & { __sbBlockSuiteStore?: any }) | null;
          const store = host?.__sbBlockSuiteStore;
          return (store?.getBlocksByFlavour('affine:paragraph') ?? []).map(({ model }: any) => {
            const parent = store.getParent(model);
            return { id: model.id, text: model.props.text?.toString?.() ?? '', type: model.props.type,
              textAlign: model.props.textAlign ?? null, textDelta: model.props.text?.toDelta?.() ?? [],
              parent: parent?.id ?? null, order: parent?.children?.findIndex((child: any) => child.id === model.id) ?? -1,
              childMapOrder: parent?.childMap?.value?.get(model.id) ?? -1 };
          });
        });
        const originalBlockId = await bodyParagraph.getAttribute('data-block-id');
        expect(originalBlockId, 'wp5_archive_fixture_original_block').toBeTruthy();
        const inlineEditor = bodyParagraph.locator('rich-text .inline-editor');
        await expect(inlineEditor, 'wp5_archive_fixture_inline_editor').toHaveAttribute('contenteditable', 'true');
        const orderBeforeSplit = await readBlockOrder();
        await inlineEditor.click();
        observed.setDiagnosticAssertion('wp5_archive_fixture_click_complete');
        // BlockSuite keeps the page root as document.activeElement while the
        // caret lives in the contenteditable's Yjs-backed inline selection.
        await expect.poll(() => inlineEditor.evaluate(editor => {
          const selection = window.getSelection();
          return Boolean(selection?.anchorNode && editor.contains(selection.anchorNode));
        }), { timeout: 5000, message: 'wp5_archive_fixture_caret_in_editor' }).toBe(true);
        observed.setDiagnosticAssertion('wp5_archive_fixture_caret_ready');
        await page.keyboard.press('End');
        await page.keyboard.press('Enter');
        observed.setDiagnosticAssertion('wp5_archive_fixture_split');
        await expect.poll(async () => {
          const previousIds = new Set(orderBeforeSplit.map(block => block.id));
          return (await readBlockOrder()).some(block => !previousIds.has(block.id)
            && block.parent === orderBeforeSplit.find(item => item.id === originalBlockId)?.parent
            && block.text.trim().length === 0);
        }, { timeout: 5000, message: 'wp5_archive_fixture_new_empty_block' }).toBe(true);
        await page.keyboard.insertText('Archive reorder target');
        const targetParagraph = richHost.locator('affine-paragraph').filter({ hasText: 'Archive reorder target' });
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_023');
        await expect(targetParagraph).toHaveCount(1);
        await expect(targetParagraph).toBeVisible();
        await expect.poll(async () => (await readBlockOrder()).find(block => block.text.includes('Archive reorder target'))?.id)
          .not.toBe(originalBlockId);

        const plus = richDialog.locator('sb-desktop-page-plus-widget button[data-kind="plus"]');
        const grip = richDialog.locator('sb-desktop-page-plus-widget button[data-kind="grip"]');
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_024');
        await targetParagraph.hover();
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_025');
        await expect(plus).toHaveAttribute('data-visible', 'true');
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_026');
        await expect(grip).toHaveAttribute('data-visible', 'true');
        if (process.env.SB_WP5_NATIVE_SCREENSHOT_PATH) {
          await page.locator('.notes-layout').screenshot({ path: process.env.SB_WP5_NATIVE_SCREENSHOT_PATH });
        }
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_027');
        const controlGeometry = await Promise.all([grip, plus].map(locator => locator.evaluate(button => {
          const rect = button.getBoundingClientRect();
          return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
        })));
        expect(Math.abs((controlGeometry[0].y + controlGeometry[0].height / 2)
          - (controlGeometry[1].y + controlGeometry[1].height / 2)), 'wp5_desktop_page_plus_center_alignment').toBeLessThan(2);
        expect(Math.abs(controlGeometry[0].x - controlGeometry[1].x), 'wp5_desktop_page_plus_direction_gap').toBeGreaterThanOrEqual(22);
        expect(Math.abs(controlGeometry[0].x - controlGeometry[1].x), 'wp5_desktop_page_plus_direction_gap').toBeLessThanOrEqual(26);
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_028');
        await plus.click();
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_029');
        const headingMenuItem = page.getByTestId('一级标题');
        await expect(headingMenuItem).toHaveCount(1);
        await expect(headingMenuItem).toBeVisible();
        await headingMenuItem.click({ timeout: 5000 });
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_030');
        await expect.poll(async () => (await readBlockOrder()).find(block => block.text.includes('Archive reorder target'))?.type)
          .toBe('h1');
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_031');
        const headingTextStyle = await targetParagraph.locator('.affine-paragraph-rich-text-wrapper').evaluate(element => {
          const style = getComputedStyle(element);
          return { fontFamily: style.fontFamily, fontSize: style.fontSize, fontWeight: style.fontWeight, lineHeight: style.lineHeight };
        });
        expect(headingTextStyle.fontFamily, 'wp5_archive_heading_font_family').toMatch(/Inter|ui-sans-serif|system-ui/i);
        expect(Number.parseFloat(headingTextStyle.fontSize), 'wp5_archive_heading_font_size').toBeGreaterThan(15);
        expect(headingTextStyle.fontWeight, 'wp5_archive_heading_weight').toBe('700');
        expect(headingTextStyle.lineHeight, 'wp5_archive_heading_line_height').toMatch(/^\d+(?:\.\d+)?px$/);

        // Exercise the archived inline and paragraph toolbars with a real
        // keyboard selection, then verify the Yjs-backed block model changed.
        observed.setWp5Step('archive_ux_toolbar_select');
        await targetParagraph.click();
        await page.keyboard.press('End');
        await page.keyboard.press('Shift+Home');
        const boldAction = richDialog.getByRole('button', { name: '加粗', exact: true });
        await expect(boldAction, 'wp5_archive_inline_toolbar_localized').toBeVisible({ timeout: 5000 });
        observed.setWp5Step('archive_ux_bold');
        await boldAction.click();
        await expect.poll(async () => {
          const block = (await readBlockOrder()).find(item => item.text.includes('Archive reorder target'));
          return block?.textDelta.some((part: any) => part.attributes?.bold === true) ?? false;
        }, { timeout: 5000 }).toBe(true);

        observed.setWp5Step('archive_ux_alignment');
        await targetParagraph.click();
        await page.keyboard.press('End');
        await page.keyboard.press('Shift+Home');
        const centerAction = richDialog.getByRole('button', { name: '居中对齐', exact: true });
        await expect(centerAction, 'wp5_archive_alignment_toolbar_localized').toBeVisible({ timeout: 5000 });
        const alignmentTargetId = await targetParagraph.getAttribute('data-block-id');
        expect(alignmentTargetId, 'wp5_archive_alignment_target_present').toBeTruthy();
        await expect.poll(async () => archiveViewport.evaluate((root, targetId) => {
          const host = root.closest('.blocksuite-resource-host') as (HTMLElement & { __sbBlockSuiteStd?: any }) | null;
          const std = host?.__sbBlockSuiteStd;
          const selection = std?.selection?.value?.find((item: any) => item.type === 'text');
          const textSelectionCtor = selection ? {
            fromTarget: Boolean(targetId && selection.from?.blockId === targetId),
            nonempty: Number.isInteger(selection.from?.length) && selection.from.length > 0,
            toTarget: !selection.to || selection.to.blockId === targetId,
          } : null;
          if (!selection) return 'wp5_archive_align_no_selection';
          if (!textSelectionCtor?.fromTarget) return 'wp5_archive_align_wrong_target';
          if (!textSelectionCtor.nonempty) return 'wp5_archive_align_empty_selection';
          if (!textSelectionCtor.toTarget) return 'wp5_archive_align_cross_block';
          const modelRange = std?.range?.textSelectionToRange(selection);
          if (!modelRange) return 'wp5_archive_align_model_range_missing';
          const nativeSelection = window.getSelection();
          if (!nativeSelection || nativeSelection.isCollapsed || nativeSelection.rangeCount === 0) return 'wp5_archive_align_native_range_missing';
          const nativeRange = nativeSelection.getRangeAt(0);
          const reverse = Boolean(nativeSelection.anchorNode && nativeSelection.focusNode
            && (nativeSelection.anchorNode === nativeSelection.focusNode
              ? nativeSelection.anchorOffset > nativeSelection.focusOffset
              : Boolean(nativeSelection.anchorNode.compareDocumentPosition(nativeSelection.focusNode)
                & Node.DOCUMENT_POSITION_PRECEDING)));
          const nativeTextSelection = std.range.rangeToTextSelection(nativeRange, reverse);
          if (!nativeTextSelection) return 'wp5_archive_align_native_conversion_missing';
          const samePoint = (left: any, right: any) => left?.blockId === right?.blockId
            && left?.index === right?.index && left?.length === right?.length;
          const logicalMatch = samePoint(selection.from, nativeTextSelection.from)
            && (selection.to === null ? nativeTextSelection.to === null : samePoint(selection.to, nativeTextSelection.to));
          return logicalMatch ? 'ready' : 'wp5_archive_align_logical_selection_mismatch';
        }, alignmentTargetId).then(status => {
          const failureAssertion = status === 'ready' ? 'wp5_archive_alignment_selection_ready' : status;
          observed.setDiagnosticAssertion(failureAssertion as DiagnosticAssertion);
          return status;
        }), { timeout: 5000, message: 'wp5_archive_text_selection_ready' }).toBe('ready');
        observed.setDiagnosticAssertion('wp5_archive_align_action_click');
        await centerAction.click();
        observed.setDiagnosticAssertion('wp5_archive_align_model_center');
        await expect.poll(async () => (await readBlockOrder()).find(block => block.text.includes('Archive reorder target'))?.textAlign)
          .toBe('center');

        observed.setDiagnosticAssertion('wp5_archive_grip_visibility');
        await targetParagraph.hover();
        await expect(grip).toHaveAttribute('data-visible', 'true');
        const gripBox = await grip.boundingBox();
        const bodyBox = await bodyParagraph.boundingBox();
        observed.setDiagnosticAssertion('wp5_archive_drag_geometry');
        expect(gripBox, 'wp5_desktop_page_plus_grip_geometry').not.toBeNull();
        expect(bodyBox, 'wp5_desktop_page_plus_drop_geometry').not.toBeNull();
        const orderBeforeDrag = await readBlockOrder();
        const dragPreflight = (() => {
          const sources = orderBeforeDrag.filter(block => block.text.includes('Archive reorder target'));
          const targets = orderBeforeDrag.filter(block => block.text.includes(richText));
          if (sources.length !== 1) return 'wp5_archive_drag_source_not_unique';
          if (targets.length !== 1) return 'wp5_archive_drag_target_not_unique';
          const source = sources[0]!;
          const target = targets[0]!;
          if (source.id === target.id) return 'wp5_archive_drag_same_block';
          if (!source.parent || !target.parent) return 'wp5_archive_drag_parent_missing';
          if (source.parent !== target.parent) return 'wp5_archive_drag_different_parents';
          if (source.order < 0) return 'wp5_archive_drag_source_missing_from_parent';
          if (target.order < 0) return 'wp5_archive_drag_target_missing_from_parent';
          if (source.order !== source.childMapOrder || target.order !== target.childMapOrder) return 'wp5_archive_drag_child_index_mismatch';
          return source.order > target.order ? 'wp5_archive_drag_source_after' : 'wp5_archive_drag_source_before';
        })();
        observed.setDiagnosticAssertion(dragPreflight as DiagnosticAssertion);
        expect(['wp5_archive_drag_source_after', 'wp5_archive_drag_source_before'], 'wp5_archive_drag_preflight').toContain(dragPreflight);
        const expectedSourceBeforeTarget = dragPreflight === 'wp5_archive_drag_source_after';
        const beforeDrag = orderBeforeDrag.find(block => block.text.includes('Archive reorder target'))!;
        const beforeDragTarget = orderBeforeDrag.find(block => block.text.includes(richText))!;
        const bodyDomBlockId = await bodyParagraph.getAttribute('data-block-id');
        observed.setDiagnosticAssertion('wp5_archive_drag_target_locator_match');
        expect(bodyDomBlockId, 'wp5_archive_drag_target_locator_match').toBe(beforeDragTarget.id);
        const dragWidget = richDialog.locator('sb-desktop-page-plus-widget');
        const anchorId = await dragWidget.evaluate(widget => (widget as HTMLElement & { anchor?: { id?: string } | null }).anchor?.id ?? null);
        observed.setDiagnosticAssertion('wp5_archive_drag_anchor_match');
        expect(anchorId, 'wp5_archive_drag_anchor_match').toBe(beforeDrag.id);
        await page.mouse.move(gripBox!.x + gripBox!.width / 2, gripBox!.y + gripBox!.height / 2);
        await page.mouse.down();
        const dropY = dragPreflight === 'wp5_archive_drag_source_after'
          ? bodyBox!.y + 1 : bodyBox!.y + bodyBox!.height - 1;
        await page.mouse.move(bodyBox!.x + bodyBox!.width / 3, dropY, { steps: 5 });
        const expectedDropBefore = dropY < bodyBox!.y + bodyBox!.height / 2;
        const dragRouting = await richDialog.evaluate((root, point) => {
          const widget = root.querySelector('sb-desktop-page-plus-widget') as (HTMLElement & {
            dragSource?: { id?: string } | null; dropTarget?: { id?: string; before?: boolean } | null;
          }) | null;
          const hit = document.elementFromPoint(point.x, point.y)?.closest('[data-block-id]') as HTMLElement | null;
          const gripButton = widget?.shadowRoot?.querySelector('button[data-kind="grip"]') as HTMLButtonElement | null;
          const hitId = hit?.getAttribute('data-block-id') ?? null;
          return { dragSourceMatches: widget?.dragSource?.id === point.sourceId,
            hitMatchesTarget: hit?.getAttribute('data-block-id') === point.targetId,
            hitIsSource: hitId === point.sourceId,
            hitHasBlock: hitId !== null,
            dropTargetMatches: widget?.dropTarget?.id === point.targetId,
            dropBefore: widget?.dropTarget?.before ?? null,
            pointerCaptured: gripButton?.hasPointerCapture(1) ?? false };
        }, { x: bodyBox!.x + bodyBox!.width / 3, y: dropY, sourceId: beforeDrag.id, targetId: beforeDragTarget.id });
        const routingAssertion: DiagnosticAssertion = !dragRouting.dragSourceMatches ? 'wp5_archive_drag_source_match'
          : !dragRouting.hitMatchesTarget ? dragRouting.hitIsSource ? 'wp5_archive_drag_hit_source'
            : dragRouting.hitHasBlock ? 'wp5_archive_drag_hit_other_block' : 'wp5_archive_drag_hit_no_block'
            : !dragRouting.dropTargetMatches ? 'wp5_archive_drag_drop_target_match'
              : dragRouting.dropBefore !== expectedDropBefore ? 'wp5_archive_drag_drop_boundary_match'
                : !dragRouting.pointerCaptured ? 'wp5_archive_drag_capture_match' : 'wp5_archive_drag_pointer_routing';
        observed.setDiagnosticAssertion(routingAssertion);
        expect(dragRouting, 'wp5_archive_drag_pointer_routing').toEqual({ dragSourceMatches: true,
          hitMatchesTarget: true, hitIsSource: false, hitHasBlock: true,
          dropTargetMatches: true, dropBefore: expectedDropBefore, pointerCaptured: true });
        await page.mouse.up();
        observed.setDiagnosticAssertion('wp5_archive_drag_result');
        await expect.poll(async () => {
          const order = await readBlockOrder();
          const source = order.find(block => block.text.includes('Archive reorder target'));
          const target = order.find(block => block.text.includes(richText));
          const sourceBeforeTarget = source && target ? source.order < target.order : null;
          return Boolean(source && target && source.parent === target.parent && sourceBeforeTarget === expectedSourceBeforeTarget);
        }).toBe(true);
        const orderAfterDrag = await readBlockOrder();
        const afterDrag = orderAfterDrag.find(block => block.text.includes('Archive reorder target'))!;
        const afterDragTarget = orderAfterDrag.find(block => block.text.includes(richText))!;
        expect(afterDrag.parent, 'wp5_desktop_page_plus_reorder_same_parent_after').toBe(afterDragTarget.parent);
        expect(afterDrag.order, 'wp5_desktop_page_plus_reorder_source_index_valid').toBeGreaterThanOrEqual(0);
        expect(afterDragTarget.order, 'wp5_desktop_page_plus_reorder_target_index_valid').toBeGreaterThanOrEqual(0);
        expect(afterDrag.order < afterDragTarget.order, 'wp5_desktop_page_plus_reorder_changed_order')
          .toBe(expectedSourceBeforeTarget);
        expect(afterDrag.order < afterDragTarget.order, 'wp5_desktop_page_plus_reorder_relationship_reversed')
          .not.toBe(beforeDrag.order < beforeDragTarget.order);
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_032');

        // Inherit the archived table path through the real Slash menu and
        // pointer selection. The store is read only to confirm that UI edits
        // reached the Yjs model before the resource is saved and reopened.
        observed.setWp5Step('archive_ux_table');
        await targetParagraph.hover();
        await expect(plus).toHaveAttribute('data-visible', 'true');
        await plus.click();
        const tableMenuItem = page.getByTestId('普通表格');
        await expect(tableMenuItem).toBeVisible();
        await tableMenuItem.click();
        const archiveTable = richHost.locator('affine-table').last();
        await expect(archiveTable).toBeVisible();
        const archiveTableCells = archiveTable.locator('td[data-row-id][data-column-id]');
        await expect.poll(() => archiveTableCells.count()).toBeGreaterThan(3);
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_035');
        const firstCell = archiveTableCells.nth(0);
        const secondCell = archiveTableCells.nth(1);
        const firstCellEditor = firstCell.locator('rich-text .inline-editor');
        const secondCellEditor = secondCell.locator('rich-text .inline-editor');
        const mergeSourceText = `WP5 merge source ${randomUUID()}`;
        const mergeCoveredText = `WP5 merge covered ${randomUUID()}`;
        const firstRowId = await firstCell.getAttribute('data-row-id');
        const firstColumnId = await firstCell.getAttribute('data-column-id');
        const secondRowId = await secondCell.getAttribute('data-row-id');
        const secondColumnId = await secondCell.getAttribute('data-column-id');
        console.log('WP5_TABLE_DOM_DIAG', JSON.stringify(await archiveTable.evaluate((element, ids) => {
          const table = element as HTMLElement & { dataManager?: { getCell?: (r: string, c: string) => { text?: { toString?: () => string; length?: number } } | undefined } };
          const cells = [ids.first, ids.second].map(({ row, column }) => {
            const td = element.querySelector<HTMLTableCellElement>(`td[data-row-id="${row}"][data-column-id="${column}"]`);
            const rich = td?.querySelector('rich-text') as (HTMLElement & { inlineEditor?: { getInlineRange?: () => unknown } }) | null;
            const editor = rich?.querySelector<HTMLElement>('.inline-editor') ?? null;
            const cell = table.dataManager?.getCell?.(row, column);
            const selection = window.getSelection();
            return { tdPresent: Boolean(td), tdHtml: td?.innerHTML ?? null, richText: Boolean(rich), contenteditable: editor?.getAttribute('contenteditable') ?? null,
              activeInside: Boolean(editor && editor.contains(document.activeElement)), activeTag: document.activeElement?.tagName ?? null,
              selectionCollapsed: selection?.isCollapsed ?? null, selectionNodeInCell: Boolean(selection?.anchorNode && td?.contains(selection.anchorNode)),
              inlineRange: rich?.inlineEditor?.getInlineRange?.() ?? null, yText: cell?.text?.toString?.() ?? null, yLength: cell?.text?.length ?? null };
          });
          return cells;
        }, { first: { row: firstRowId!, column: firstColumnId! }, second: { row: secondRowId!, column: secondColumnId! } })));
        expect(firstRowId && firstColumnId && secondRowId && secondColumnId, 'wp5_archive_table_cell_addresses_present').toBeTruthy();
        const waitForTableCellText = async (targetRowId: string, targetColumnId: string, text: string) => {
          const tableId = await archiveTable.getAttribute('data-block-id');
          expect(tableId, 'wp5_archive_table_block_id_present').toBeTruthy();
          await page.waitForFunction(({ tableId, rowId, columnId, text }) => {
            const table = document.querySelector<HTMLElement & { dataManager?: { getCell?: (row: string, column: string) => { text?: { toString?: () => string } } | undefined } }>(`affine-table[data-block-id="${tableId}"]`);
            return (table?.dataManager?.getCell?.(rowId, columnId)?.text?.toString?.() ?? '').includes(text);
          }, { tableId, rowId: targetRowId, columnId: targetColumnId, text }, { timeout: 5_000 });
        };
        const assertTableCellEditable = async (cell: Locator) => cell.evaluate((targetCell): boolean => {
          const richText = targetCell.querySelector('rich-text');
          if (!richText) return false;
          const editor = richText.querySelector<HTMLElement>('.inline-editor');
          return Boolean(editor && editor.getAttribute('contenteditable') === 'true');
        });
        const focusTableCellEditor = async (editor: Locator, rowId: string, columnId: string) => {
          await editor.click();
          observed.setDiagnosticAssertion('wp5_archive_cell_click_complete');
          await page.waitForFunction(({ rowId, columnId }) => {
            const cell = document.querySelector<HTMLTableCellElement>(`td[data-row-id="${rowId}"][data-column-id="${columnId}"]`);
            const activeEditor = cell?.querySelector<HTMLElement>('rich-text .inline-editor[contenteditable="true"]');
            return Boolean(activeEditor && document.activeElement === activeEditor);
          }, { rowId, columnId }, { timeout: 5_000 });
        };
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_038');
        expect(await assertTableCellEditable(firstCell), 'wp5_archive_table_first_cell_editable').toBe(true);
        await focusTableCellEditor(firstCellEditor, firstRowId!, firstColumnId!);
        observed.setDiagnosticAssertion('wp5_archive_cell_focus_ready');
        await page.keyboard.insertText(mergeSourceText);
        await waitForTableCellText(firstRowId!, firstColumnId!, mergeSourceText);
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_039');
        expect(await assertTableCellEditable(secondCell), 'wp5_archive_table_second_cell_editable').toBe(true);
        await focusTableCellEditor(secondCellEditor, secondRowId!, secondColumnId!);
        observed.setDiagnosticAssertion('wp5_archive_cell_focus_ready');
        await page.keyboard.insertText(mergeCoveredText);
        await waitForTableCellText(secondRowId!, secondColumnId!, mergeCoveredText);
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_040');
        const firstCellBox = await firstCell.boundingBox();
        const secondCellBox = await secondCell.boundingBox();
        expect(firstCellBox, 'wp5_archive_table_first_cell_geometry').not.toBeNull();
        expect(secondCellBox, 'wp5_archive_table_second_cell_geometry').not.toBeNull();
        await page.mouse.move(firstCellBox!.x + firstCellBox!.width / 2, firstCellBox!.y + firstCellBox!.height / 2);
        await page.mouse.down();
        await page.mouse.move(secondCellBox!.x + secondCellBox!.width / 2, secondCellBox!.y + secondCellBox!.height / 2, { steps: 4 });
        await page.mouse.up();
        await secondCell.click({ button: 'right' });
        const mergeCellsAction = page.getByText('合并单元格', { exact: true });
        await expect(mergeCellsAction).toBeVisible();
        await mergeCellsAction.click();
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_041');
        const tableMergeCount = await archiveTable.evaluate(element => {
          const table = element as HTMLElement & { dataManager?: { model?: { props?: { mergeRegions?: Record<string, unknown> } } } };
          return Object.keys(table.dataManager?.model?.props?.mergeRegions ?? {}).length;
        });
        expect(tableMergeCount, 'wp5_archive_table_merge_model').toBe(1);
        await expect(archiveTable.locator('td[data-row-id][data-column-id]').first()).toHaveAttribute('colspan', '2');
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_042');
        const mergedCellTexts = await archiveTable.evaluate((element, expectedRowTexts) => {
          const table = element as HTMLElement & { dataManager?: { rows$?: { value: Array<{ rowId: string }> }; columns$?: { value: Array<{ columnId: string }> }; getCell?: (rowId: string, columnId: string) => { text?: { toString?: () => string } } | undefined } };
          const row = table.dataManager?.rows$?.value[0];
          const columns = table.dataManager?.columns$?.value ?? [];
          if (!row || !table.dataManager?.getCell) return [];
          return columns.slice(0, 2).map(column => table.dataManager!.getCell!(row.rowId, column.columnId)?.text?.toString?.() ?? '')
            .filter(value => expectedRowTexts.some(text => value.includes(text)));
        }, [mergeSourceText, mergeCoveredText]);
        expect(mergedCellTexts.join('\n'), 'wp5_archive_table_merge_retains_cell_text').toContain(mergeSourceText);
        expect(mergedCellTexts.join('\n'), 'wp5_archive_table_merge_retains_covered_text').toContain(mergeCoveredText);
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_036');

        const mergedCell = archiveTable.locator('td[data-row-id][data-column-id][colspan="2"]').first();
        await mergedCell.click({ button: 'right' });
        observed.setDiagnosticAssertion('wp5_archive_table_vertical_menu_action');
        const verticalMiddleAction = page.getByRole('button', { name: '垂直居中', exact: true });
        await expect(verticalMiddleAction, 'wp5_archive_table_vertical_menu_action').toBeVisible();
        await verticalMiddleAction.click();
        const verticalAlignment = await archiveTable.evaluate((element, address) => {
          const table = element as HTMLElement & { dataManager?: { getCell?: (row: string, column: string) => { verticalAlign?: string } | undefined } };
          return table.dataManager?.getCell?.(address.row, address.column)?.verticalAlign ?? 'top';
        }, { row: firstRowId!, column: firstColumnId! });
        expect(verticalAlignment, 'wp5_archive_table_vertical_alignment_model').toBe('middle');
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_043');
        await mergedCell.click({ button: 'right' });
        const splitCellAction = page.getByText('拆分单元格', { exact: true });
        await expect(splitCellAction, 'wp5_archive_table_split_menu_action').toBeVisible();
        await splitCellAction.click();
        const mergeCountAfterSplit = await archiveTable.evaluate(element => {
          const table = element as HTMLElement & { dataManager?: { model?: { props?: { mergeRegions?: Record<string, unknown> } } } };
          return Object.keys(table.dataManager?.model?.props?.mergeRegions ?? {}).length;
        });
        expect(mergeCountAfterSplit, 'wp5_archive_table_split_model').toBe(0);
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_044');
        const splitFirstBox = await firstCell.boundingBox();
        const splitSecondBox = await secondCell.boundingBox();
        expect(splitFirstBox, 'wp5_archive_table_split_first_cell_geometry').not.toBeNull();
        expect(splitSecondBox, 'wp5_archive_table_split_second_cell_geometry').not.toBeNull();
        await page.mouse.move(splitFirstBox!.x + splitFirstBox!.width / 2, splitFirstBox!.y + splitFirstBox!.height / 2);
        await page.mouse.down();
        await page.mouse.move(splitSecondBox!.x + splitSecondBox!.width / 2, splitSecondBox!.y + splitSecondBox!.height / 2, { steps: 4 });
        await page.mouse.up();
        await secondCell.click({ button: 'right' });
        const remergeAction = page.getByText('合并单元格', { exact: true });
        await expect(remergeAction, 'wp5_archive_table_remerge_menu_action').toBeVisible();
        await remergeAction.click();
        const mergeCountAfterRemerge = await archiveTable.evaluate(element => {
          const table = element as HTMLElement & { dataManager?: { model?: { props?: { mergeRegions?: Record<string, unknown> } } } };
          return Object.keys(table.dataManager?.model?.props?.mergeRegions ?? {}).length;
        });
        expect(mergeCountAfterRemerge, 'wp5_archive_table_remerge_model').toBe(1);
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_045');

        const firstTableRow = archiveTable.locator('tr[data-row-id]').first();
        const rowBox = await firstTableRow.boundingBox();
        const rowId = await firstTableRow.getAttribute('data-row-id');
        expect(rowBox, 'wp5_archive_table_row_geometry').not.toBeNull();
        expect(rowId, 'wp5_archive_table_row_id_present').toBeTruthy();
        await page.mouse.move(rowBox!.x + Math.min(rowBox!.width / 2, 80), rowBox!.y + rowBox!.height - 1);
        await page.mouse.down();
        await page.mouse.move(rowBox!.x + Math.min(rowBox!.width / 2, 80), rowBox!.y + rowBox!.height + 20, { steps: 3 });
        await page.mouse.up();
        const persistedRowHeight = await archiveTable.evaluate((element, targetRowId) => {
          const table = element as HTMLElement & { dataManager?: { model?: { props?: { rows?: Record<string, { minHeight?: number }> } } } };
          return table.dataManager?.model?.props?.rows?.[targetRowId ?? '']?.minHeight ?? null;
        }, rowId);
        expect(persistedRowHeight, 'wp5_archive_table_row_resize_model').toBeGreaterThan(38);
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_037');

        observed.setWp5Step('archive_ux_emoji');
        observed.setDiagnosticAssertion('wp5_archive_emoji_command_visible');
        const emojiParagraph = richHost.locator('affine-paragraph').filter({ hasText: richText }).first();
        const emojiTarget = emojiParagraph.locator('rich-text .inline-editor');
        await emojiTarget.click();
        await page.keyboard.press('End');
        await page.keyboard.press('/');
        const emojiSlashItem = page.getByText('插入表情图标', { exact: true });
        // The native slash menu is a scrollable list; this command is below
        // its initial viewport, so bring the actual menu item into view before
        // asserting visibility and exercising its picker action.
        await emojiSlashItem.scrollIntoViewIfNeeded();
        await expect(emojiSlashItem, 'wp5_archive_emoji_command_visible').toBeVisible({ timeout: 10000 });
        await emojiSlashItem.click();
        const emojiDialog = page.getByRole('dialog', { name: '选择表情' });
        observed.setDiagnosticAssertion('wp5_archive_emoji_picker_visible');
        await expect(emojiDialog, 'wp5_archive_emoji_picker_visible').toBeVisible();
        const emojiPicker = emojiDialog.locator('em-emoji-picker');
        const emojiSearch = emojiPicker.locator('input[type="search"]');
        await expect(emojiSearch, 'wp5_archive_emoji_picker_visible').toHaveAttribute('placeholder', '搜索');
        await emojiSearch.fill('笑脸');
        observed.setDiagnosticAssertion('wp5_archive_emoji_search_results');
        // Read the actual picker shadow DOM and select the requested native
        // emoji by its accessible label; search ranking can reorder results.
        const hasGrinningEmoji = await emojiPicker.evaluate(picker =>
          [...(picker.shadowRoot?.querySelectorAll('button[aria-posinset]') ?? [])]
            .some(button => button.getAttribute('aria-label') === '😀'));
        observed.setDiagnosticAssertion(hasGrinningEmoji
          ? 'wp5_archive_emoji_dom_target_present' : 'wp5_archive_emoji_dom_target_missing');
        expect(hasGrinningEmoji, 'wp5_archive_emoji_search_dom_target').toBe(true);
        const grinningEmoji = emojiPicker.locator('button[aria-label="😀"]');
        await expect(grinningEmoji, 'wp5_archive_emoji_search_results').toBeVisible({ timeout: 10000 });
        await grinningEmoji.click();
        observed.setDiagnosticAssertion('wp5_archive_emoji_insert');
        await expect(emojiParagraph, 'wp5_archive_emoji_insert').toContainText('😀', { timeout: 5000 });
        await expect(emojiDialog, 'wp5_archive_emoji_insert').toHaveCount(0);

        await richDialog.locator('.blocksuite-canvas-tools > summary').click();
        const canvasGallery = richDialog.getByRole('region', { name: '独立画布资源' });
        observed.setDiagnosticAssertion('wp5_archive_canvas_reference_lifecycle');
        const canvasCreate = page.waitForResponse(response => response.request().method() === 'POST'
          && new URL(response.url()).pathname === `/api/notes/drafts/${richCreated.path}/blocksuite/resources`, { timeout: 20000 });
        await canvasGallery.getByRole('button', { name: '新建独立画布' }).click();
        const canvasCreated = await canvasCreate;
        expect(canvasCreated.status(), 'wp5_archive_canvas_reference_lifecycle').toBe(200);
        const sourceCanvas = await canvasCreated.json() as { resource_id: string };
        const sourceCard = canvasGallery.locator('.canvas-b-card').filter({ hasText: sourceCanvas.resource_id });
        await expect(sourceCard, 'wp5_archive_canvas_reference_lifecycle').toBeVisible();
        const removableCanvasCreate = page.waitForResponse(response => response.request().method() === 'POST'
          && new URL(response.url()).pathname === `/api/notes/drafts/${richCreated.path}/blocksuite/resources`, { timeout: 20000 });
        await canvasGallery.getByRole('button', { name: '新建独立画布' }).click();
        const removableCanvasResponse = await removableCanvasCreate;
        expect(removableCanvasResponse.status(), 'wp5_archive_canvas_reference_lifecycle').toBe(200);
        const removableCanvas = await removableCanvasResponse.json() as { resource_id: string };
        const removableCard = canvasGallery.locator('.canvas-b-card').filter({ hasText: removableCanvas.resource_id });
        await expect(removableCard, 'wp5_archive_canvas_reference_lifecycle').toBeVisible();
        await sourceCard.getByRole('button', { name: '打开编辑' }).click();
        const sourceCanvasDialog = page.getByRole('dialog', { name: 'BlockSuite Edgeless 资源' });
        const sourceCanvasText = sourceCanvasDialog.locator('.blocksuite-resource-host').getByText('独立 Edgeless 便签', { exact: true }).first();
        await expect(sourceCanvasText, 'wp5_archive_canvas_reference_lifecycle').toBeVisible({ timeout: 15000 });
        const sourceCanvasTextBox = await sourceCanvasText.boundingBox();
        expect(sourceCanvasTextBox, 'wp5_archive_canvas_reference_lifecycle').not.toBeNull();
        await page.mouse.dblclick(sourceCanvasTextBox!.x + sourceCanvasTextBox!.width / 2, sourceCanvasTextBox!.y + sourceCanvasTextBox!.height / 2);
        await page.keyboard.press('End');
        const canvasReferenceMarker = `Canvas gallery ${randomUUID()}`;
        await page.keyboard.insertText(` ${canvasReferenceMarker}`);
        const sourceCanvasSave = page.waitForResponse(response => response.request().method() === 'PUT'
          && new URL(response.url()).pathname === `/api/notes/drafts/${richCreated.path}/blocksuite/resources/${sourceCanvas.resource_id}`, { timeout: 20000 });
        await sourceCanvasDialog.getByRole('button', { name: '保存资源' }).click();
        expect((await sourceCanvasSave).status(), 'wp5_archive_canvas_reference_lifecycle').toBe(200);
        await expect(sourceCanvasDialog.getByRole('status')).toHaveText('BlockSuite 资源已保存', { timeout: 15000 });
        await sourceCanvasDialog.getByRole('button', { name: '关闭', exact: true }).click();
        await expect(sourceCard.locator('.canvas-b-card-preview'), 'wp5_archive_canvas_reference_lifecycle')
          .toContainText('自动裁剪预览', { timeout: 10000 });

        const canvasCopy = page.waitForResponse(response => response.request().method() === 'POST'
          && new URL(response.url()).pathname === `/api/notes/drafts/${richCreated.path}/blocksuite/resources`, { timeout: 20000 });
        await sourceCard.getByRole('button', { name: '深拷贝画布' }).click();
        const copiedCanvasResponse = await canvasCopy;
        expect(copiedCanvasResponse.status(), 'wp5_archive_canvas_reference_lifecycle').toBe(200);
        const copiedCanvas = await copiedCanvasResponse.json() as { resource_id: string };
        expect(copiedCanvas.resource_id, 'wp5_archive_canvas_reference_lifecycle').not.toBe(sourceCanvas.resource_id);
        const copiedCard = canvasGallery.locator('.canvas-b-card').filter({ hasText: copiedCanvas.resource_id });
        await expect(copiedCard, 'wp5_archive_canvas_reference_lifecycle').toBeVisible();
        await expect(copiedCard.locator('.canvas-b-card-preview'), 'wp5_archive_canvas_copy_preview').toContainText('自动裁剪预览');
        await expect(sourceCard, 'wp5_archive_canvas_reference_lifecycle').toBeVisible();
        await expect(canvasGallery.locator('.canvas-b-card'), 'wp5_archive_canvas_reference_lifecycle').toHaveCount(3);
        const sourceCanvasRead = await page.request.get(`${baseUrl}/api/notes/drafts/${richCreated.path}/blocksuite/resources/${sourceCanvas.resource_id}`);
        const copiedCanvasRead = await page.request.get(`${baseUrl}/api/notes/drafts/${richCreated.path}/blocksuite/resources/${copiedCanvas.resource_id}`);
        expect(sourceCanvasRead.status(), 'wp5_archive_canvas_source_preserved').toBe(200);
        expect(copiedCanvasRead.status(), 'wp5_archive_canvas_copy_readback').toBe(200);
        const copiedCanvasBody = await copiedCanvasRead.json() as { snapshot: Record<string, unknown> };
        expect(JSON.stringify(copiedCanvasBody.snapshot), 'wp5_archive_canvas_copy_content').toContain(canvasReferenceMarker);
        await removableCard.getByRole('button', { name: '移除引用' }).click();
        await expect(removableCard, 'wp5_archive_canvas_reference_lifecycle').toHaveCount(0);
        expect((await page.request.get(`${baseUrl}/api/notes/drafts/${richCreated.path}/blocksuite/resources/${sourceCanvas.resource_id}`)).status(),
          'wp5_archive_canvas_original_not_deleted').toBe(200);
        expect((await page.request.get(`${baseUrl}/api/notes/drafts/${richCreated.path}/blocksuite/resources/${removableCanvas.resource_id}`)).status(),
          'wp5_archive_canvas_removed_reference_resource_preserved').toBe(200);
        observed.setDiagnosticAssertion('wp5_archive_canvas_reference_lifecycle');

        const savedArchiveResource = page.waitForResponse(response => response.request().method() === 'PUT'
          && new URL(response.url()).pathname === `/api/notes/drafts/${richCreated.path}/blocksuite/resources/${richResourceInfo.resource_id}`, { timeout: 20000 });
        const savedArchiveMarkdown = page.waitForResponse(response => response.request().method() === 'PUT'
          && new URL(response.url()).pathname === `/api/notes/drafts/${richCreated.path}`, { timeout: 20000 });
        await richDialog.getByRole('button', { name: '保存笔记', exact: true }).click();
        expect((await savedArchiveResource).status(), 'wp5_archive_ux_resource_save').toBe(200);
        expect((await savedArchiveMarkdown).status(), 'wp5_archive_ux_markdown_save').toBe(200);
        const archiveSaveState = await richDialog.locator('.document-status').evaluate(element => {
          const status = (element.textContent ?? '').trim();
          if (status === 'BlockSuite 资源已保存') return 'saved';
          if (/失败|冲突|412|409|缺失|未能|ERROR/.test(status)) return 'error';
          if (/正在保存|保存中/.test(status)) return 'pending';
          if (/未保存/.test(status)) return 'unsaved';
          return 'other';
        }).catch(() => 'missing');
        observed.setDiagnosticAssertion(`wp5_archive_resource_save_status_${archiveSaveState}` as DiagnosticAssertion);
        expect(archiveSaveState, 'wp5_archive_ux_resource_save_status').toBe('saved');
        observed.setDiagnosticAssertion('wp5_archive_html_export');
        const htmlExport = page.waitForEvent('download');
        await richDialog.getByRole('button', { name: '导出 HTML' }).click();
        const htmlDownload = await htmlExport;
        expect(htmlDownload.suggestedFilename(), 'wp5_archive_html_download_name').toMatch(/\.html$/i);
        const htmlExportPath = await htmlDownload.path();
        expect(htmlExportPath, 'wp5_archive_html_download_path').toBeTruthy();
        const htmlExportContent = await readFile(htmlExportPath!, 'utf8');
        expect(htmlExportContent, 'wp5_archive_html_download_content').toContain(mergeSourceText);
        expect(htmlExportContent, 'wp5_archive_html_export_script_free').not.toMatch(/<script\b/i);
        observed.setDiagnosticAssertion('wp5_archive_pdf_preview');
        await page.evaluate((marker) => {
          const probeWindow = window as Window & { __wp5PdfProbe?: { state: string } };
          probeWindow.__wp5PdfProbe = { state: 'waiting' };
          const observer = new MutationObserver(() => {
            const frame = document.querySelector<HTMLIFrameElement>('iframe[title="笔记 PDF 打印"]');
            if (!frame) return;
            observer.disconnect();
            frame.addEventListener('load', () => {
              const body = frame.contentDocument?.body;
              probeWindow.__wp5PdfProbe = { state: !body ? 'missing_body'
                : body.innerText.includes(marker) ? 'body_contains_source' : 'body_source_missing' };
            }, { once: true });
          });
          observer.observe(document.body, { childList: true, subtree: true });
        }, mergeSourceText);
        await richDialog.getByRole('button', { name: '导出 PDF' }).click();
        await expect.poll(async () => {
          const state = await page.evaluate(() => (window as Window & { __wp5PdfProbe?: { state: string } }).__wp5PdfProbe?.state ?? 'waiting');
          const status = await richDialog.locator('.document-status').textContent().catch(() => '');
          return state !== 'waiting' ? state : status?.includes('PDF 导出失败') ? 'export_error' : 'waiting';
        }, { timeout: 10000 }).not.toBe('waiting');
        const pdfProbeState = await page.evaluate(() => {
          const state = (window as Window & { __wp5PdfProbe?: { state: string } }).__wp5PdfProbe?.state ?? 'waiting';
          const status = document.querySelector('.document-status')?.textContent ?? '';
          return state !== 'waiting' ? state : status.includes('PDF 导出失败') ? 'export_error' : 'no_frame';
        });
        observed.setDiagnosticAssertion(pdfProbeState === 'body_contains_source' ? 'wp5_archive_pdf_body_contains_source'
          : pdfProbeState === 'export_error' ? 'wp5_archive_pdf_export_error'
            : pdfProbeState === 'no_frame' ? 'wp5_archive_pdf_no_frame'
              : pdfProbeState === 'missing_body' ? 'wp5_archive_pdf_body_missing_body' : 'wp5_archive_pdf_body_source_missing');
        expect(pdfProbeState, 'wp5_archive_pdf_print_preview_dom').toBe('body_contains_source');
        observed.setDiagnosticAssertion('wp5_archive_save_close');
        await richDialog.getByRole('button', { name: '返回笔记列表', exact: true }).click();
        await expect(richDialog).toHaveCount(0);
        observed.setDiagnosticAssertion('wp5_archive_saved_reopen');
        await page.locator('.notes-sidebar li button').filter({ hasText: '新建笔记' }).last().click();
        await expect(richDialog).toBeVisible();
        await expect(richDialog).toHaveAttribute('aria-busy', 'false');
        await expect.poll(async () => (await readBlockOrder()).filter(block => block.text.includes('Archive reorder target')).length)
          .toBe(1);
        const orderAfterReopen = await readBlockOrder();
        expect(orderAfterReopen.filter(block => block.text.includes('Archive reorder target')), 'wp5_desktop_page_plus_reorder_source_after_reopen').toHaveLength(1);
        expect(orderAfterReopen.filter(block => block.text.includes(richText)), 'wp5_desktop_page_plus_reorder_target_after_reopen').toHaveLength(1);
        const reopenedSource = orderAfterReopen.find(block => block.text.includes('Archive reorder target'))!;
        const reopenedTarget = orderAfterReopen.find(block => block.text.includes(richText))!;
        expect(reopenedSource.type, 'wp5_desktop_page_plus_heading_persisted').toBe('h1');
        expect(reopenedSource.textAlign, 'wp5_archive_alignment_persisted').toBe('center');
        expect(reopenedSource.textDelta.some((part: any) => part.attributes?.bold === true), 'wp5_archive_inline_style_persisted').toBe(true);
        expect(reopenedSource.parent, 'wp5_desktop_page_plus_reorder_parent_persisted').toBe(reopenedTarget.parent);
        expect(reopenedSource.order, 'wp5_desktop_page_plus_reorder_source_index_reopened').toBeGreaterThanOrEqual(0);
        expect(reopenedTarget.order, 'wp5_desktop_page_plus_reorder_target_index_reopened').toBeGreaterThanOrEqual(0);
        expect(reopenedSource.order < reopenedTarget.order, 'wp5_desktop_page_plus_reorder_persisted').toBe(expectedSourceBeforeTarget);
        expect(reopenedSource.order < reopenedTarget.order, 'wp5_desktop_page_plus_reorder_reversal_persisted')
          .not.toBe(beforeDrag.order < beforeDragTarget.order);
        const reopenedTable = richHost.locator('affine-table').last();
        observed.setDiagnosticAssertion('wp5_archive_table_state_reopened');
        await expect(reopenedTable).toBeVisible();
        await richDialog.locator('.blocksuite-canvas-tools > summary').click();
        const reopenedGallery = richDialog.getByRole('region', { name: '独立画布资源' });
        const reopenedCopiedCard = reopenedGallery.locator('.canvas-b-card').filter({ hasText: copiedCanvas.resource_id });
        const reopenedSourceCard = reopenedGallery.locator('.canvas-b-card').filter({ hasText: sourceCanvas.resource_id });
        await expect(reopenedGallery.locator('.canvas-b-card'), 'wp5_archive_canvas_reference_reopen').toHaveCount(2);
        await expect(reopenedSourceCard, 'wp5_archive_canvas_reference_reopen').toBeVisible();
        await expect(reopenedCopiedCard, 'wp5_archive_canvas_reference_reopen').toBeVisible();
        await expect(reopenedCopiedCard.locator('.canvas-b-card-preview'), 'wp5_archive_canvas_preview_reopen')
          .toContainText('自动裁剪预览');
        const reopenedCopiedResource = await page.request.get(`${baseUrl}/api/notes/drafts/${richCreated.path}/blocksuite/resources/${copiedCanvas.resource_id}`);
        expect(reopenedCopiedResource.status(), 'wp5_archive_canvas_reference_reopen').toBe(200);
        expect(JSON.stringify((await reopenedCopiedResource.json() as { snapshot: Record<string, unknown> }).snapshot),
          'wp5_archive_canvas_reference_reopen').toContain(canvasReferenceMarker);
        const reopenedTableState = await reopenedTable.evaluate((element, targetRowId) => {
          const table = element as HTMLElement & { dataManager?: { model?: { props?: { mergeRegions?: Record<string, unknown>; rows?: Record<string, { minHeight?: number }> } } } };
          return { mergeCount: Object.keys(table.dataManager?.model?.props?.mergeRegions ?? {}).length,
            rowHeight: table.dataManager?.model?.props?.rows?.[targetRowId ?? '']?.minHeight ?? 38 };
        }, rowId);
        expect(reopenedTableState.mergeCount, 'wp5_archive_table_merge_reopened').toBe(1);
        expect(reopenedTableState.rowHeight, 'wp5_archive_table_row_resize_reopened').toBeGreaterThan(38);
        const reopenedVerticalAlignment = await reopenedTable.evaluate((element, address) => {
          const table = element as HTMLElement & { dataManager?: { getCell?: (row: string, column: string) => { verticalAlign?: string } | undefined } };
          return table.dataManager?.getCell?.(address.row, address.column)?.verticalAlign ?? 'top';
        }, { row: firstRowId!, column: firstColumnId! });
        expect(reopenedVerticalAlignment, 'wp5_archive_table_vertical_menu_action').toBe('middle');
        const reopenedMergeTexts = await reopenedTable.evaluate((element, expectedRowTexts) => {
          const table = element as HTMLElement & { dataManager?: { rows$?: { value: Array<{ rowId: string }> }; columns$?: { value: Array<{ columnId: string }> }; getCell?: (rowId: string, columnId: string) => { text?: { toString?: () => string } } | undefined } };
          const row = table.dataManager?.rows$?.value[0];
          const columns = table.dataManager?.columns$?.value ?? [];
          if (!row || !table.dataManager?.getCell) return [];
          return columns.slice(0, 2).map(column => table.dataManager!.getCell!(row.rowId, column.columnId)?.text?.toString?.() ?? '')
            .filter(value => expectedRowTexts.some(text => value.includes(text)));
        }, [mergeSourceText, mergeCoveredText]);
        expect(reopenedMergeTexts.join('\n'), 'wp5_archive_table_merge_source_reopened').toContain(mergeSourceText);
        expect(reopenedMergeTexts.join('\n'), 'wp5_archive_table_merge_covered_reopened').toContain(mergeCoveredText);
        observed.setDiagnosticAssertion('wp5_resource_checkpoint_034');
        if (process.env.SB_WP5_NATIVE_DOM_EVIDENCE_PATH) {
          await targetParagraph.hover();
          const interactiveChrome = await Promise.all([grip, plus].map(locator => locator.evaluate(button => {
            const rect = button.getBoundingClientRect();
            const style = getComputedStyle(button);
            return { kind: button.getAttribute('data-kind'), visible: button.dataset.visible === 'true'
              && rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none',
              x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) };
          })));
          const titleAndBody = await page.locator('.notes-document-rich-page').evaluate(root => {
            const visible = (node: Element) => { const rect = node.getBoundingClientRect(); return rect.width > 0 && rect.height > 0 && getComputedStyle(node).display !== 'none'; };
            const heading = [...root.querySelectorAll('.document-heading')].filter(visible).map(node => node.textContent?.trim() ?? '');
            const hiddenTitle = root.querySelector('[data-sb-document-title-block="true"]');
            const hiddenTitleDisplay = hiddenTitle ? getComputedStyle(hiddenTitle).display : null;
            const host = root.querySelector<HTMLElement>('.blocksuite-resource-host') as (HTMLElement & { __sbBlockSuiteStore?: any }) | null;
            const blocks = (host?.__sbBlockSuiteStore?.getBlocksByFlavour('affine:paragraph') ?? []).map(({ model }: any) => ({
              text: model.props.text?.toString?.() ?? '', type: model.props.type,
            }));
            return { visibleTitleHeadings: heading, hiddenTitleDisplay, blocks,
              inlineEditor: Boolean(root.querySelector('.blocksuite-resource-dialog.blocksuite-resource-inline')),
              modalEditorCount: document.querySelectorAll('.blocksuite-resource-backdrop').length };
          });
          await writeFile(process.env.SB_WP5_NATIVE_DOM_EVIDENCE_PATH, JSON.stringify({
            viewport: '1440x1000', enter: liveEnterEvidence, firstOpen: readyMetrics.at(-1), warmOpen: warmReadyMetrics.at(-1),
            titleAndBody, blockControls: interactiveChrome,
            journey: ['create', 'title', 'first line', 'Enter', 'multi paragraph', 'drag', 'insert', 'save', 'switch', 'reopen', 'reload'],
          }, null, 2));
        }
        return;
      }
      if (!nestedCanvasResourceId) throw new Error('Expected nested canvas resource identity for recovery verification');
      const restoreMarker = `restore probe ${randomUUID()}`;
      const restoreParagraph = richDialog.locator('affine-paragraph').filter({ hasText: richText }).first();
      await restoreParagraph.click(); await page.keyboard.press('End'); await page.keyboard.insertText(` ${restoreMarker}`);
      const restoreResourceSave = page.waitForResponse(response => response.request().method() === 'PUT'
        && new URL(response.url()).pathname === `/api/notes/drafts/${richCreated.path}/blocksuite/resources/${richResourceInfo.resource_id}`, { timeout: 20000 });
      await richDialog.getByRole('button', { name: '保存笔记', exact: true }).click();
      expect((await restoreResourceSave).status(), 'wp5_rich_page_restore_probe_save').toBe(200);
      await expect(richDialog.getByRole('status').first()).toContainText('已保存', { timeout: 15000 });
      await richDialog.locator('.blocksuite-more-tools > summary').click();
      await richDialog.getByRole('button', { name: '查看版本与恢复' }).click();
      const backupSection = page.getByRole('region', { name: 'BlockSuite 快照恢复' });
      await expect(backupSection).toBeVisible({ timeout: 15000 });
      observed.setWp5Step('rich_page_backup_preview');
      const snapshotChoice = backupSection.getByRole('button', { name: '选择并预览' }).first();
      await expect(snapshotChoice).toBeVisible();
      await snapshotChoice.click();
      const snapshotPreview = backupSection.getByLabel('BlockSuite 快照预览');
      await expect(snapshotPreview).toBeVisible();
      await expect(snapshotPreview.locator('pre').first()).toContainText(richText);
      await expect(snapshotPreview.locator('pre').first()).not.toContainText(restoreMarker);
      page.once('dialog', dialog => dialog.accept());
      const blockSuiteRestoreResponse = page.waitForResponse(response => response.request().method() === 'POST'
        && new URL(response.url()).pathname.includes('/blocksuite/snapshots/')
        && new URL(response.url()).pathname.endsWith('/restore'), { timeout: 30000 });
      observed.setWp5Step('rich_page_snapshot_restore');
      await snapshotPreview.getByRole('button', { name: '确认恢复此 BlockSuite 快照' }).click();
      expect((await blockSuiteRestoreResponse).status(), 'wp5_rich_page_snapshot_restore').toBe(200);
      await expect(page.getByRole('alert')).toContainText('BlockSuite 快照已恢复', { timeout: 15000 });
      const restoredMarkdown = await page.request.get(`${baseUrl}/api/notes/drafts/${richCreated.path}`);
      expect(restoredMarkdown.status(), 'wp5_rich_page_snapshot_markdown_read').toBe(200);
      expect((await restoredMarkdown.json() as { content: string }).content, 'wp5_rich_page_snapshot_markdown_content').toContain(richText);
      expect((await restoredMarkdown.json() as { content: string }).content, 'wp5_rich_page_snapshot_markdown_removed_probe').not.toContain(restoreMarker);
      const restoredNativeResponse = await page.request.get(`${baseUrl}/api/notes/drafts/${richCreated.path}/blocksuite/resources/${richResourceInfo.resource_id}`);
      expect(restoredNativeResponse.status(), 'wp5_rich_page_snapshot_resource_read').toBe(200);
      expect(JSON.stringify((await restoredNativeResponse.json() as { snapshot: unknown }).snapshot), 'wp5_rich_page_snapshot_resource_content').toContain(richText);
      observed.setDiagnosticAssertion('wp5_resource_close');

      observed.setWp5Step('rich_page_post_restore_reopen');
      await page.reload();
      const reopenedRichDialog = page.locator('.blocksuite-resource-inline');
      await expect(reopenedRichDialog).toBeVisible({ timeout: 20000 });
      await expect(reopenedRichDialog).toHaveAttribute('aria-busy', 'false', { timeout: 20000 });
      const reopenedEdgelessViewport = reopenedRichDialog.locator('.affine-edgeless-viewport');
      if (await reopenedEdgelessViewport.count()) {
        // A restored Edgeless document can retain a camera that leaves the
        // Note outside the bounded viewport. Use the editor's visible control
        // so the reopen assertion checks readable, actually reachable content.
        const fitToScreen = reopenedRichDialog.locator('.affine-edgeless-viewport edgeless-zoom-toolbar edgeless-tool-icon-button').first();
        await expect(fitToScreen, 'wp5_rich_page_reopen_fit_control_visible').toBeVisible({ timeout: 5000 });
        await fitToScreen.click({ timeout: 5000 });
      }
      await expect(reopenedRichDialog.getByText(richText, { exact: false })).toBeVisible({ timeout: 20000 });
      observed.setDiagnosticAssertion('wp5_resource_reopen');

      // Simulate an external Markdown edit while the local native document is
      // open. Its CAS must reject automatic projection; both sides and recovery
      // JSON must remain readable for explicit resolution.
      const beforeExternalWrite = await page.request.get(`${baseUrl}/api/notes/drafts/${richCreated.path}`);
      const latestRichNote = await beforeExternalWrite.json() as { content: string; etag: string };
      const latestArtifactSetEtag = beforeExternalWrite.headers()['x-artifact-set-etag'];
      expect(latestArtifactSetEtag, 'wp5_rich_page_conflict_artifact_set_etag').toMatch(/^"[a-f0-9]{64}"$/);
      if (!latestArtifactSetEtag) throw new Error('BlockSuite artifact set version is missing from the note read.');
      const externalRichMarker = `external rich-page ${randomUUID()}`;
      observed.setWp5Step('rich_page_conflict');
      const externalRichWrite = await page.evaluate(async ({ path, content, etag, artifactSetEtag, marker }) => {
        const response = await fetch(`/api/notes/drafts/${path}`, { method: 'PUT', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json', 'If-Match': `"${etag}"`, 'If-Artifact-Set-Match': artifactSetEtag },
          body: JSON.stringify({ content: `${content}\n${marker}\n` }) });
        return response.status;
      }, { path: richCreated.path, content: latestRichNote.content, etag: latestRichNote.etag,
        artifactSetEtag: latestArtifactSetEtag, marker: externalRichMarker });
      expect(externalRichWrite, 'wp5_rich_page_external_markdown_write').toBe(200);
      const conflictRichDialog = page.locator('.blocksuite-resource-inline');
      const localRichMarker = `local rich-page ${randomUUID()}`;
      const localRichParagraph = conflictRichDialog.locator('affine-paragraph').filter({ hasText: richText }).first();
      const conflictSaveButton = conflictRichDialog.getByRole('button', { name: '保存笔记', exact: true });
      let conflictAction = 'paragraph-geometry';
      type NoteClickState = { selected: boolean; editing: boolean; gfxEditing: boolean; caretInParagraph: boolean; locked: boolean | null; rangeCount: number; anchorOffset: number | null };
      let firstClickState: NoteClickState | null = null;
      let secondClickState: NoteClickState | null = null;
      let structureSummary: { hostKind: string | null; paragraphCount: number; paragraphPath: string[]; paragraphRect: number[]; dialogRect: number[]; viewportRect: number[]; windowSize: number[]; notes: Array<[string, number[], number, boolean]>; hitPath: string[]; hitTargets: [boolean, boolean, number] } | null = null;
      let lastPointerProbe: { hitParagraph: boolean; hitNote: boolean; depth: number; hitTag: string; stableSamples: number; geometryUnchanged: boolean } | null = null;
      try {
        let bounds: Awaited<ReturnType<typeof localRichParagraph.boundingBox>> = null;
        let viewportBounds: typeof bounds = null;
        let clickPoint: { x: number; y: number } | null = null;
        let previousHitGeometry = '';
        let stableTargetSamples = 0;
        conflictAction = 'stable-pointer-target';
        await expect.poll(async () => {
          bounds = await localRichParagraph.boundingBox();
          viewportBounds = await conflictRichDialog.locator('.affine-edgeless-viewport').boundingBox();
          if (!bounds || !viewportBounds) { stableTargetSamples = 0; return false; }
          const visibleLeft = Math.max(bounds.x, viewportBounds.x);
          const visibleTop = Math.max(bounds.y, viewportBounds.y);
          const visibleRight = Math.min(bounds.x + bounds.width, viewportBounds.x + viewportBounds.width);
          const visibleBottom = Math.min(bounds.y + bounds.height, viewportBounds.y + viewportBounds.height);
          if (visibleRight <= visibleLeft || visibleBottom <= visibleTop) { stableTargetSamples = 0; return false; }
          clickPoint = { x: (visibleLeft + visibleRight) / 2, y: (visibleTop + visibleBottom) / 2 };
          const hitPath = await localRichParagraph.evaluate((targetParagraph, { x, y }) => {
            let hit: Element | null = document.elementFromPoint(x, y);
            while (hit?.shadowRoot) {
              const inner = hit.shadowRoot.elementFromPoint(x, y);
              if (!inner || inner === hit) break;
              hit = inner;
            }
            let targetNote: Element | null = null;
            let targetNode: Node | null = targetParagraph;
            while (targetNode) {
              if (targetNode instanceof Element && targetNode.localName === 'affine-edgeless-note') {
                targetNote = targetNode;
                break;
              }
              if (targetNode.parentNode) targetNode = targetNode.parentNode;
              else {
                const root = targetNode.getRootNode();
                targetNode = root instanceof ShadowRoot ? root.host : null;
              }
            }
            let hitParagraph = false;
            let hitNote = false;
            let depth = 0;
            let node: Node | null = hit;
            while (node && depth < 64) {
              if (node === targetParagraph) hitParagraph = true;
              if (node === targetNote) hitNote = true;
              depth += 1;
              if (node.parentNode) node = node.parentNode;
              else {
                const root = node.getRootNode();
                node = root instanceof ShadowRoot ? root.host : null;
              }
            }
            return { hitParagraph, hitNote, depth, hitTag: hit?.localName ?? 'none' };
          }, clickPoint);
          lastPointerProbe = {
            ...hitPath,
            stableSamples: 0,
            geometryUnchanged: false,
          };
          // Before editing, BlockSuite's Edgeless Note mask intentionally
          // receives pointer input. The first real click selects the Note;
          // only after the second click is paragraph editing/caret asserted.
          const targetHit = hitPath.hitNote;
          const geometry = JSON.stringify([bounds.x, bounds.y, bounds.width, bounds.height,
            viewportBounds.x, viewportBounds.y, viewportBounds.width, viewportBounds.height, hitPath]);
          const geometryUnchanged = geometry === previousHitGeometry;
          stableTargetSamples = targetHit && geometryUnchanged ? stableTargetSamples + 1 : targetHit ? 1 : 0;
          lastPointerProbe.stableSamples = stableTargetSamples;
          lastPointerProbe.geometryUnchanged = geometryUnchanged;
          previousHitGeometry = geometry;
          return stableTargetSamples >= 2;
        }, { timeout: 5000, message: 'wp5_rich_page_conflict_target_hit_stable_after_fit' }).toBe(true);
        expect(bounds, 'wp5_rich_page_conflict_paragraph_visible').not.toBeNull();
        expect(viewportBounds, 'wp5_rich_page_conflict_edgeless_viewport_visible').not.toBeNull();
        const visibleLeft = Math.max(bounds!.x, viewportBounds!.x);
        const visibleTop = Math.max(bounds!.y, viewportBounds!.y);
        const visibleRight = Math.min(bounds!.x + bounds!.width, viewportBounds!.x + viewportBounds!.width);
        const visibleBottom = Math.min(bounds!.y + bounds!.height, viewportBounds!.y + viewportBounds!.height);
        expect(visibleRight).toBeGreaterThan(visibleLeft);
        expect(visibleBottom).toBeGreaterThan(visibleTop);
        expect(clickPoint).not.toBeNull();
        const confirmedClickPoint = clickPoint!;
        conflictAction = 'readonly-dom-structure';
        structureSummary = await page.evaluate(({ x, y, text }) => {
          const dialog = document.querySelector<HTMLElement>('.blocksuite-resource-dialog');
          if (!dialog) return { hostKind: null, paragraphCount: 0, paragraphPath: [], paragraphRect: [], dialogRect: [], viewportRect: [], windowSize: [], notes: [], hitPath: [], hitTargets: [false, false, 0] as [boolean, boolean, number] };
          const roots: Array<Document | ShadowRoot | HTMLElement> = [dialog];
          const elements: Element[] = [];
          for (let index = 0; index < roots.length; index += 1) {
            const root = roots[index];
            for (const element of root.querySelectorAll('*')) {
              elements.push(element);
              if (element.shadowRoot) roots.push(element.shadowRoot);
            }
          }
          const pathOf = (start: Node | null) => {
            const path: string[] = [];
            let node = start;
            while (node && path.length < 64) {
              if (node instanceof Element) path.push(node.localName);
              if (node.parentNode) node = node.parentNode;
              else {
                const root = node.getRootNode();
                node = root instanceof ShadowRoot ? root.host : null;
              }
            }
            return path;
          };
          const paragraphs = elements.filter(element => element.localName === 'affine-paragraph'
            && element.textContent?.includes(text));
          const notes: Array<[string, number[], number, boolean]> = elements.filter(element => element.localName === 'affine-edgeless-note').slice(0, 3).map(element => {
            const note = element as HTMLElement & { model?: { id?: string } };
            const rect = note.getBoundingClientRect();
            const bodyParagraphs = [...new Set([
              ...note.querySelectorAll('affine-paragraph'),
              ...(note.shadowRoot?.querySelectorAll('affine-paragraph') ?? []),
            ])];
            const includesTarget = paragraphs.some(paragraph => bodyParagraphs.includes(paragraph));
            return [note.model?.id?.slice(-6) ?? '',
              [Math.round(rect.x), Math.round(rect.y), Math.round(rect.width), Math.round(rect.height)],
              bodyParagraphs.length, includesTarget] as [string, number[], number, boolean];
          });
          const host = dialog.querySelector<HTMLElement>('.blocksuite-resource-host');
          const dialogRect = dialog.getBoundingClientRect();
          const viewportRect = dialog.querySelector<HTMLElement>('.affine-edgeless-viewport')?.getBoundingClientRect();
          const paragraphRect = paragraphs[0]?.getBoundingClientRect();
          const rectValues = (rect?: DOMRect) => rect ? [Math.round(rect.x), Math.round(rect.y), Math.round(rect.width), Math.round(rect.height)] : [];
          let hit: Element | null = document.elementFromPoint(x, y);
          while (hit?.shadowRoot) {
            const inner = hit.shadowRoot.elementFromPoint(x, y);
            if (!inner || inner === hit) break;
            hit = inner;
          }
          const targetParagraph = paragraphs[0];
          const targetNote = targetParagraph && elements.find(element => element.localName === 'affine-edgeless-note'
            && [...element.querySelectorAll('affine-paragraph'), ...(element.shadowRoot?.querySelectorAll('affine-paragraph') ?? [])]
              .includes(targetParagraph));
          let hitParagraph = false;
          let hitNote = false;
          let hitDepth = 0;
          let hitNode: Node | null = hit;
          while (hitNode && hitDepth < 64) {
            if (hitNode === targetParagraph) hitParagraph = true;
            if (hitNode === targetNote) hitNote = true;
            hitDepth += 1;
            if (hitNode.parentNode) hitNode = hitNode.parentNode;
            else {
              const root = hitNode.getRootNode();
              hitNode = root instanceof ShadowRoot ? root.host : null;
            }
          }
          return { hostKind: host?.dataset.kind ?? null, paragraphCount: paragraphs.length,
            paragraphPath: pathOf(paragraphs[0] ?? null), paragraphRect: rectValues(paragraphRect),
            dialogRect: rectValues(dialogRect), viewportRect: rectValues(viewportRect), windowSize: [innerWidth, innerHeight],
            notes, hitPath: pathOf(hit), hitTargets: [hitParagraph, hitNote, hitDepth] as [boolean, boolean, number] };
        }, { x: confirmedClickPoint.x, y: confirmedClickPoint.y, text: richText });
        expect(structureSummary.notes.some(note => note[3]), 'wp5_rich_page_conflict_paragraph_belongs_to_active_note').toBe(true);
        expect(structureSummary.hitTargets[1], 'wp5_rich_page_conflict_hit_target_note').toBe(true);
        await page.evaluate(() => {
          const target = window as Window & { __wp5NotePointerHits?: Array<{ note: boolean; paragraph: boolean; editable: boolean }> };
          target.__wp5NotePointerHits = [];
          const recordPointer = (event: PointerEvent) => {
            const path = event.composedPath().filter((item): item is Element => item instanceof Element);
            target.__wp5NotePointerHits?.push({
              note: path.some(element => element.localName === 'affine-edgeless-note'),
              paragraph: path.some(element => element.localName === 'affine-paragraph'),
              editable: path.some(element => (element as HTMLElement).isContentEditable),
            });
            if (target.__wp5NotePointerHits!.length >= 2) window.removeEventListener('pointerdown', recordPointer, true);
          };
          window.addEventListener('pointerdown', recordPointer, true);
        });
        const readRichNoteState = () => localRichParagraph.evaluate(paragraph => {
          let node: Node | null = paragraph;
          while (node) {
            if (node instanceof Element && node.localName === 'affine-edgeless-note') {
              const note = node as HTMLElement & { model?: { id?: string; isLocked?: () => boolean }; gfx?: { selection?: { has?: (id: string) => boolean; editing?: boolean } } };
              const selected = Boolean(note.model?.id && note.gfx?.selection?.has?.(note.model.id));
              const editing = note.querySelector<HTMLElement>('[data-testid="edgeless-note-container"]')?.dataset.editing === 'true';
              const gfxEditing = note.gfx?.selection?.editing === true;
              const nativeSelection = window.getSelection();
              let anchor: Node | null = nativeSelection?.anchorNode ?? null;
              const anchorOffset = nativeSelection?.anchorOffset ?? null;
              let caretInParagraph = false;
              while (anchor) {
                if (anchor === paragraph) { caretInParagraph = true; break; }
                if (anchor.parentNode) anchor = anchor.parentNode;
                else {
                  const root = anchor.getRootNode();
                  anchor = root instanceof ShadowRoot ? root.host : null;
                }
              }
              return { selected, editing, gfxEditing, caretInParagraph, locked: note.model?.isLocked?.() ?? null,
                rangeCount: nativeSelection?.rangeCount ?? 0, anchorOffset };
            }
            if (node.parentNode) node = node.parentNode;
            else {
              const root = node.getRootNode();
              node = root instanceof ShadowRoot ? root.host : null;
            }
          }
          return null;
        });
        conflictAction = 'note-click-1';
        await page.mouse.click(confirmedClickPoint.x, confirmedClickPoint.y);
        conflictAction = 'note-wait-selection';
        await expect.poll(async () => {
          firstClickState = await readRichNoteState();
          return firstClickState?.selected;
        }, { timeout: 5000 })
          .toBe(true);
        conflictAction = 'note-click-2';
        await page.mouse.click(confirmedClickPoint.x, confirmedClickPoint.y);
        conflictAction = 'note-wait-editing';
        await expect.poll(async () => {
          secondClickState = await readRichNoteState();
          return secondClickState?.editing === true && secondClickState.gfxEditing && secondClickState.caretInParagraph;
        }, { timeout: 5000 })
          .toBe(true);
        const pointerHits = await page.evaluate(() =>
          (window as Window & { __wp5NotePointerHits?: Array<{ note: boolean; paragraph: boolean; editable: boolean }> }).__wp5NotePointerHits ?? []);
        expect(pointerHits, 'wp5_rich_page_conflict_real_pointer_clicks').toHaveLength(2);
        expect(pointerHits.every(hit => hit.note), 'wp5_rich_page_conflict_pointer_stayed_in_target_note').toBe(true);
        conflictAction = 'keyboard-edit';
        await page.keyboard.press('End'); await page.keyboard.insertText(` ${localRichMarker}`);
        await expect(localRichParagraph, 'wp5_rich_page_conflict_local_edit_visible').toContainText(localRichMarker, { timeout: 5000 });
        const richResourceHost = conflictRichDialog.locator('.blocksuite-resource-host');
        await expect.poll(async () => richResourceHost.evaluate((host, marker) => {
          const store = (host as HTMLElement & { __sbBlockSuiteStore?: any }).__sbBlockSuiteStore;
          return Boolean(store?.getBlocksByFlavour('affine:paragraph')?.some(({ model }: any) =>
            model.props.text?.toString().includes(marker)));
        }, localRichMarker), { timeout: 5000, message: 'wp5_rich_page_conflict_local_marker_in_store' }).toBe(true);
        conflictAction = 'wait-save-enabled';
        await expect(conflictSaveButton).toBeEnabled({ timeout: 5000 });
        conflictAction = 'save-click';
        await conflictSaveButton.click({ timeout: 5000 });
        conflictAction = 'wait-conflict-status';
        await expect(conflictRichDialog.getByRole('alert').filter({ hasText: '版本冲突' }))
          .toContainText('版本冲突', { timeout: 15000 });
      } catch (error) {
        const interactionState = await Promise.race([
          page.evaluate(({ marker }) => {
            const dialog = document.querySelector<HTMLElement>('.blocksuite-resource-dialog');
            if (!dialog) return null;
            const roots: Array<ShadowRoot | HTMLElement> = [dialog];
            const allElements: Element[] = [];
            for (let index = 0; index < roots.length; index += 1) {
              const root = roots[index];
              for (const element of root.querySelectorAll('*')) {
                allElements.push(element);
                if (element.shadowRoot) roots.push(element.shadowRoot);
              }
            }
            const find = (selector: string) => roots.map(root => root.querySelector(selector)).find(Boolean) as HTMLElement | undefined;
            const pageViewport = find('.affine-page-viewport');
            const edgelessViewport = find('.affine-edgeless-viewport');
            const viewport = pageViewport ?? edgelessViewport;
            const paragraphs = allElements.filter(element => element.localName === 'affine-paragraph'
              && element.textContent?.includes('Synthetic rich page round trip')) as HTMLElement[];
            const paragraph = paragraphs[0];
            const paragraphRect = paragraph?.getBoundingClientRect();
            const viewportRect = viewport?.getBoundingClientRect();
            const host = find('.blocksuite-resource-host') as (HTMLElement & { __sbBlockSuiteStore?: any }) | undefined;
            const hostRect = host?.getBoundingClientRect();
            const store = host?.__sbBlockSuiteStore;
            const docMode = store?.spaceDoc?.getMap?.('secondbrain-rich-page-properties')?.get?.('docMode') ?? null;
            let active: Element | null = document.activeElement;
            while (active?.shadowRoot?.activeElement) active = active.shadowRoot.activeElement;
            const note = allElements.find(element => element.localName === 'affine-edgeless-note'
              && element.querySelector('affine-paragraph')?.textContent?.includes('Synthetic rich page round trip')) as (HTMLElement & { model?: any; gfx?: any }) | undefined;
            const noteContainer = note?.querySelector<HTMLElement>('[data-testid="edgeless-note-container"]');
            const noteSelection = note?.gfx?.selection;
            const noteModelId = note?.model?.id;
            const nativeSelection = window.getSelection();
            let anchor: Node | null = nativeSelection?.anchorNode ?? null;
            let selectionInParagraph = false;
            while (anchor) {
              if (anchor === paragraph) { selectionInParagraph = true; break; }
              if (anchor.parentNode) anchor = anchor.parentNode;
              else {
                const root = anchor.getRootNode();
                anchor = root instanceof ShadowRoot ? root.host : null;
              }
            }
            const pointerTarget = (window as Window & { __wp5NotePointerHits?: Array<{ note: boolean; paragraph: boolean; editable: boolean }> }).__wp5NotePointerHits ?? [];
            const markerInStore = Boolean(store?.getBlocksByFlavour('affine:paragraph')?.some(({ model }: any) =>
              model.props.text?.toString().includes(marker)));
            const saveButton = allElements.find(element => element.localName === 'button'
              && element.textContent?.trim() === '保存资源') as HTMLButtonElement | undefined;
            const rectValues = (rect?: DOMRect) => rect ? [Math.round(rect.x), Math.round(rect.y), Math.round(rect.width), Math.round(rect.height)] : [];
            return { view: pageViewport ? 'page' : edgelessViewport ? 'edgeless' : 'none', docMode,
              paragraphCount: paragraphs.length, paragraphRect: rectValues(paragraphRect), hostRect: rectValues(hostRect),
              viewportRect: rectValues(viewportRect),
              paragraphIntersectsViewport: Boolean(paragraphRect && viewportRect && paragraphRect.bottom > viewportRect.top
                && paragraphRect.top < viewportRect.bottom && paragraphRect.right > viewportRect.left
                && paragraphRect.left < viewportRect.right),
              focusedContenteditable: Boolean(active && (active as HTMLElement).isContentEditable), markerInStore,
              saveEnabled: Boolean(saveButton && !saveButton.disabled), pointerTarget,
              noteEditing: noteContainer?.dataset.editing ?? null,
              noteSelected: Boolean(noteModelId && noteSelection?.has?.(noteModelId)),
              selectionEditing: Boolean(noteSelection?.editing), selectionInParagraph,
              editableCount: note?.querySelectorAll('[contenteditable="true"]').length ?? 0 };
          }, { marker: localRichMarker }).catch(() => null),
          new Promise<null>(resolve => setTimeout(() => resolve(null), 1000)),
        ]);
        const compactClickState = (state: NoteClickState | null) => state && [Number(state.selected), Number(state.editing), Number(state.gfxEditing),
          Number(state.caretInParagraph), state.locked === null ? null : Number(state.locked), state.rangeCount, state.anchorOffset];
        console.log('WP5_RESOURCE_CREATE_ERROR', JSON.stringify({ a: conflictAction,
          view: interactionState?.view, mode: interactionState?.docMode,
          hit: structureSummary ? Number(structureSummary.hitTargets[0]) + Number(structureSummary.hitTargets[1]) : 0,
          depth: structureSummary?.hitTargets[2] ?? 0,
          probe: lastPointerProbe && [Number(lastPointerProbe.hitParagraph), Number(lastPointerProbe.hitNote),
            lastPointerProbe.depth, lastPointerProbe.stableSamples, Number(lastPointerProbe.geometryUnchanged), lastPointerProbe.hitTag],
          pointer: interactionState?.pointerTarget.map((hit: { note: boolean; paragraph: boolean; editable: boolean }) => [Number(hit.note), Number(hit.paragraph), Number(hit.editable)]),
          clicks: [compactClickState(firstClickState), compactClickState(secondClickState)],
          state: [Number(Boolean(interactionState?.noteSelected)), Number(Boolean(interactionState?.selectionEditing)),
            Number(interactionState?.selectionInParagraph), interactionState?.editableCount ?? 0] }));
        throw error;
      }
      await expect(conflictRichDialog.getByRole('alert').filter({ hasText: '未自动合并或覆盖' }))
        .toContainText('未自动合并或覆盖');
      const preservedRemote = await page.request.get(`${baseUrl}/api/notes/drafts/${richCreated.path}`);
      expect(preservedRemote.status(), 'wp5_rich_page_conflict_remote_read').toBe(200);
      const preservedRemoteNote = await preservedRemote.json() as { content: string; etag: string };
      expect(preservedRemoteNote.content, 'wp5_rich_page_conflict_remote_marker').toContain(externalRichMarker);
      expect(preservedRemoteNote.content, 'wp5_rich_page_conflict_remote_not_overwritten').not.toContain(localRichMarker);
      const preservedNativeResponse = await page.request.get(`${baseUrl}/api/notes/drafts/${richCreated.path}/blocksuite/resources/${richResourceInfo.resource_id}`);
      expect(preservedNativeResponse.status(), 'wp5_rich_page_conflict_native_read').toBe(200);
      const preservedNative = await preservedNativeResponse.json() as { snapshot: Record<string, unknown> };
      expect(JSON.stringify(preservedNative.snapshot), 'wp5_rich_page_conflict_saved_native_preserved').toContain(richText);
      expect(JSON.stringify(preservedNative.snapshot), 'wp5_rich_page_conflict_no_implicit_write').not.toContain(localRichMarker);
      observed.setWp5Step('rich_page_recovery_copy');
      const recoveryDownloadPromise = page.waitForEvent('download');
      await conflictRichDialog.getByRole('button', { name: '下载资源恢复副本' }).click();
      const recoveryDownload = await recoveryDownloadPromise;
      const recoveryJson = JSON.parse(await readFile(await recoveryDownload.path(), 'utf8')) as { complete: boolean; remoteMarkdown: { content: string } | null; snapshot: unknown; resources: Array<{ resourceId: string; snapshot: unknown }>; blobs: Array<{ id: string; base64: string }> };
      expect(recoveryJson.complete, 'wp5_rich_page_recovery_complete').toBe(true);
      expect(recoveryJson.remoteMarkdown?.content, 'wp5_rich_page_recovery_has_remote').toContain(externalRichMarker);
      expect(JSON.stringify(recoveryJson.snapshot), 'wp5_rich_page_recovery_has_local').toContain(localRichMarker);
      expect(recoveryJson.resources.map(resource => resource.resourceId), 'wp5_rich_page_recovery_nested_resource_closure').toContain(nestedCanvasResourceId);
      expect(recoveryJson.blobs.length, 'wp5_rich_page_recovery_nested_blob_closure').toBeGreaterThan(0);
      expect(recoveryJson.blobs.every(blob => blob.base64.length > 0), 'wp5_rich_page_recovery_blob_bytes').toBe(true);

      observed.setWp5Step('rich_page_explicit_fork');
      const forkNoteCreate = page.waitForResponse(response => response.request().method() === 'POST'
        && new URL(response.url()).pathname === '/api/notes', { timeout: 20000 });
      const forkResourceCreates = [0, 1].map(() => page.waitForResponse(response => response.request().method() === 'POST'
        && new URL(response.url()).pathname.endsWith('/blocksuite/resources'), { timeout: 30000 }));
      const forkResourceUpdates = [0, 1, 2].map(() => page.waitForResponse(response => response.request().method() === 'PUT'
        && new URL(response.url()).pathname.includes('/blocksuite/resources/'), { timeout: 30000 }));
      const forkMarkdownProjection = page.waitForResponse(response => response.request().method() === 'PUT'
        && /^\/api\/notes\/drafts\/[^/]+$/.test(new URL(response.url()).pathname), { timeout: 30000 });
      observed.captureNextBlockSuiteFork();
      await conflictRichDialog.getByRole('button', { name: '另存为新富 Page（保留原件）' }).click();
      const forkedNoteResponse = await forkNoteCreate;
      expect(forkedNoteResponse.status(), 'wp5_rich_page_explicit_fork_note').toBe(200);
      const forkedNote = await forkedNoteResponse.json() as { path: string; content: string };
      expect(forkedNote.path, 'wp5_rich_page_explicit_fork_new_path').not.toBe(richCreated.path);
      for (const response of await Promise.all(forkResourceCreates)) expect(response.status(), 'wp5_rich_page_explicit_fork_resource').toBe(200);
      for (const response of await Promise.all(forkResourceUpdates)) expect(response.status(), 'wp5_rich_page_explicit_fork_resource_remap').toBe(200);
      expect((await forkMarkdownProjection).status(), 'wp5_rich_page_explicit_fork_projection').toBe(200);
      const originalAfterFork = await page.request.get(`${baseUrl}/api/notes/drafts/${richCreated.path}`);
      expect((await originalAfterFork.json() as { content: string }).content, 'wp5_rich_page_original_remains').toContain(externalRichMarker);
      const forkedNoteRead = await page.request.get(`${baseUrl}/api/notes/drafts/${forkedNote.path}`);
      expect(forkedNoteRead.status(), 'wp5_rich_page_fork_readback').toBe(200);
      const forkedMarkdown = (await forkedNoteRead.json() as { content: string }).content;
      expect(forkedMarkdown, 'wp5_rich_page_fork_preserves_local_edit').toContain(localRichMarker);
      expect(forkedMarkdown, 'wp5_rich_page_fork_preserves_external_markdown').toContain(externalRichMarker);
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
      else {
        await page.getByRole('button', { name: 'WP5 focused roundtrip', exact: true }).click();
        await expect(page.locator('.notes-document-heading')).not.toContainText(conflictPath);
        await expect(page.locator('.blocksuite-notes-canvas')).toHaveAttribute('aria-busy', 'false');
      }
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
      wp5_step: observed?.wp5Step ?? 'not_started',
      blocksuite_request_statuses: observed?.blockSuiteRequestStatuses ?? [],
      ...(observed?.wp5CanvasSaveDiagnostic ? { wp5_canvas_save: observed.wp5CanvasSaveDiagnostic } : {}),
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
