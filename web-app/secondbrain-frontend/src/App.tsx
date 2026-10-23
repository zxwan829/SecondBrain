import React, { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchHome, type Home } from './api/home';
import { adaptHome, type DataKind, type ListItem } from './api/home-adapter';
import { DEMO_KPI_DELTAS, DEMO_SOURCE_SPLIT, DEMO_WEATHER } from './demo-data';
import { parseReviewDocument, ReviewMarkdown } from './ReviewMarkdown';
import aiCubeUrl from './assets/ai-cube-user.png';
import hermesOrbUrl from './assets/hermes-planet-user.png';
import todayLandscapeUrl from './assets/today-lake-background.png';
import { UnifiedCaptureComposer } from './UnifiedCaptureComposer';
import { JournalPage } from './JournalPage';
import { TaskPage } from './TaskPage';
import { notesApi } from './api/notes';
import { PromotePreviewPanel } from './PromotePreviewPanel';

const NotesPage = lazy(() => import('./NotesPage').then((module) => ({ default: module.NotesPage })));
const VocabularyPage = lazy(() => import('./VocabularyPage').then((module) => ({ default: module.VocabularyPage })));
const UnifiedInboxPage = lazy(() => import('./UnifiedInboxPage').then((module) => ({ default: module.UnifiedInboxPage })));
const KnowledgePage = lazy(() => import('./KnowledgePage').then((module) => ({ default: module.KnowledgePage })));
const notesFeatureEnabled = () => import.meta.env.VITE_ENABLE_NOTES === 'true';
import { parseRunToolApproval, type RunToolApprovalCard } from './chat-approval';
import { apiFailureLabel, captureFailureLabel, captureStatusLabel, chatFailureLabel, chatStatusLabel, chatToolStageLabel, isImageOcrDescriptionUnavailable, reviewStatusLabel } from './user-messages';
import { isExplicitJournalIntent } from './journal-intent';
import { parseExplicitTaskCommand } from './task-intent';
import { activityTimeLabel, mergeChatTimeline, type ChatActivity, type ChatHistoryMessage } from './chat-activity';
import { citationErrorBundle, parseKnowledgeCitationBundle, readCitationRunLocators, rememberCitationRun,
  type CitationRunLocator, type KnowledgeCitationBundle } from './chat-knowledge-citations';
import { V1ReadOnlyPage } from './V1ReadOnlyPages';
import { V1BriefHealthPage } from './V1BriefHealthPages';
import { CalendarPage } from './CalendarPage';
import { journalInboxAttemptKey, journalInboxFailureLabel, journalInboxReceiptKey,
  makeJournalInboxAttempt, parseJournalInboxAttempt, parseJournalInboxGet,
  parseJournalInboxPostReceipt, parseJournalInboxReceipt,
  type JournalInboxAttempt, type JournalInboxReceipt } from './chat-inbox';
import { inboxEntryErrorLabel, inboxEntryStatusLabel, parseVerifiedInboxEntry } from './inbox-entry';
import { ChatKnowledgeCitations } from './ChatKnowledgeCitations';
import { ChatContextPreview, ChatNaturalCandidates } from './ChatContextPreview';
import { ChatGroundingCandidates } from './ChatGroundingCandidates';
import { fetchContextCandidates, fetchContextPreview, type ContextPreview } from './chat-context-preview';
import { PersonalMemoryPage } from './PersonalMemoryPage';
import { PlanningPanel } from './PlanningPanel';

type Locale = 'zh-CN' | 'en';
type Page = string;
type Copy = typeof messages['zh-CN'];

type ReviewItem = {
  review_path: string;
  review_sha256: string;
  target_filename: string;
  title: string;
  status: string;
  captured_at?: string | null;
  decision?: { status?: string; request_id?: string; error_code?: string } | null;
};
type ReviewDetail = ReviewItem & { content: string };
type CaptureItem = {
  capture_id: string; source_type: string; input_type: string; captured_at: string;
  original_asset: string; raw_path: string; review_path?: string | null; status: string;
  error?: { code: string; message: string } | null; title: string; content_preview?: string;
  display_filename?: string | null; document_title?: string | null;
  source_url?: string | null; derived_source_url?: string | null;
  processor?: { kind?: string; name?: string } | null;
};
type CaptureSummary = {
  capture_id: string;
  source_type: string | null;
  input_type: string | null;
  captured_at: string | null;
  display_filename: string | null;
  status: string;
  error_code: string | null;
  has_review: boolean;
};
type InboxScope = 'capture' | 'drafts' | null;

function capturedAtMillis(value?: string | null): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function sortByCapturedAt<T extends { captured_at?: string | null }>(items: T[], stableKey: (item: T) => string): T[] {
  return items.map((item, index) => ({ item, index, time: capturedAtMillis(item.captured_at) }))
    .sort((a, b) => {
      if (a.time === null && b.time !== null) return 1;
      if (a.time !== null && b.time === null) return -1;
      if (a.time !== null && b.time !== null && a.time !== b.time) return b.time - a.time;
      const keyA = stableKey(a.item);
      const keyB = stableKey(b.item);
      return (keyA < keyB ? -1 : keyA > keyB ? 1 : 0) || a.index - b.index;
    }).map(({ item }) => item);
}

function capturedAtLabel(value: string | null | undefined, locale: Locale): string {
  const time = capturedAtMillis(value);
  if (time === null) return locale === 'en' ? 'Time unknown' : '时间未知';
  if (value && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return new Intl.DateTimeFormat(locale === 'en' ? 'en-US' : 'zh-CN', {
      year: 'numeric', month: 'numeric', day: 'numeric', timeZone: 'UTC',
    }).format(new Date(time));
  }
  return new Date(time).toLocaleString(locale === 'en' ? 'en-US' : 'zh-CN');
}

function inboxEntryIdFromHash(hash: string): string | null {
  const match = /^#capture-([0-9a-f]{32})$/i.exec(hash);
  return match?.[1].toLowerCase() ?? null;
}

function isVisionDescriptionOnly(item: CaptureItem) {
  return isImageOcrDescriptionUnavailable(item);
}

function captureDisplayFilename(item: CaptureItem, locale: Locale) {
  const saved = item.display_filename?.trim();
  if (saved) return saved;
  const rawName = item.raw_path.replace(/\\/g, '/').split('/').pop()?.trim();
  return rawName || (locale === 'en' ? 'Untitled capture' : '未命名素材');
}

export function scrollReviewItemIntoView(container: HTMLElement, target: HTMLElement) {
  const reducedMotion = typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const behavior: ScrollBehavior = reducedMotion ? 'auto' : 'smooth';
  const style = window.getComputedStyle(container);
  const scrollsInternally = /^(auto|scroll|overlay)$/.test(style.overflowY)
    && container.scrollHeight > container.clientHeight;
  if (scrollsInternally) {
    const containerRect = container.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    const top = container.scrollTop + targetRect.top - containerRect.top
      - (container.clientHeight - targetRect.height) / 2;
    if (typeof container.scrollTo === 'function') container.scrollTo({ top, behavior });
    else container.scrollTop = top;
    return;
  }
}

function pageFromPath(path: string, enableNotes: boolean): Page {
  if (path === '/inbox/source') return enableNotes ? 'inbox-source' : 'home';
  const route = navItems.find((item) => 'route' in item && item.route !== '/' &&
    (path === item.route || path.startsWith(`${item.route}/`)));
  if (route?.id === 'notes' && !enableNotes) return 'home';
  if (route) return route.id;
  return 'home';
}

export function singleDraftSourceFromSearch(search: string): { collection: 'drafts'; path: string } | null {
  const params = new URLSearchParams(search);
  if ([...params.keys()].some((key) => key !== 'collection' && key !== 'path')
    || params.getAll('collection').length !== 1 || params.getAll('path').length !== 1
    || params.get('collection') !== 'drafts') return null;
  const path = params.get('path') || '';
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(path)
    ? { collection: 'drafts', path } : null;
}

const messages = {
  'zh-CN': {
    brand: 'SecondBrain', workspace: '你的工作台', subtitle: '一眼掌握当前状态，专注今日最重要的事情',
    home: '首页', chat: '对话', today: '今日', calendar: '日历', inbox: '收件箱', review: '待审核', projects: '项目',
    knowledge: '知识库', brief: '简报', agentHealth: 'Agent 状态', activity: '动态', journal: '日记', notes: '笔记', vocabulary: '标签与类型', memory: '个人记忆', settings: '设置',
    projectOverview: '项目概览', knowledgeOverview: '知识总览', agent: '智能助手', online: '在线',
    todayDescription: '专注当下，记录并推进你的重要事项',
    returnedItems: 'API 返回条目', agentSupport: 'SecondBrain V1', source: '数据来源',
    emptyTitle: '暂无今日记录', emptyDescription: '可以先添加待办，日程功能尚未接入。', create: '新建待办',
    empty: '暂无内容', notConnected: '功能即将上线', notConnectedTitle: '功能即将上线',
    notConnectedDescription: '接入后将为你提供每日重点和重要更新', waiting: '待我处理',
    recentKnowledge: '最近知识', quick: '快捷操作', quickDescription: '常用能力，一键直达',
    capture: '快速收录', newJournal: '新建日记', soon: '即将开放',
    localeLabel: '中文', menu: '打开导航菜单', closeMenu: '关闭导航菜单', demo: 'DEMO', real: 'REAL',
    demoTrend: '趋势示意', demoSources: '来源占比示意', pending: '待审核', apiEntries: 'API 返回条目',
    unavailable: '尚未统计', noTodayData: '今日数据结构暂不可识别', technicalItems: 'Home API 当前返回的是项目目录文件，尚非业务项目列表。',
    viewAll: '查看全部', viewCalendar: '查看完整日历', reviewStatus: '待审核', projectType: '项目条目', knowledgeType: '知识条目',
    statusUnavailable: '状态未提供', demoDelta: '趋势示意',
    briefDescription: '每日为你生成关键信息摘要', activityDescription: '聚合与你协作的动态',
    chatDescription: '与 SecondBrain 对话', reviewDescription: '查看待处理内容',
    captureDescription: '进入对话页后，可切换到收录模式', journalDescription: '记录今日思考',
    personal: 'Personal OS', workspaceType: '个人工作台', settingsSoon: '设置即将开放',
    copyTrace: '复制全部诊断结果', copied: '诊断结果已复制', copyManual: '请在下方文本框中全选复制',
    reviewPageTitle: '待审核', reviewPageDescription: '查看真实 Review 内容与状态。Promote 当前关闭。',
    coreUnlock: '登录', coreLock: '退出登录', corePassphrase: 'SecondBrain 登录口令',
    coreLocked: '请登录以读取真实 Review 内容。',
    coreLoading: '正在读取 Core Review…', coreConnected: '已连接 Core · {count} 条真实 Review · Promote 关闭',
    coreNoItems: '暂无待审核条目', coreSelectItem: '选择条目查看内容', coreStatus: '状态',
    coreNeedHttps: '请使用当前 SecondBrain App 地址。',
    coreNotConfigured: 'SecondBrain App API 尚未配置。',
    coreSessionExpired: '登录会话已失效，请重新登录。', coreConnectionFailed: 'SecondBrain 服务连接失败',
    coreUnlockFailed: '登录失败，请检查口令后重试。', coreLockFailed: '退出登录失败', backHome: '返回首页',
  },
  en: {
    brand: 'SecondBrain', workspace: 'Your workspace', subtitle: 'See your current state and focus on what matters today',
    home: 'Home', chat: 'Chat', today: 'Today', calendar: 'Calendar', inbox: 'Inbox', review: 'Review', projects: 'Projects',
    knowledge: 'Knowledge', brief: 'Brief', agentHealth: 'Agent Health', activity: 'Activity', journal: 'Journal', notes: 'Notes', vocabulary: 'Tags & Types', memory: 'Personal Memory', settings: 'Settings',
    projectOverview: 'Project overview', knowledgeOverview: 'Knowledge overview', agent: 'AI assistant', online: 'Online',
    todayDescription: 'Stay present, capture ideas, and move important things forward.',
    returnedItems: 'API entries', agentSupport: 'SecondBrain V1', source: 'Data source',
    emptyTitle: 'Nothing planned today', emptyDescription: 'Add a task here; calendar event creation is not connected yet.', create: 'New task',
    empty: 'Nothing here yet', notConnected: 'Coming soon', notConnectedTitle: 'Coming soon',
    notConnectedDescription: 'Daily highlights and important updates will appear here once connected', waiting: 'Waiting for me',
    recentKnowledge: 'Recent knowledge', quick: 'Quick actions', quickDescription: 'Your most-used destinations',
    capture: 'Quick capture', newJournal: 'New journal', soon: 'Coming soon',
    localeLabel: 'EN', menu: 'Open navigation', closeMenu: 'Close navigation', demo: 'DEMO', real: 'REAL',
    demoTrend: 'illustrative trend', demoSources: 'illustrative source mix', pending: 'Pending',
    apiEntries: 'API returned entries', unavailable: 'Not available', noTodayData: 'Today data shape is not recognized',
    technicalItems: 'The Home API currently returns project-directory files, not business project records.',
    viewAll: 'View all', viewCalendar: 'View full calendar', reviewStatus: 'Pending review', projectType: 'Project entry', knowledgeType: 'Knowledge entry',
    statusUnavailable: 'Status unavailable', demoDelta: 'illustrative change',
    briefDescription: 'A daily summary of the information that matters', activityDescription: 'A view of the work happening around you',
    chatDescription: 'Talk with SecondBrain', reviewDescription: 'Review items waiting for you',
    captureDescription: 'Open Chat and explicitly switch to capture mode', journalDescription: 'Record a thought from today',
    personal: 'Personal OS', workspaceType: 'Personal workspace', settingsSoon: 'Settings coming soon',
    copyTrace: 'Copy all diagnostic results', copied: 'Diagnostics copied', copyManual: 'Select and copy the text below',
    reviewPageTitle: 'Review', reviewPageDescription: 'Read real Review content and status. Promote is disabled.',
    coreUnlock: 'Sign in', coreLock: 'Sign out', corePassphrase: 'SecondBrain passphrase',
    coreLocked: 'Sign in to load real Review items.',
    coreLoading: 'Loading Core Review…', coreConnected: 'Connected to Core · {count} real Review items · Promote disabled',
    coreNoItems: 'No pending Review items', coreSelectItem: 'Select an item to view its content', coreStatus: 'Status',
    coreNeedHttps: 'Open Review through the configured Dashboard HTTPS address.',
    coreNotConfigured: 'The SecondBrain App API is not configured.',
    coreSessionExpired: 'App session expired. Sign in again.', coreConnectionFailed: 'SecondBrain service connection failed',
    coreUnlockFailed: 'Sign-in failed. Check the password and try again.', coreLockFailed: 'Could not sign out', backHome: 'Back to Home',
  },
} as const;

const navItems = [
  { id: 'home', key: 'home', icon: 'home', section: 'top', route: '/' },
  { id: 'chat', key: 'chat', icon: 'message', section: 'top', route: '/chat' },
  { id: 'today', key: 'today', icon: 'calendar', section: 'work', route: '/today' },
  { id: 'calendar', key: 'calendar', icon: 'calendar', section: 'work', route: '/calendar' },
  { id: 'inbox', key: 'inbox', icon: 'inbox', section: 'work', route: '/inbox' },
  { id: 'review', key: 'review', icon: 'check', section: 'work', route: '/review' },
  { id: 'projects', key: 'projects', icon: 'folder', section: 'library', route: '/projects' },
  { id: 'knowledge', key: 'knowledge', icon: 'book', section: 'library', route: '/knowledge' },
  { id: 'brief', key: 'brief', icon: 'file', section: 'library', route: '/brief' },
  { id: 'agent-health', key: 'agentHealth', icon: 'brain', section: 'library', route: '/agent-health' },
  { id: 'activity', key: 'activity', icon: 'activity', section: 'library', route: '/activity' },
  { id: 'journal', key: 'journal', icon: 'journal', section: 'library', route: '/journal' },
  { id: 'notes', key: 'notes', icon: 'notes', section: 'library', route: '/notes' },
  { id: 'vocabulary', key: 'vocabulary', icon: 'check', section: 'library', route: '/vocabulary' },
  { id: 'memory', key: 'memory', icon: 'brain', section: 'library', route: '/memory' },
  { id: 'settings', key: 'settings', icon: 'settings', section: 'bottom', route: '/settings' },
] as const;

const anchorByNav: Record<string, string> = {
  home: 'top', today: 'today', calendar: 'calendar', inbox: 'waiting', review: 'waiting',
  projects: 'projects', knowledge: 'knowledge', brief: 'brief', 'agent-health': 'agent-health', activity: 'activity',
};

export function App() {
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const [password, setPassword] = useState('');
  const [authError, setAuthError] = useState('');
  const [authBusy, setAuthBusy] = useState(false);

  const checkSession = async () => {
    try {
      const response = await fetch('/api/auth/session', { credentials: 'same-origin' });
      setAuthenticated(response.ok);
      if (!response.ok && response.status !== 401) setAuthError('SecondBrain App API 暂不可用。');
    } catch {
      setAuthenticated(false);
      setAuthError('无法连接 SecondBrain App API。');
    }
  };
  useEffect(() => { void checkSession(); }, []);

  const login = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAuthBusy(true); setAuthError('');
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      });
      if (!response.ok) throw new Error(loginFailureMessage(response.status));
      setPassword(''); setAuthenticated(true);
    } catch (error) {
      setAuthError(error instanceof Error ? apiFailureLabel(error.message, 0, 'zh-CN', 'general') : '登录请求未成功，请稍后重试。');
    } finally { setAuthBusy(false); }
  };

  if (authenticated === null) return <div className="app-login"><p>SecondBrain</p><span>正在检查登录状态…</span></div>;
  if (!authenticated) return <main className="app-login"><div className="app-login-card"><span className="brand-mark"><Icon name="brain" size={21} /></span><p className="eyebrow">SECONDBRAIN</p><h1>欢迎回来</h1><p>登录后进入你的个人工作台。</p><form onSubmit={login}><label htmlFor="app-password">{messages['zh-CN'].corePassphrase}</label><input id="app-password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required /><button type="submit" disabled={authBusy || !password}>{authBusy ? '正在登录…' : '登录'}</button></form>{authError && <p role="alert" className="auth-error">{authError}</p>}</div></main>;
  return <WorkspaceApp onLogout={async () => { await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: '{}' }); setAuthenticated(false); }} />;
}

type BlankChatState = { sessionIds: string[]; selectedSessionId: string };
const blankChatStateKey = 'secondbrain.chat.blank.sessions';

function readBlankChatState(): BlankChatState {
  try {
    const value = JSON.parse(sessionStorage.getItem(blankChatStateKey) ?? 'null') as Partial<BlankChatState> | null;
    const sessionIds = Array.isArray(value?.sessionIds)
      ? [...new Set(value.sessionIds.filter((id): id is string => typeof id === 'string' && Boolean(id.trim())))] : [];
    const selectedSessionId = typeof value?.selectedSessionId === 'string' && sessionIds.includes(value.selectedSessionId)
      ? value.selectedSessionId : '';
    return { sessionIds, selectedSessionId };
  } catch { return { sessionIds: [], selectedSessionId: '' }; }
}

function blankChatSessionList(sessionIds: string[], locale: Locale): ChatSession[] {
  return sessionIds.map((id, index) => ({ id, title: locale === 'en' ? `Test session ${index + 1}` : `合成会话 ${index + 1}` }));
}

function loginFailureMessage(status: number): string {
  if (status === 401) return '登录未通过 App 凭据校验（HTTP 401）。';
  if (status === 403) return '请求来源校验失败（HTTP 403）。请使用配置的 SecondBrain HTTPS 地址。';
  if (status === 429) return '登录尝试过多（HTTP 429），请稍后再试。';
  if (status >= 500) return `SecondBrain App 服务异常（HTTP ${status}），请稍后重试。`;
  return `登录请求被拒绝（HTTP ${status}）。`;
}

function WorkspaceApp({ onLogout }: { onLogout: () => void }) {
  const enableNotes = notesFeatureEnabled();
  const [locale, setLocale] = useState<Locale>(() => localStorage.getItem('secondbrain.locale') === 'en' ? 'en' : 'zh-CN');
  const [home, setHome] = useState<Home | null>(null);
  const [error, setError] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [page, setPage] = useState<Page>(() => pageFromPath(location.pathname, enableNotes));
  const pageRef = useRef(page);
  pageRef.current = page;
  const previousHomeEffectPage = useRef(page);
  const skippedHomeEffectPage = useRef<Page | null>(null);
  const homeRequestStarted = useRef(false);
  const [routeRevision, setRouteRevision] = useState(0);
  const [inboxScope, setInboxScope] = useState<InboxScope>(null);
  const [notesAvailable, setNotesAvailable] = useState(false);
  const [notesGateChecked, setNotesGateChecked] = useState(!enableNotes);
  const isSingleSourceInboxPath = location.pathname === '/inbox/source';
  const isInboxRoute = location.pathname === '/inbox' || location.pathname.startsWith('/inbox/');
  const isKnowledgePage = page === 'knowledge';
  const isHomePage = page === 'home';
  const singleSource = isSingleSourceInboxPath ? singleDraftSourceFromSearch(location.search) : null;
  const notesNavigationGuard = useRef<(() => boolean) | null>(null);
  const navigationIndex = useRef(typeof history.state?.sbNavigationIndex === 'number' ? history.state.sbNavigationIndex as number : 0);
  const t = messages[locale];

  useEffect(() => {
    localStorage.setItem('secondbrain.locale', locale);
    document.documentElement.lang = locale;
  }, [locale]);
  useEffect(() => {
    // Scoped pages must not trigger the broad Home aggregate, which also reads
    // unrelated Review and Knowledge content.
    const previousPage = previousHomeEffectPage.current;
    const skippedPage = skippedHomeEffectPage.current;
    if (skippedPage && skippedPage !== page) skippedHomeEffectPage.current = null;
    previousHomeEffectPage.current = page;
    // The aggregate endpoint is Home data, so direct routes such as Chat and
    // Review must not fetch it merely because the authenticated shell mounted.
    if (!isHomePage) return;
    if (isKnowledgePage || location.pathname === '/inbox/source' || isInboxRoute) return;
    // Keep this transition guard stable across StrictMode's effect replay. The
    // previous-page ref is updated above, so relying on it alone would allow
    // the replay to issue Home immediately after leaving Inbox.
    if (skippedPage === page) return;
    const leftKnowledgeForAnotherPage = previousPage === 'knowledge' && !isHomePage;
    if (leftKnowledgeForAnotherPage) return;
    const returnedFromInbox = (previousPage === 'inbox' || previousPage === 'inbox-source') && !isInboxRoute;
    if (returnedFromInbox) {
      skippedHomeEffectPage.current = page;
      return;
    }
    if (homeRequestStarted.current && previousPage !== 'knowledge') return;
    let mounted = true;
    let completed = false;
    homeRequestStarted.current = true;
    fetchHome().then((data) => { completed = true; if (mounted) setHome(data); }).catch(() => { completed = true; if (mounted) setError(true); });
    return () => { mounted = false; if (!completed) homeRequestStarted.current = false; };
  }, [isKnowledgePage, isHomePage, isSingleSourceInboxPath, isInboxRoute]);
  const registerNotesNavigationGuard = useCallback((guard: (() => boolean) | null) => {
    notesNavigationGuard.current = guard;
  }, []);
  const pushAppPath = useCallback((path: string) => {
    const nextIndex = navigationIndex.current + 1;
    history.pushState({ ...history.state, sbNavigationIndex: nextIndex }, '', path);
    navigationIndex.current = nextIndex;
  }, []);

  useEffect(() => {
    if (typeof history.state?.sbNavigationIndex !== 'number') {
      history.replaceState({ ...history.state, sbNavigationIndex: navigationIndex.current }, '', location.href);
    }
  }, []);
  useEffect(() => {
    const onPop = (event: PopStateEvent) => {
      const isNotesPath = location.pathname === '/notes' || location.pathname.startsWith('/notes/') || location.pathname === '/inbox/source';
      if (pageRef.current === 'notes' && !isNotesPath && notesNavigationGuard.current && !notesNavigationGuard.current()) {
        const targetIndex = typeof event.state?.sbNavigationIndex === 'number' ? event.state.sbNavigationIndex as number : null;
        const direction = targetIndex === null ? -1 : Math.sign(targetIndex - navigationIndex.current);
        history.go(direction > 0 ? -1 : 1);
        return;
      }
      if (typeof event.state?.sbNavigationIndex === 'number') navigationIndex.current = event.state.sbNavigationIndex as number;
      setInboxScope(null);
      setPage(pageFromPath(location.pathname, enableNotes)); setRouteRevision((value) => value + 1);
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, [enableNotes]);

  useEffect(() => {
    if (!enableNotes) return;
    // Notes availability is checked only after an explicit Notes or single-source
    // Inbox route. The authenticated shell must not read the Notes collection
    // just to render unrelated pages or discover whether the nav item is usable.
    if (page !== 'notes' && !isSingleSourceInboxPath) return;
    if (isInboxRoute && !isSingleSourceInboxPath) return;
    if (isSingleSourceInboxPath) {
      // The exact-source Notes read is the Core permission check for this isolated route.
      // Do not fetch the Notes collections endpoint as a route-level preflight.
      setNotesAvailable(true); setNotesGateChecked(true);
      return;
    }
    let active = true;
    void notesApi.collections().then(() => {
      if (active) { setNotesAvailable(true); setNotesGateChecked(true); }
    }).catch(() => {
      if (active) { setNotesAvailable(false); setNotesGateChecked(true); }
    });
    return () => { active = false; };
  }, [enableNotes, isSingleSourceInboxPath, isInboxRoute, page]);

  useEffect(() => {
    const isNotesPath = location.pathname === '/notes' || location.pathname.startsWith('/notes/') || location.pathname === '/inbox/source';
    if (isNotesPath && (!enableNotes || (notesGateChecked && !notesAvailable))) {
      history.replaceState(history.state, '', '/');
      setPage('home');
      setRouteRevision((value) => value + 1);
    }
  }, [enableNotes, notesAvailable, notesGateChecked, routeRevision]);

  const view = useMemo(() => adaptHome(home), [home]);
  const changeLocale = () => setLocale((current) => current === 'zh-CN' ? 'en' : 'zh-CN');
  const navigate = (item: string) => {
    if (pageRef.current === 'notes' && item !== 'notes' && notesNavigationGuard.current && !notesNavigationGuard.current()) return;
    const destination = navItems.find((entry) => entry.id === item);
    if (destination && 'route' in destination && destination.route) {
      if (location.pathname !== destination.route || location.search) pushAppPath(destination.route);
      if (destination.id === 'inbox') setInboxScope(null);
      setPage(destination.id); setRouteRevision((value) => value + 1); setMenuOpen(false); return;
    }
    if (page !== 'home') {
        pushAppPath('/'); setPage('home');
    }
    const target = document.getElementById(anchorByNav[item] ?? 'top');
    window.requestAnimationFrame(() => target?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
    setMenuOpen(false);
  };

  const nav = (mobile = false) => (
    <nav className={mobile ? 'nav-list mobile-nav-list' : 'nav-list'} aria-label={t.brand}>
      {(['top', 'work', 'library', 'bottom'] as const).map((section) => (
        <div className={`nav-section nav-section-${section}`} key={section}>
          {navItems.filter((item) => item.section === section && (item.id !== 'notes' || (enableNotes && (!notesGateChecked || notesAvailable)))).map((item) => (
            <button
              type="button"
              key={item.id}
              className={`nav-item ${(item.id === page || (page === 'home' && item.id === 'home')) ? 'is-active' : ''} ${'soon' in item && item.soon ? 'is-soon' : ''}`}
              aria-current={item.id === page ? 'page' : undefined}
              aria-disabled={'soon' in item && item.soon ? 'true' : undefined}
              onClick={() => { if ('soon' in item && item.soon) return; navigate(item.id); }}
            >
              <Icon name={item.icon} size={18} />
              <span className="nav-label">{t[item.key]}</span>
              {'soon' in item && item.soon === true && <span className="nav-soon">{t.soon}</span>}
            </button>
          ))}
        </div>
      ))}
    </nav>
  );

  return (
    <main className="sb-app v3-shell" id="top">
      {menuOpen && <button type="button" className="mobile-scrim" aria-label={t.closeMenu} onClick={() => setMenuOpen(false)} />}
      <aside className={`sidebar ${menuOpen ? 'is-open' : ''}`} aria-label={t.brand}>
        <div className="brand">
          <span className="brand-mark"><Icon name="brain" size={21} /></span>
          <span className="brand-name">{t.brand}</span>
          <button className="sidebar-locale" type="button" onClick={changeLocale}>{t.localeLabel}</button>
        </div>
        {nav()}
        <div className="sidebar-profile">
          <span className="profile-avatar">SB</span>
          <span className="profile-copy"><strong>{t.personal}</strong><small>{t.workspaceType}</small></span>
          <Icon name="chevrons" size={16} />
        </div>
      </aside>

      <section className={`dashboard ${page === 'review' ? 'is-review-page' : ''}`}>
        <div className="mobile-topbar">
          <button type="button" className="mobile-menu-button" aria-label={menuOpen ? t.closeMenu : t.menu} aria-expanded={menuOpen} onClick={() => setMenuOpen((open) => !open)}><Icon name={menuOpen ? 'close' : 'menu'} size={20} /></button>
          <span className="mobile-brand-mark"><Icon name="brain" size={19} /></span>
          <strong>{t.brand}</strong>
          <button type="button" className="locale-button" onClick={changeLocale}>{t.localeLabel}</button>
        </div>

        {page === 'brief' || page === 'agent-health' ? <V1BriefHealthPage page={page} locale={locale} />
          : page === 'projects' || page === 'activity' ? <V1ReadOnlyPage page={page} locale={locale} />
          : page === 'calendar' ? <CalendarPage locale={locale} />
          : page === 'knowledge' ? <Suspense fallback={<div role="status">{locale === 'en' ? 'Loading Knowledge…' : '正在加载知识库…'}</div>}><KnowledgePage locale={locale} /></Suspense>
          : page === 'vocabulary' ? <Suspense fallback={<div role="status">{locale === 'en' ? 'Loading vocabulary…' : '正在加载词库…'}</div>}><VocabularyPage locale={locale} /></Suspense>
          : page === 'journal' ? <JournalPage /> : page === 'notes' ? (!notesGateChecked
          ? <div role="status">{locale === 'en' ? 'Checking Notes availability…' : '正在检查笔记状态…'}</div>
          : enableNotes && notesAvailable
          ? <Suspense fallback={<div role="status">{locale === 'en' ? 'Loading Notes…' : '正在加载笔记…'}</div>}><NotesPage onRegisterNavigationGuard={registerNotesNavigationGuard} onOpenInboxSource={(collection, path) => {
            const query = new URLSearchParams({ collection, path });
            pushAppPath(`/inbox/source?${query}`); setPage('inbox-source'); setRouteRevision((value) => value + 1);
          }} /></Suspense>
          : <div role="status">{locale === 'en' ? 'Notes is unavailable.' : '笔记功能当前不可用。'}</div>)
          : page === 'inbox-source' ? (enableNotes && (notesAvailable || isSingleSourceInboxPath)
            ? <Suspense fallback={<div role="status">{locale === 'en' ? 'Loading selected Draft…' : '正在加载所选 Draft…'}</div>}><UnifiedInboxPage key={singleSource ? `${singleSource.collection}:${singleSource.path}` : 'invalid-source'} locale={locale} onReview={(path) => { const query = new URLSearchParams({ review_path: path }); pushAppPath(`/review?${query}`); setPage('review'); setRouteRevision((value) => value + 1); }} showSyntheticCaptureDemo={false} singleSourceMode singleSource={singleSource} /></Suspense>
            : <div role="status">{locale === 'en' ? 'Notes is unavailable.' : '笔记功能当前不可用。'}</div>)
          : page === 'today' ? <TaskPage locale={locale} /> : page === 'home' ? <>
        <header className="workspace-header">
          <div className="workspace-heading">
            <p className="eyebrow">{t.brand.toUpperCase()} <span>/</span> {t.home.toUpperCase()}</p>
            <h1>{t.workspace}</h1>
            <p className="workspace-subtitle">{t.subtitle}</p>
          </div>
          <div className="header-actions">
            <ClockWeather locale={locale} />
            <span className={`header-agent ${view.agentStatus ? 'is-real' : 'is-unavailable'}`}><i />{view.agentStatus ? localizeStatus(view.agentStatus, locale) : t.unavailable}</span>
            <button type="button" className="locale-button desktop-locale" onClick={changeLocale}>{t.localeLabel}<Icon name="chevron" size={13} /></button>
            <button type="button" className="settings-button" onClick={onLogout} title={t.coreLock} aria-label={t.coreLock}><Icon name="settings" size={17} /></button>
          </div>
        </header>

        {error && <div className="error-state" role="alert">{locale === 'en' ? 'Home data could not be loaded. Try reloading the page.' : '暂时无法加载 Home 数据，请刷新页面重试。'}</div>}

        <section className="overview-visual" aria-label={t.projectOverview}>
          <KpiCard icon="folder" tone="blue" title={t.projectOverview} value={view.projectSource === 'UNAVAILABLE' ? '—' : String(view.projectItems.length)} detail={view.projectSource === 'REAL' ? t.returnedItems : t.unavailable} source={view.projectSource} chart="bars" locale={locale} demoDelta={view.source === 'REAL' ? DEMO_KPI_DELTAS.projects : undefined} />
          <KpiCard icon="book" tone="violet" title={t.knowledgeOverview} value={view.source === 'UNAVAILABLE' ? t.unavailable : String(view.knowledgeItems.length)} detail={t.returnedItems} source={view.source} chart="line" locale={locale} demoDelta={view.source === 'REAL' ? DEMO_KPI_DELTAS.knowledge : undefined} />
          <KpiCard icon="brain" tone="teal" title={t.agent} value={view.agentStatus ? localizeStatus(view.agentStatus, locale) : '—'} detail={view.agentStatus ? 'Hermes · REAL' : t.unavailable} source={view.agentSource} chart="orb" locale={locale} />
          <Donut locale={locale} />
        </section>

        <section className="primary-grid" aria-label={t.today}>
          <TodayCard state={view.today} locale={locale} onViewCalendar={() => navigate('calendar')} onCreateTask={() => navigate('today')} />
          <ReviewCard title={t.waiting} items={view.review} pendingCount={view.pendingCount} source={view.reviewSource} locale={locale} />
        </section>

        <section className="secondary-grid" aria-label={t.projects}>
          <ListCard id="projects" title={t.projects} items={view.projectItems} kind="project" source={view.projectSource} locale={locale} />
          <ListCard id="knowledge" title={t.recentKnowledge} items={view.knowledgeItems} kind="knowledge" source={view.knowledgeSource} locale={locale} />
          <AgentCard status={view.agentStatus} locale={locale} />
        </section>

        <section className="info-grid">
          <ConnectedPlaceholder id="brief" title={t.brief} description={t.briefDescription} locale={locale} icon="file" />
          <ConnectedPlaceholder id="activity" title={t.activity} description={t.activityDescription} locale={locale} icon="activity" />
        </section>

        <section className="quick-strip" aria-labelledby="quick-title">
          <div className="quick-heading"><div><h2 id="quick-title">{t.quick}</h2><p>{t.quickDescription}</p></div><Icon name="bolt" size={21} /></div>
          <div className="action-row">
            <ActionCard icon="message" tone="action-blue" title={t.chat} description={t.chatDescription} onClick={() => navigate('chat')} />
            <ActionCard icon="check" tone="action-violet" title={t.review} description={t.reviewDescription} onClick={() => navigate('review')} />
            <ActionCard icon="capture" tone="action-teal" title={t.capture} description={t.captureDescription} onClick={() => navigate('chat')} />
            <ActionCard icon="journal" tone="action-slate" title={t.newJournal} description={t.journalDescription} soon={t.soon} />
          </div>
        </section>

        </> : page === 'review' ? <ReviewPage key={routeRevision} locale={locale} initialReviewPath={new URLSearchParams(location.search).get('review_path')}
          expectedReviewSha256={new URLSearchParams(location.search).get('source_sha256')} pushHistory={pushAppPath} onBack={() => navigate('home')} />
          : page === 'inbox' ? inboxEntryIdFromHash(location.hash)
            ? <InboxEntryStatusPage key={inboxEntryIdFromHash(location.hash)} locale={locale} inboxId={inboxEntryIdFromHash(location.hash)!}
              onBack={() => { history.replaceState(history.state, '', '/inbox'); setInboxScope(null); setRouteRevision((value) => value + 1); }}
              onReview={(path, sha256) => { const query = new URLSearchParams({ review_path: path, source_sha256: sha256 }); pushAppPath(`/review?${query}`); setPage('review'); setRouteRevision((value) => value + 1); }} />
            : <InboxScopePage locale={locale} scope={inboxScope} onScopeChange={setInboxScope}
            onReview={(path) => { const query = new URLSearchParams({ review_path: path }); pushAppPath(`/review?${query}`); setPage('review'); setRouteRevision((value) => value + 1); }}
            onOpenDraft={(path) => { const query = new URLSearchParams({ collection: 'drafts', path }); pushAppPath(`/inbox/source?${query}`); setPage('inbox-source'); setRouteRevision((value) => value + 1); }} />
          : page === 'chat' ? <ChatPage locale={locale} blankMode={location.pathname === '/chat/blank'} onGoInbox={() => navigate('inbox')}
            onGoJournal={() => navigate('journal')} onGoToday={() => navigate('today')} />
            : page === 'settings' ? <AutomationSettingsPage locale={locale} />
            : page === 'memory' ? <PersonalMemoryPage key={routeRevision} locale={locale} />
            : <div className="chat-empty" role="status">{locale === 'en' ? 'This Personal OS module is not connected yet.' : '此 Personal OS 模块尚未接入。'}</div>}
      </section>
    </main>
  );
}

export function InboxEntryStatusPage({ locale, inboxId, onBack, onReview }: {
  locale: Locale; inboxId: string; onBack: () => void; onReview: (path: string, sha256: string) => void;
}) {
  const en = locale === 'en';
  const [entry, setEntry] = useState<ReturnType<typeof parseVerifiedInboxEntry>>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true); setEntry(null); setError('');
    void fetch(`/api/inbox/entries/${encodeURIComponent(inboxId)}`, { credentials: 'same-origin', signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw Object.assign(new Error('inbox_status_unavailable'), { status: response.status });
        const payload = await response.json().catch(() => null);
        const verified = parseVerifiedInboxEntry(payload, inboxId);
        if (!verified) throw Object.assign(new Error('inbox_status_unverified'), { status: 0 });
        if (active) setEntry(verified);
      })
      .catch((cause) => {
        if (!active || controller.signal.aborted) return;
        const status = typeof cause?.status === 'number' && cause.status > 0 ? cause.status : null;
        setError(inboxEntryErrorLabel(status, en));
      })
      .finally(() => { if (active && !controller.signal.aborted) setLoading(false); });
    return () => { active = false; controller.abort(); };
  }, [en, inboxId, revision]);

  return <section className="capture-page" aria-labelledby="inbox-entry-title">
    <header className="capture-page-header"><div><p className="eyebrow">SECONDBRAIN <span>/</span> INBOX</p>
      <h1 id="inbox-entry-title">{en ? 'Inbox entry status' : 'Inbox 条目状态'}</h1>
      <p className="workspace-subtitle">{en ? 'Only the linked entry status is requested. Original content is not loaded here.' : '仅查询此链接对应条目的状态；此页不会读取原文。'}</p></div>
      <button type="button" className="capture-secondary" onClick={onBack}>{en ? 'Back to Inbox' : '返回收件箱'}</button></header>
    {loading && <p role="status">{en ? 'Checking status for this exact Inbox ID…' : '正在核对该 Inbox ID 对应的状态…'}</p>}
    {error && <div role="alert" className="capture-alert"><p>{error}</p>
      <button type="button" onClick={() => setRevision((value) => value + 1)}>{en ? 'Retry status check' : '重试状态核验'}</button></div>}
    {entry && <article className="inbox-item" aria-label={en ? 'Inbox status' : 'Inbox 状态'}>
      <div className="inbox-item-main"><div><h2>{en ? 'Core Inbox status checked' : 'Core Inbox 状态已核对'}</h2>
        <p>{en ? 'Intent' : '收录意图'}: {entry.intent} · {en ? 'Source' : '来源'}: {entry.sourceChannel}</p>
        <p>{en ? 'Captured' : '收录时间'}: {capturedAtLabel(entry.capturedAt, locale)}</p></div>
        <span className={`capture-status status-${entry.status}`}>{inboxEntryStatusLabel(entry.status, en)}</span></div>
      <p role="status">{en ? 'This is an Inbox state only. It does not mean a Journal, Knowledge, or Project write has completed.' : '这只表示 Inbox 状态，不代表 Journal、Knowledge 或 Project 已完成写入。'}</p>
      {entry.reviewPath && entry.reviewSha256
        ? <button type="button" className="capture-primary" onClick={() => onReview(entry.reviewPath!, entry.reviewSha256!)}>{en ? 'Open Review source with matching version' : '打开版本匹配的 Review 来源'}</button>
        : <p role="status">{en ? 'No version-matched Review source link is available.' : '当前没有提供版本匹配的 Review 来源链接。'}</p>}
      <button type="button" className="capture-secondary" onClick={() => setRevision((value) => value + 1)}>{en ? 'Refresh status' : '刷新状态'}</button>
    </article>}
  </section>;
}

function InboxScopePage({ locale, scope, onScopeChange, onReview, onOpenDraft }: { locale: Locale; scope: InboxScope; onScopeChange: (scope: InboxScope) => void; onReview: (reviewPath: string) => void; onOpenDraft: (path: string) => void }) {
  const en = locale === 'en';
  if (scope === 'capture') return <section className="capture-page" aria-labelledby="inbox-title">
    <header className="capture-page-header"><div><p className="eyebrow">SECONDBRAIN <span>/</span> INBOX</p><h1 id="inbox-title">{en ? 'Capture pending' : 'Capture 待处理'}</h1></div><button type="button" className="capture-secondary" onClick={() => onScopeChange(null)}>{en ? 'Change scope' : '更换范围'}</button></header>
    <ScopedCaptureInbox locale={locale} onReview={onReview} />
  </section>;
  if (scope === 'drafts') return <section className="capture-page" aria-labelledby="inbox-title">
    <header className="capture-page-header"><div><p className="eyebrow">SECONDBRAIN <span>/</span> INBOX</p><h1 id="inbox-title">{en ? 'Notes Drafts' : 'Notes Draft 草稿'}</h1></div><button type="button" className="capture-secondary" onClick={() => onScopeChange(null)}>{en ? 'Change scope' : '更换范围'}</button></header>
    <InboxDraftList locale={locale} onOpenDraft={onOpenDraft} />
  </section>;
  return <section className="capture-page" aria-labelledby="inbox-title">
    <header className="capture-page-header"><div><p className="eyebrow">SECONDBRAIN <span>/</span> INBOX</p><h1 id="inbox-title">{en ? 'Choose an Inbox scope' : '选择收件箱范围'}</h1><p className="workspace-subtitle">{en ? 'Nothing is loaded until you choose a source.' : '选择来源前不会加载任何收件箱内容。'}</p></div></header>
    <div className="action-row" role="group" aria-label={en ? 'Inbox source scope' : '收件箱来源范围'}>
      <button type="button" className="action-card action-blue is-interactive" onClick={() => onScopeChange('capture')}><strong>{en ? 'Capture pending' : 'Capture 待处理'}</strong><span>{en ? 'Review captured source metadata' : '查看已收录来源的状态摘要'}</span></button>
      <button type="button" className="action-card action-violet is-interactive" onClick={() => onScopeChange('drafts')}><strong>{en ? 'Notes Drafts' : 'Notes Draft 草稿'}</strong><span>{en ? 'Choose a Draft to review' : '选择一篇草稿进行审核'}</span></button>
    </div>
  </section>;
}

function ScopedCaptureInbox({ locale, onReview }: { locale: Locale; onReview: (reviewPath: string) => void }) {
  const en = locale === 'en';
  const [items, setItems] = useState<CaptureSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [detail, setDetail] = useState<CaptureItem | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const [retrying, setRetrying] = useState(false);
  const [organizerStatusRequested, setOrganizerStatusRequested] = useState(false);
  const [organizeReason, setOrganizeReason] = useState('');
  const [organizeAvailable, setOrganizeAvailable] = useState(false);
  const [organizeBusy, setOrganizeBusy] = useState(false);
  const [organizeMessage, setOrganizeMessage] = useState('');
  const scopeController = useRef<AbortController | null>(null);
  const detailController = useRef<AbortController | null>(null);
  const detailRevision = useRef(0);
  const selectedCaptureId = useRef<string | null>(null);
  const summaryRevision = useRef(0);
  const organizerController = useRef<AbortController | null>(null);

  const loadSummary = useCallback(async (signal?: AbortSignal) => {
    const response = await fetch('/api/inbox/summary?limit=100', { credentials: 'same-origin', signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json() as { items?: CaptureSummary[] };
    return Array.isArray(payload.items) ? payload.items.filter((item): item is CaptureSummary => Boolean(item)
      && typeof item.capture_id === 'string' && /^[0-9a-f]{32}$/.test(item.capture_id)) : [];
  }, []);
  const refreshSummary = useCallback(async () => {
    const signal = scopeController.current?.signal;
    if (!signal || signal.aborted) return;
    const revision = ++summaryRevision.current;
    try {
      const nextItems = await loadSummary(signal);
      if (!signal.aborted && revision === summaryRevision.current) { setItems(nextItems); setError(''); }
    } catch (cause) {
      if (!signal.aborted && revision === summaryRevision.current) setError(cause instanceof Error ? cause.message : (en ? 'Inbox summary is unavailable.' : '收件箱摘要暂不可用。'));
    } finally {
      if (!signal.aborted && revision === summaryRevision.current) setLoading(false);
    }
  }, [en, loadSummary]);

  useEffect(() => {
    const controller = new AbortController();
    scopeController.current = controller;
    void refreshSummary();
    const refresh = () => { void refreshSummary(); };
    const timer = window.setInterval(refresh, 5000);
    window.addEventListener('sb-inbox-refresh', refresh);
    return () => {
      controller.abort();
      summaryRevision.current += 1;
      detailRevision.current += 1;
      selectedCaptureId.current = null;
      detailController.current?.abort();
      organizerController.current?.abort();
      window.clearInterval(timer);
      window.removeEventListener('sb-inbox-refresh', refresh);
    };
  }, [refreshSummary]);

  const refreshOrganizerStatus = useCallback(async () => {
    const signal = organizerController.current?.signal;
    if (!signal || signal.aborted) return;
    try {
      const response = await fetch('/api/automation/organize/status', { credentials: 'same-origin', signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const value = await response.json() as { blocked_reason?: unknown; execution_available?: unknown };
      if (signal.aborted) return;
      setOrganizeReason(typeof value.blocked_reason === 'string' ? value.blocked_reason : '');
      setOrganizeAvailable(value.execution_available === true);
    } catch (cause) {
      if (!signal.aborted) {
        setOrganizeAvailable(false);
        setOrganizeReason(cause instanceof Error ? cause.message : (en ? 'The organization runner is unavailable.' : '自动整理执行器当前不可用。'));
      }
    }
  }, [en]);

  useEffect(() => {
    if (!organizerStatusRequested) return;
    const controller = new AbortController();
    organizerController.current = controller;
    void refreshOrganizerStatus();
    const refresh = () => { void refreshOrganizerStatus(); };
    const timer = window.setInterval(refresh, 5000);
    window.addEventListener('sb-inbox-refresh', refresh);
    return () => {
      controller.abort();
      window.clearInterval(timer);
      window.removeEventListener('sb-inbox-refresh', refresh);
    };
  }, [organizerStatusRequested, refreshOrganizerStatus]);

  const requestOrganizerStatus = () => {
    setOrganizeMessage('');
    setOrganizerStatusRequested(true);
  };

  const organizeNow = async () => {
    if (!organizeAvailable || organizeBusy) return;
    setOrganizeBusy(true); setOrganizeMessage('');
    try {
      const response = await fetch('/api/automation/organize/run', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      const value = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error('organizer_run_failed');
      const label = value.status === 'no_new_messages' ? (en ? 'No new messages to organize.' : '没有新增对话，无需整理。')
        : value.status === 'already_running' ? (en ? 'An organization job is already running.' : '已有整理任务正在运行。')
          : (en ? `Organization finished; ${Number(value.draft_count ?? 0)} drafts added.` : `整理完成，新增 ${Number(value.draft_count ?? 0)} 条 Review 草稿。`);
      setOrganizeMessage(label);
      window.dispatchEvent(new Event('sb-inbox-refresh'));
    } catch {
      setOrganizeMessage(en ? 'Organization could not be completed; check its status and try again.' : '整理未能完成，请查看运行状态后再试。');
    } finally { setOrganizeBusy(false); }
  };

  const openCapture = async (captureId: string) => {
    detailController.current?.abort();
    const controller = new AbortController();
    detailController.current = controller;
    const revision = ++detailRevision.current;
    selectedCaptureId.current = captureId;
    setDetail(null); setDetailError(''); setDetailLoading(true);
    setRetrying(false);
    try {
      const response = await fetch(`/api/capture/${encodeURIComponent(captureId)}`, { credentials: 'same-origin', signal: controller.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const value = await response.json() as CaptureItem;
      if (controller.signal.aborted || revision !== detailRevision.current) return;
      if (value.capture_id !== captureId) throw new Error('Capture identity mismatch');
      setDetail(value);
      if (previewKind(value.raw_path) === 'text') {
        const preview = await fetch(`/api/inbox/${encodeURIComponent(captureId)}/preview`, { credentials: 'same-origin', signal: controller.signal });
        if (!preview.ok) throw new Error(`HTTP ${preview.status}`);
        const content = await preview.text();
        if (!controller.signal.aborted && revision === detailRevision.current) setDetail((current) => current?.capture_id === captureId ? { ...current, content_preview: content } : current);
      }
    } catch (cause) {
      if (!controller.signal.aborted && revision === detailRevision.current) setDetailError(cause instanceof Error ? cause.message : (en ? 'Selected Capture could not be loaded.' : '无法加载所选 Capture。'));
    } finally { if (!controller.signal.aborted && revision === detailRevision.current) setDetailLoading(false); }
  };

  const retryCapture = async () => {
    if (!detail || detail.status !== 'partial_success' || retrying) return;
    const captureId = detail.capture_id;
    const revision = detailRevision.current;
    const isCurrentSelection = () => !scopeController.current?.signal.aborted
      && detailRevision.current === revision && selectedCaptureId.current === captureId;
    const signal = scopeController.current?.signal;
    if (!signal || signal.aborted) return;
    setRetrying(true); setDetailError('');
    try {
      const response = await fetch(`/api/capture/${encodeURIComponent(captureId)}/retry`, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      if (!isCurrentSelection()) return;
      const retryResult = await response.json() as CaptureItem;
      if (!isCurrentSelection()) return;
      if (retryResult.capture_id !== captureId) throw new Error('Capture identity mismatch');
      setDetail(retryResult);
      await refreshSummary();
    } catch (cause) { if (isCurrentSelection()) setDetailError(cause instanceof Error ? cause.message : (en ? 'Retry failed.' : '重试失败。')); }
    finally { if (isCurrentSelection()) setRetrying(false); }
  };

  return <>
    {error && <p className="capture-alert" role="alert">{error}</p>}
    <section className="inbox-header-actions" aria-label={en ? 'Organizer controls' : '自动整理操作'}>
      {!organizerStatusRequested ? <button type="button" onClick={requestOrganizerStatus}>{en ? 'Check organizer status' : '查看自动整理状态'}</button> : <>
        <button type="button" disabled={!organizeAvailable || organizeBusy} title={organizeReason} onClick={() => void organizeNow()}>{organizeBusy ? (en ? 'Organizing…' : '整理中…') : (en ? 'Organize now' : '立即整理')}</button>
        <small>{organizeReason || (en ? 'Settings are saved, but the organizer is not active.' : '设置仅保存，自动整理尚未运行。')}</small>
        {organizeMessage && <small role="status">{organizeMessage}</small>}
      </>}
    </section>
    <div className="inbox-list" aria-live="polite">{loading ? <p>{en ? 'Loading summary…' : '正在加载摘要…'}</p> : items.length ? items.map((item) => <article className="inbox-item" key={item.capture_id}>
      <div className="inbox-item-main"><span className="inbox-type">{(item.input_type || 'item').toUpperCase()}</span><div><h2>{item.display_filename || item.capture_id}</h2><p>{item.source_type || (en ? 'Source' : '来源')} · {capturedAtLabel(item.captured_at, locale)}</p></div><span className={`capture-status status-${item.status}`}>{captureStatus(item.status, en)}</span></div>
      {item.error_code && <p className="capture-processing-note">{en ? 'Error code' : '错误代码'}: {item.error_code}</p>}
      <div className="inbox-links"><button type="button" onClick={() => void openCapture(item.capture_id)}>{en ? 'Open selected Capture' : '打开此 Capture'}</button></div>
    </article>) : <p className="capture-empty">{en ? 'No Capture entries.' : '没有 Capture 条目。'}</p>}</div>
    {detailLoading && <p role="status">{en ? 'Loading selected Capture…' : '正在加载所选 Capture…'}</p>}
    {detailError && <p role="alert" className="capture-alert">{detailError}</p>}
    {detail && <CapturePreview item={detail} locale={locale} content={detail.content_preview ?? null} error="" onClose={() => { detailController.current?.abort(); detailRevision.current += 1; selectedCaptureId.current = null; setRetrying(false); setDetail(null); setDetailError(''); }} onReview={onReview}
      onRetry={detail.status === 'partial_success' ? () => void retryCapture() : undefined} retrying={retrying} />}
  </>;
}

function InboxDraftList({ locale, onOpenDraft }: { locale: Locale; onOpenDraft: (path: string) => void }) {
  const en = locale === 'en';
  const [items, setItems] = useState<{ path: string; title: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    void fetch('/api/notes/drafts', { credentials: 'same-origin', signal: controller.signal }).then(async (response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json() as { items?: { path: string; title: string }[] };
    }).then((payload) => {
      if (active) setItems(Array.isArray(payload.items) ? payload.items.filter((item): item is { path: string; title: string } => Boolean(item) && typeof item.path === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(item.path) && typeof item.title === 'string') : []);
    }).catch((cause) => { if (active && !controller.signal.aborted) setError(cause instanceof Error ? cause.message : (en ? 'Draft list is unavailable.' : '草稿列表暂不可用。')); })
      .finally(() => { if (active && !controller.signal.aborted) setLoading(false); });
    return () => { active = false; controller.abort(); };
  }, [en]);
  if (error) return <p role="alert" className="capture-alert">{error}</p>;
  if (loading) return <p role="status">{en ? 'Loading Draft list…' : '正在加载草稿列表…'}</p>;
  return <div className="inbox-list" aria-live="polite">{items.length ? items.map((item) => <article className="inbox-item" key={item.path}>
    <div className="inbox-item-main"><div><h2>{item.title || item.path}</h2><p>{en ? 'Notes Draft' : 'Notes 草稿'}</p></div></div>
    <div className="inbox-links"><button type="button" onClick={() => onOpenDraft(item.path)}>{en ? 'Open selected Draft' : '打开此 Draft'}</button></div>
  </article>) : <p className="capture-empty">{en ? 'No Drafts.' : '没有草稿。'}</p>}</div>;
}

export function InboxPage({ locale, onReview, children }: { locale: Locale; onReview: (reviewPath: string) => void; children?: React.ReactNode }) {
  const [items, setItems] = useState<CaptureItem[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState<CaptureItem | null>(null);
  const [previewText, setPreviewText] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState('');
  const [organizeReason, setOrganizeReason] = useState('');
  const [organizeAvailable, setOrganizeAvailable] = useState(false);
  const [organizeBusy, setOrganizeBusy] = useState(false);
  const [organizeMessage, setOrganizeMessage] = useState('');
  const [anchorFeedback, setAnchorFeedback] = useState('');
  const load = async (showLoading = false) => {
    if (showLoading) setLoading(true);
    setError('');
    try {
      const response = await fetch('/api/inbox', { credentials: 'same-origin' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const value = await response.json();
      setItems(sortByCapturedAt(Array.isArray(value.items) ? value.items : [], (item: CaptureItem) => item.capture_id));
    } catch { setError(locale === 'en' ? 'Inbox could not be loaded.' : '收件箱暂时无法加载。'); }
    finally { setLoading(false); }
  };
  useEffect(() => {
    void load(true);
    void fetch('/api/automation/organize/status', { credentials: 'same-origin' }).then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    }).then((value) => {
      if (value && typeof value.blocked_reason === 'string') setOrganizeReason(value.blocked_reason);
      setOrganizeAvailable(value?.execution_available === true);
    }).catch((cause) => {
      setOrganizeAvailable(false);
      const status = cause instanceof Error ? /^HTTP (\d{3})$/.exec(cause.message)?.[1] : undefined;
      setOrganizeReason(status
        ? (locale === 'en' ? `Organizer status could not be verified (HTTP ${status}); action remains disabled.` : `自动整理状态无法验证（HTTP ${status}），操作保持禁用。`)
        : (locale === 'en' ? 'The organization runner is unavailable.' : '自动整理执行器当前不可用。'));
    });
    const refresh = () => void load();
    window.addEventListener('sb-inbox-refresh', refresh);
    const timer = window.setInterval(refresh, 5000);
    return () => { window.removeEventListener('sb-inbox-refresh', refresh); window.clearInterval(timer); };
  }, []);
  useEffect(() => {
    const match = window.location.hash.match(/^#capture-([a-f\d]{32})$/i);
    if (!match || loading || error) return;
    const target = document.getElementById(`capture-${match[1]}`);
    if (!target) {
      setAnchorFeedback(locale === 'en'
        ? 'The requested Inbox source was not found in the loaded list.'
        : '未在当前收件箱列表中找到指定来源。');
      return;
    }
    setAnchorFeedback('');
    const frame = window.requestAnimationFrame(() => {
      target.scrollIntoView?.({ block: 'center' });
      target.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [items, loading, error, locale]);
  const text = locale === 'en';
  const openPreview = async (item: CaptureItem) => {
    setPreview(item); setPreviewText(null); setPreviewError('');
    if (previewKind(item.raw_path) === 'text') {
      try {
        const response = await fetch(`/api/inbox/${encodeURIComponent(item.capture_id)}/preview`, { credentials: 'same-origin' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        setPreviewText(await response.text());
      } catch { setPreviewError(text ? 'Preview could not be loaded.' : '原件预览暂时无法加载。'); }
    }
  };
  const retryCapture = async (item: CaptureItem) => {
    setError('');
    try {
      const response = await fetch(`/api/capture/${encodeURIComponent(item.capture_id)}/retry`, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) { setError(apiFailureLabel(payload.detail, response.status, locale, 'capture')); return; }
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? apiFailureLabel(cause.message, 0, locale, 'capture') : (text ? 'Retry failed.' : '重试请求未成功，请稍后再试。'));
    }
  };
  const organizeNow = async () => {
    if (!organizeAvailable || organizeBusy) return;
    setOrganizeBusy(true); setOrganizeMessage('');
    try {
      const response = await fetch('/api/automation/organize/run', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      const value = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error('organizer_run_failed');
      const label = value.status === 'no_new_messages' ? (text ? 'No new messages to organize.' : '没有新增对话，无需整理。')
        : value.status === 'already_running' ? (text ? 'An organization job is already running.' : '已有整理任务正在运行。')
          : (text ? `Organization finished; ${Number(value.draft_count ?? 0)} drafts added.` : `整理完成，新增 ${Number(value.draft_count ?? 0)} 条 Review 草稿。`);
      setOrganizeMessage(label); window.dispatchEvent(new Event('sb-inbox-refresh'));
    } catch {
      setOrganizeMessage(text ? 'Organization could not be completed; check its status and try again.' : '整理未能完成，请查看运行状态后再试。');
    } finally { setOrganizeBusy(false); }
  };
  return <section className="capture-page" aria-labelledby="inbox-title">
    <header className="capture-page-header"><div><p className="eyebrow">SECONDBRAIN <span>/</span> INBOX</p><h1 id="inbox-title">{text ? 'Inbox' : '收件箱'}</h1><p className="workspace-subtitle">{text ? 'Captured source material and processing status.' : '查看采集来源、原始素材和处理状态。'}</p></div><div className="inbox-header-actions"><button type="button" disabled={!organizeAvailable || organizeBusy} title={organizeReason} onClick={() => void organizeNow()}>{organizeBusy ? (text ? 'Organizing…' : '整理中…') : (text ? 'Organize now' : '立即整理')}</button><small>{organizeReason || (text ? 'Settings are saved, but the organizer is not active.' : '设置仅保存，自动整理尚未运行。')}</small>{organizeMessage && <small role="status">{organizeMessage}</small>}</div></header>
    {error && <p role="alert" className="capture-alert">{error}</p>}
    {anchorFeedback && <p role="status" className="capture-processing-note">{anchorFeedback}</p>}
    <div className="inbox-list" aria-live="polite">{loading ? <p>{text ? 'Loading…' : '加载中…'}</p> : items.length ? items.map((item) => <article className="inbox-item" id={`capture-${item.capture_id}`} tabIndex={-1} key={item.capture_id}>
      <div className="inbox-item-main"><span className="inbox-type">{item.input_type.toUpperCase()}</span><div><h2>{captureDisplayFilename(item, locale)}</h2><p>{item.source_type} · {capturedAtLabel(item.captured_at, locale)}</p></div><span className={`capture-status status-${item.status}`}>{captureStatus(item.status, text)}</span></div>
      {item.content_preview && <pre className="inbox-preview">{item.content_preview.slice(0, 500)}</pre>}
      {isVisionDescriptionOnly(item)
        ? <p className="capture-processing-note" role="status">{text ? 'Text recognition completed; image understanding is not connected yet.' : '文字识别完成，画面理解暂未接入。'}</p>
        : item.error && <p className="capture-alert">{captureFailureLabel(item.error, locale)}</p>}
      <div className="inbox-links"><button type="button" onClick={() => void openPreview(item)}>{text ? 'Preview details' : '预览与详情'}</button><a href={`/api/inbox/${encodeURIComponent(item.capture_id)}/raw`} download>{text ? 'Download Raw' : '下载原件'}</a>{item.review_path && <button type="button" onClick={() => onReview(item.review_path!)}>{text ? 'View Review' : '查看 Review'}</button>}{item.status === 'partial_success' && !isVisionDescriptionOnly(item) && <button type="button" onClick={() => void retryCapture(item)}>{text ? 'Retry' : '重试处理'}</button>}</div>
    </article>) : <p className="capture-empty">{text ? 'No captures yet.' : '还没有采集内容。'}</p>}</div>
    {children}
    {preview && <CapturePreview item={preview} locale={locale} content={previewText} error={previewError} onClose={() => { setPreview(null); setPreviewText(null); setPreviewError(''); }} onReview={onReview} />}
  </section>;
}

function previewKind(path: string): 'text' | 'pdf' | 'image' | 'audio' | 'unsupported' {
  const suffix = path.toLowerCase().split('.').pop() || '';
  if (['txt', 'md', 'markdown'].includes(suffix)) return 'text';
  if (suffix === 'pdf') return 'pdf';
  if (['png', 'jpg', 'jpeg', 'webp', 'gif'].includes(suffix)) return 'image';
  if (['wav', 'mp3', 'm4a', 'aac', 'ogg', 'flac'].includes(suffix)) return 'audio';
  return 'unsupported';
}

function isSafeHttpUrl(value: string): boolean {
  try { const url = new URL(value); return url.protocol === 'http:' || url.protocol === 'https:'; }
  catch { return false; }
}

function CapturePreview({ item, locale, content, error, onClose, onReview, onRetry, retrying = false }: { item: CaptureItem; locale: Locale; content: string | null; error: string; onClose: () => void; onReview: (path: string) => void; onRetry?: () => void; retrying?: boolean }) {
  const en = locale === 'en';
  const displayFilename = captureDisplayFilename(item, locale);
  const kind = previewKind(item.raw_path);
  const url = `/api/inbox/${encodeURIComponent(item.capture_id)}/preview`;
  return <div className="capture-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="capture-modal capture-preview-modal" role="dialog" aria-modal="true" aria-labelledby="capture-preview-title">
      <header><div><p className="eyebrow">SECONDBRAIN / INBOX</p><h2 id="capture-preview-title">{displayFilename}</h2></div><button className="capture-close" onClick={onClose} aria-label={en ? 'Close' : '关闭'}>×</button></header>
      <p>{captureStatus(item.status, en)} · {new Date(item.captured_at).toLocaleString(en ? 'en-US' : 'zh-CN')}</p>
      <p>{item.raw_path ? (en ? 'Raw preserved' : '原件已保存') : (en ? 'Raw unavailable' : '原件未保存')} · {isVisionDescriptionOnly(item) ? (en ? 'Text recognition completed; image understanding is not connected yet.' : '文字识别完成，画面理解暂未接入。') : item.error ? captureFailureLabel(item.error, locale) : (en ? 'No processing error' : '无处理错误')}</p>
      {item.source_url && <dl><dt>{en ? 'Original URL' : '原始 URL'}</dt><dd>{isSafeHttpUrl(item.source_url) ? <a href={item.source_url} target="_blank" rel="noreferrer">{item.source_url}</a> : item.source_url}</dd>{item.derived_source_url && <><dt>{en ? 'Fetched URL' : '实际获取地址'}</dt><dd>{item.derived_source_url}</dd></>}</dl>}
      <div className="capture-preview-content">
        {kind === 'text' && (error ? <p role="alert">{error}</p> : content === null ? <p>{en ? 'Loading preview…' : '正在读取预览…'}</p> : <pre>{content}</pre>)}
        {kind === 'pdf' && <p><a href={url} target="_blank" rel="noreferrer">{en ? 'Open PDF preview' : '在新标签页预览 PDF'}</a></p>}
        {kind === 'image' && <img src={url} alt={displayFilename} />}
        {kind === 'audio' && <audio controls preload="metadata" src={url}>{en ? 'Audio playback is not supported by this browser.' : '当前浏览器不支持此音频播放。'}</audio>}
        {kind === 'unsupported' && <p>{en ? 'This file type cannot be previewed here. Download the original file instead.' : '此类型暂不支持站内预览，可下载原件查看。'}</p>}
      </div>
      <footer><a className="capture-secondary" href={`/api/inbox/${encodeURIComponent(item.capture_id)}/raw`} download>{en ? 'Download original' : '下载原件'}</a>{item.review_path && <button type="button" className="capture-primary" onClick={() => onReview(item.review_path!)}>{en ? 'View related Review' : '查看对应 Review'}</button>}{onRetry && <button type="button" className="capture-primary" onClick={onRetry} disabled={retrying}>{retrying ? (en ? 'Retrying…' : '重试中…') : (en ? 'Retry selected Capture' : '重试此 Capture')}</button>}<button type="button" className="capture-secondary" onClick={onClose}>{en ? 'Close' : '关闭'}</button></footer>
    </section>
  </div>;
}

function captureStatus(status: string, en: boolean) {
  return captureStatusLabel(status, en ? 'en' : 'zh-CN');
}

export function ReviewPage({ locale, onBack, initialReviewPath = null, expectedReviewSha256 = null, pushHistory = (path: string) => history.pushState({}, '', path) }: { locale: Locale; onBack: () => void; initialReviewPath?: string | null; expectedReviewSha256?: string | null; pushHistory?: (path: string) => void }) {
  const t = messages[locale];
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string>(t.coreLoading);
  const [promoteEnabled, setPromoteEnabled] = useState(false);
  const [promotionSelectedPath, setPromotionSelectedPath] = useState<string | null>(null);
  const [mobileListOpen, setMobileListOpen] = useState(false);
  const reviewListRef = useRef<HTMLDivElement | null>(null);
  const reviewDetailRef = useRef<HTMLElement | null>(null);
  const selectedReviewRef = useRef<HTMLButtonElement | null>(null);
  const detailRequestRef = useRef<AbortController | null>(null);
  const detailRequestSequence = useRef(0);
  const listRequestRef = useRef<AbortController | null>(null);
  const listRequestSequence = useRef(0);

  const request = async <T,>(path: string, init: RequestInit = {}): Promise<T> => {
    const response = await fetch(`/api/promote${path}`, {
      ...init,
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
    });
    let payload: Record<string, unknown> = {};
    try { payload = await response.json() as Record<string, unknown>; } catch { /* retain status fallback */ }
    if (!response.ok) {
      const error = new Error(apiFailureLabel(payload.detail, response.status, locale, 'review'));
      Object.assign(error, { status: response.status });
      throw error;
    }
    return payload as T;
  };

  const loadList = async () => {
    listRequestRef.current?.abort();
    detailRequestSequence.current += 1;
    detailRequestRef.current?.abort();
    const controller = new AbortController();
    listRequestRef.current = controller;
    const sequence = ++listRequestSequence.current;
    setBusy(true);
    setStatus(t.coreLoading);
    const requestedReviewPath = location.pathname === '/review'
      ? new URLSearchParams(location.search).get('review_path')
      : initialReviewPath;
    try {
      const result = await request<{ items?: ReviewItem[] }>('/review/items', { signal: controller.signal });
      if (controller.signal.aborted || sequence !== listRequestSequence.current) return;
      const nextItems = sortByCapturedAt(Array.isArray(result.items) ? result.items : [], (item) => item.review_path);
      setItems(nextItems);
      setStatus(t.coreConnected.replace('{count}', String(nextItems.length)));
      if (requestedReviewPath) {
        const selected = nextItems.find((item) => item.review_path === requestedReviewPath);
        if (selected && expectedReviewSha256 && selected.review_sha256 !== expectedReviewSha256) {
          setDetail(null); setStatus(locale === 'en' ? 'The linked Review source has changed; no source content was opened.' : '关联的 Review 来源版本已变化；未打开来源正文。');
        } else if (selected && !controller.signal.aborted) await loadDetail(selected);
        else { setDetail(null); setStatus(locale === 'en' ? 'The requested Review item could not be found.' : '找不到指定的 Review 条目。'); }
      } else {
        setDetail(null);
        setPromotionSelectedPath(null);
      }
      if (controller.signal.aborted || sequence !== listRequestSequence.current) return;
      const promote = await request<{ promote_enabled?: boolean }>('/status', { signal: controller.signal });
      if (controller.signal.aborted || sequence !== listRequestSequence.current) return;
      setPromoteEnabled(promote.promote_enabled === true);
    } catch (error) {
      if (controller.signal.aborted || sequence !== listRequestSequence.current) return;
      setItems([]);
      setDetail(null);
      const statusCode = (error as Error & { status?: number }).status;
      if (statusCode === 401) window.location.reload();
      setStatus(error instanceof Error ? apiFailureLabel(error.message, statusCode ?? 0, locale, 'review') : t.coreConnectionFailed);
    } finally {
      if (sequence === listRequestSequence.current) setBusy(false);
    }
  };

  const loadDetail = async (item: ReviewItem) => {
    detailRequestRef.current?.abort();
    const controller = new AbortController();
    detailRequestRef.current = controller;
    const sequence = ++detailRequestSequence.current;
    setBusy(true);
    try {
      const safePath = item.review_path.split('/').map(encodeURIComponent).join('/');
      const result = await request<ReviewDetail>(`/review/items/${safePath}`, { signal: controller.signal });
      if (controller.signal.aborted || sequence !== detailRequestSequence.current) return;
      if (result.review_path !== item.review_path || result.review_sha256 !== item.review_sha256) {
        throw Object.assign(new Error(locale === 'en' ? 'Review source changed while opening; no content was shown.' : '打开时 Review 来源版本发生变化；未展示来源正文。'), { status: 409 });
      }
      setDetail({ ...result, captured_at: result.captured_at ?? item.captured_at ?? null });
    } catch (error) {
      if (controller.signal.aborted || sequence !== detailRequestSequence.current) return;
      setDetail(null);
      const statusCode = (error as Error & { status?: number }).status;
      setStatus(statusCode === 401 ? t.coreSessionExpired : error instanceof Error ? apiFailureLabel(error.message, statusCode ?? 0, locale, 'review') : t.coreConnectionFailed);
      if (statusCode === 401) window.location.reload();
    } finally {
      if (sequence === detailRequestSequence.current) setBusy(false);
    }
  };

  useEffect(() => {
    void loadList();
    // Initial status check only; subsequent reads are user initiated.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialReviewPath]);

  useEffect(() => () => {
    listRequestSequence.current += 1;
    listRequestRef.current?.abort();
    detailRequestSequence.current += 1;
    detailRequestRef.current?.abort();
  }, []);

  useEffect(() => {
    if (!detail?.review_path) return;
    if (reviewDetailRef.current) reviewDetailRef.current.scrollTop = 0;
  }, [detail?.review_path]);

  useEffect(() => {
    if (!detail?.review_path) return;
    const frame = window.requestAnimationFrame(() => {
      const list = reviewListRef.current;
      const selected = selectedReviewRef.current;
      if (list && selected) scrollReviewItemIntoView(list, selected);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [detail?.review_path, mobileListOpen]);

  const selectReview = (item: ReviewItem) => {
    setDetail(null);
    setPromotionSelectedPath(item.review_path);
    setStatus(locale === 'en' ? 'Loading selected Review…' : '正在读取所选 Review…');
    const query = new URLSearchParams({ review_path: item.review_path });
    pushHistory(`/review?${query}`);
    setMobileListOpen(false);
    void loadDetail(item);
  };

  const decide = async () => {
    if (!detail) return;
    setBusy(true);
    try {
      const result = await request<{ status?: string }>('/review/defer', { method: 'POST', body: JSON.stringify({
        review_path: detail.review_path, review_sha256: detail.review_sha256,
        request_id: crypto.randomUUID(), target_filename: detail.target_filename,
      }) });
      setStatus(reviewStatusLabel(result.status || 'deferred', locale));
      await loadList();
    } catch (error) {
      const message = error instanceof Error ? apiFailureLabel(error.message, (error as Error & { status?: number }).status ?? 0, locale, 'review') : t.coreConnectionFailed;
      await loadList();
      setStatus(message);
    } finally { setBusy(false); }
  };

  const document = detail ? parseReviewDocument(detail.content) : null;
  const decisionStatus = detail?.decision?.status || detail?.status || 'pending';
  const isOcrDocument = Boolean(document && (/^OCR:\s*tesseract\s*;/m.test(document.body) || /## OCR 识别文字/.test(document.body)));
  const ocrOnlyText = Boolean(document?.metadata.source_type === 'image' && /## AI 画面描述/.test(document.body));
  const visibleReviewBody = isOcrDocument && document
    ? document.body.replace(/^OCR:\s*tesseract\s*;[^\n]*(?:\n|$)/m, '')
    : document?.body ?? '';

  return <section className="review-page" aria-labelledby="review-page-title">
    <header className="review-page-header">
      <div><p className="eyebrow">SECONDBRAIN <span>/</span> {t.review.toUpperCase()}</p><h1 id="review-page-title">{t.reviewPageTitle}</h1><p className="workspace-subtitle">{t.reviewPageDescription}</p></div>
      <button type="button" className="review-back-button" onClick={onBack}>{t.backHome}</button>
    </header>
    <p className={`review-connection-status ${busy ? 'is-locked' : 'is-connected'}`} role="status" aria-live="polite">{status}</p>
      <div className="review-page-toolbar"><div><button type="button" className="review-mobile-list-toggle" aria-expanded={mobileListOpen} onClick={() => setMobileListOpen((open) => !open)}>{mobileListOpen ? (locale === 'en' ? 'Hide list' : '收起列表') : (locale === 'en' ? 'Browse list' : '浏览审核列表')}</button><button type="button" onClick={() => void loadList()} disabled={busy}>{locale === 'en' ? 'Refresh' : '刷新'}</button></div></div>
      <div className="review-page-grid">
        <div ref={reviewListRef} className={`review-page-list ${mobileListOpen ? 'is-mobile-open' : 'is-mobile-collapsed'}`} aria-label={t.reviewPageTitle}>
          {items.length ? items.map((item) => <button ref={detail?.review_path === item.review_path ? selectedReviewRef : null} key={item.review_path} type="button" className={`review-page-item ${detail?.review_path === item.review_path ? 'is-selected' : ''}`} onClick={() => selectReview(item)}>
        <strong>{item.title || item.target_filename}</strong><small>{item.target_filename} · {capturedAtLabel(item.captured_at, locale)}</small><span>{t.coreStatus}: {reviewStatusLabel(item.decision?.status || item.status || 'pending', locale)}</span>
          </button>) : <p className="review-page-empty">{t.coreNoItems}</p>}
        </div>
        <article ref={reviewDetailRef} className="review-page-detail" tabIndex={-1}>
          {detail && document ? <><header className="review-detail-heading"><h2>{detail.title || detail.target_filename}</h2><p>{detail.target_filename} · {t.coreStatus}: {reviewStatusLabel(decisionStatus, locale)}{detail.decision?.error_code ? ` · ${locale === 'en' ? 'Failure' : '失败'}: ${detail.decision.error_code}` : ''}</p><dl><dt>{locale === 'en' ? 'Source' : '来源'}</dt><dd>{document.metadata.source_type || (locale === 'en' ? 'Not provided' : '未提供')}</dd><dt>{locale === 'en' ? 'Captured' : '采集日期'}</dt><dd>{capturedAtLabel(detail.captured_at ?? document.metadata.captured_at, locale)}</dd></dl></header>
            {isOcrDocument && <p className="review-ocr-note" role="note">{ocrOnlyText ? (locale === 'en' ? 'OCR text only. Please verify the recognized text against the original.' : '仅包含 OCR 文字识别结果，请对照原件核对。') : (locale === 'en' ? 'OCR text may contain recognition errors. Please verify it against the original.' : 'OCR 识别可能存在误差，请对照原件核对。')}</p>}
            <details className="review-metadata"><summary>{locale === 'en' ? 'Full metadata' : '完整元数据'}</summary><dl>{Object.entries(document.metadata).map(([key, value]) => <React.Fragment key={key}><dt>{key}</dt><dd>{value}</dd></React.Fragment>)}</dl></details>
            {isOcrDocument && <details className="review-source-original"><summary>{locale === 'en' ? 'Full original Review text' : '查看完整原始识别内容'}</summary><pre>{document.body}</pre></details>}
            <ReviewMarkdown source={visibleReviewBody} preserveLines={isOcrDocument} />
            <div className="review-decisions"><button type="button" onClick={() => void decide()} disabled={busy || ['approved', 'promoting', 'promoted', 'failed'].includes(detail.decision?.status || '')}>{locale === 'en' ? 'Defer' : '暂缓'}</button></div>
            {promotionSelectedPath === detail.review_path && <PromotePreviewPanel key={`${detail.review_path}:${detail.review_sha256}:${detail.target_filename}`} locale={locale}
              reviewPath={detail.review_path} reviewSha256={detail.review_sha256} targetFilename={detail.target_filename}
              title={detail.title || detail.target_filename} promoteEnabled={promoteEnabled} />}</> : <p>{t.coreSelectItem}</p>}
        </article>
      </div>
  </section>;
}

type ChatSession = { id: string; title: string; updated?: string | number };
type ChatMessage = ChatHistoryMessage;
type CaptureSuggestion = { approvedProposalId: string; approvedProposalVersion: number | null; sourceEventId: string; occurredAt: string; originalText: string; sessionId: string };
type CaptureApproval = { proposalId: string; version: number; kind: 'journal' | 'review' | 'project'; sourceVersion: string; vocabularyVersion: number };
type CaptureReceipt = { sessionId: string; inboxId: string; sourceEventId: string; proposalId: string; proposalVersion: number; sourceVersion: string; kind: 'journal' | 'review' | 'project' };
const captureReceiptKey = (sessionId: string) => `secondbrain.chat.captureReceipt:${sessionId}`;
const captureIdPattern = /^[0-9a-f]{32}$/;
const captureStatuses = new Set(['pending', 'prepared', 'processing', 'completed', 'partial_success', 'failed']);
const parseCaptureApproval = (body: unknown, suggestion: CaptureSuggestion): CaptureApproval | null => {
  if (!body || typeof body !== 'object') return null;
  const proposal = (body as Record<string, unknown>).proposal;
  if (!proposal || typeof proposal !== 'object') return null;
  const value = proposal as Record<string, unknown>;
  const proposalSuggestion = value.suggestion;
  if (!proposalSuggestion || typeof proposalSuggestion !== 'object' || Array.isArray(proposalSuggestion)) return null;
  const original = (proposalSuggestion as Record<string, unknown>).original;
  const current = (proposalSuggestion as Record<string, unknown>).current;
  if (!original || typeof original !== 'object' || Array.isArray(original)) return null;
  const originalValue = original as Record<string, unknown>;
  const originalKeys = Object.keys(originalValue).sort();
  if (originalKeys.length !== 2 || originalKeys[0] !== 'reason' || originalKeys[1] !== 'value'
    || typeof originalValue.value !== 'string' || typeof originalValue.reason !== 'string') return null;
  if (!current || typeof current !== 'object' || Array.isArray(current)
    || typeof (current as Record<string, unknown>).value !== 'string') return null;
  if (value.proposal_id !== suggestion.approvedProposalId || value.status !== 'approved_recorded'
    || value.version !== suggestion.approvedProposalVersion || !Number.isInteger(value.version)
    || !['journal', 'review', 'project'].includes(String(value.kind))
    || typeof value.source_version !== 'string' || !value.source_version
    || !Number.isSafeInteger(value.vocabulary_version) || (value.vocabulary_version as number) < 0
    || originalValue.value !== suggestion.originalText) return null;
  return { proposalId: value.proposal_id as string, version: value.version as number,
    kind: value.kind as CaptureApproval['kind'], sourceVersion: value.source_version,
    vocabularyVersion: value.vocabulary_version as number };
};
const parseCaptureReceiptResponse = (body: unknown, receipt: CaptureReceipt) => {
  if (!body || typeof body !== 'object') return null;
  const value = body as Record<string, unknown>;
  const source = value.source as Record<string, unknown> | undefined;
  const evidence = value.consent_evidence as Record<string, unknown> | undefined;
  const proposal = value.approved_proposal as Record<string, unknown> | undefined;
  const recordedAt = typeof evidence?.recorded_at === 'string' ? Date.parse(evidence.recorded_at) : Number.NaN;
  if (value.inbox_id !== receipt.inboxId || !captureIdPattern.test(String(value.inbox_id))
    || !captureStatuses.has(String(value.status)) || value.intent !== 'approved_suggestion'
    || source?.channel !== 'web' || source.event_id !== receipt.sourceEventId
    || evidence?.kind !== 'authenticated_app_approved_proposal' || typeof evidence.subject !== 'string' || !evidence.subject
    || !Number.isFinite(recordedAt) || evidence.source_version !== receipt.sourceVersion
    || evidence.proposal_id !== receipt.proposalId || evidence.proposal_version !== receipt.proposalVersion
    || proposal?.proposal_id !== receipt.proposalId || proposal.version !== receipt.proposalVersion
    || proposal.kind !== receipt.kind || proposal.source_version !== receipt.sourceVersion) return null;
  return String(value.status);
};

export function ChatPage({ locale, blankMode = false, onGoInbox, onGoJournal = () => undefined, onGoToday = () => undefined }: {
  locale: Locale; blankMode?: boolean; onGoInbox: () => void; onGoJournal?: () => void; onGoToday?: () => void;
}) {
  const en = locale === 'en';
  const [blankState, setBlankState] = useState<BlankChatState>(() => blankMode ? readBlankChatState() : { sessionIds: [], selectedSessionId: '' });
  const blankSessionIdsRef = useRef(new Set(blankState.sessionIds));
  const [sessions, setSessions] = useState<ChatSession[]>(() => blankMode ? blankChatSessionList(blankState.sessionIds, locale) : []);
  const [selected, setSelected] = useState(() => blankMode ? blankState.selectedSessionId : '');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [activities, setActivities] = useState<ChatActivity[]>([]);
  const [citationBundles, setCitationBundles] = useState<KnowledgeCitationBundle[]>([]);
  const [citationHistoryLoading, setCitationHistoryLoading] = useState(false);
  const [citationPersistenceIssue, setCitationPersistenceIssue] = useState(false);
  const [contextPreview, setContextPreview] = useState<ContextPreview | null>(null);
  const [contextPreviewLoading, setContextPreviewLoading] = useState(false);
  const [contextPreviewError, setContextPreviewError] = useState('');
  const [naturalContext, setNaturalContext] = useState<ContextPreview | null>(null);
  const [naturalContextLoading, setNaturalContextLoading] = useState(false);
  const [naturalContextError, setNaturalContextError] = useState('');
  const timeline = mergeChatTimeline(messages, activities);
  const [input, setInput] = useState('');
  const [progress, setProgress] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [runId, setRunId] = useState('');
  const [pendingApproval, setPendingApproval] = useState<RunToolApprovalCard | null>(null);
  const [approvalResolving, setApprovalResolving] = useState(false);
  const [captureSuggestion, setCaptureSuggestion] = useState<CaptureSuggestion | null>(null);
  const [captureApproval, setCaptureApproval] = useState<CaptureApproval | null>(null);
  const [captureReceipt, setCaptureReceipt] = useState<CaptureReceipt | null>(null);
  const [captureStatus, setCaptureStatus] = useState('');
  const [captureConfirmation, setCaptureConfirmation] = useState('');
  const [captureFeedback, setCaptureFeedback] = useState('');
  const [captureSourceId, setCaptureSourceId] = useState('');
  const [captureBusy, setCaptureBusy] = useState(false);
  const [journalInboxAttempt, setJournalInboxAttempt] = useState<JournalInboxAttempt | null>(null);
  const [journalInboxReceipt, setJournalInboxReceipt] = useState<JournalInboxReceipt | null>(null);
  const [journalInboxStatus, setJournalInboxStatus] = useState('');
  const [journalInboxFeedback, setJournalInboxFeedback] = useState('');
  const journalInboxAttemptsRef = useRef(new Map<string, JournalInboxAttempt>());
  const journalInboxSubmittingRef = useRef(false);
  const journalInboxSequenceRef = useRef(0);
  const [inputMode, setInputMode] = useState<'chat' | 'capture'>('chat');
  const [pendingAttachment, setPendingAttachment] = useState<File | null>(null);
  const [attachmentNotice, setAttachmentNotice] = useState('');
  const [chatDragOver, setChatDragOver] = useState(false);
  const [pendingPreview, setPendingPreview] = useState('');
  const attachmentInput = useRef<HTMLInputElement>(null);
  const abortRef = React.useRef<AbortController | null>(null);
  const selectedSessionRef = useRef(blankMode ? blankState.selectedSessionId : '');
  const selectionIntentRef = useRef(0);
  const contentLoadRef = useRef(0);
  const citationHistoryAbortRef = useRef<AbortController | null>(null);
  const contextPreviewAbortRef = useRef<AbortController | null>(null);
  const contextPreviewSequenceRef = useRef(0);
  const naturalContextAbortRef = useRef<AbortController | null>(null);
  const naturalContextSequenceRef = useRef(0);
  const citationFrameByRunRef = useRef(new Map<string, string>());
  const activityRetryRef = useRef<{ sessionId: string; text: string; key: string; kind: 'journal' | 'task' } | null>(null);
  const captureRequestSequence = useRef(0);

  useEffect(() => () => {
    citationHistoryAbortRef.current?.abort();
    contextPreviewSequenceRef.current += 1;
    contextPreviewAbortRef.current?.abort();
    naturalContextSequenceRef.current += 1;
    naturalContextAbortRef.current?.abort();
  }, []);

  useEffect(() => {
    contextPreviewSequenceRef.current += 1;
    contextPreviewAbortRef.current?.abort();
    setContextPreview(null); setContextPreviewLoading(false); setContextPreviewError('');
  }, [input]);

  useEffect(() => {
    if (!pendingAttachment?.type.startsWith('image/')) { setPendingPreview(''); return; }
    const url = URL.createObjectURL(pendingAttachment);
    setPendingPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [pendingAttachment]);

  const api = async <T,>(path: string, init: RequestInit = {}): Promise<T> => {
    const response = await fetch(path, { ...init, credentials: 'same-origin', headers: {
      ...(init.body ? { 'Content-Type': 'application/json' } : {}), ...(init.headers ?? {}),
    } });
    const body = await response.json().catch(() => ({})) as Record<string, unknown>;
    if (!response.ok) {
      if (response.status === 401) window.location.reload();
      throw new Error(apiFailureLabel(body.detail, response.status, locale, 'chat'));
    }
    return body as T;
  };

  const refreshCaptureReceipt = async (receipt: CaptureReceipt, sequence: number) => {
    const payload = await api<Record<string, unknown>>(`/api/inbox/entries/${encodeURIComponent(receipt.inboxId)}`);
    if (selectedSessionRef.current !== receipt.sessionId || sequence !== captureRequestSequence.current) return;
    const status = parseCaptureReceiptResponse(payload, receipt);
    const sourceRef = payload.source_ref as Record<string, unknown> | undefined;
    if (!status || sourceRef?.capture_id !== receipt.inboxId) throw new Error(en ? 'Core could not verify this exact Inbox entry.' : 'Core 无法核验这条确切的 Inbox 记录。');
    setCaptureReceipt(receipt); setCaptureSourceId(receipt.inboxId); setCaptureStatus(status);
    setCaptureFeedback(en ? `Core accepted the entry; current processing status: ${status}.` : `Core 已受理；当前处理状态：${status}。`);
  };

  const verifyCaptureReceipt = async (receipt: CaptureReceipt, sequence: number) => {
    if (selectedSessionRef.current !== receipt.sessionId || sequence !== captureRequestSequence.current) return;
    setCaptureReceipt(receipt);
    setCaptureSourceId(''); setCaptureStatus('');
    setCaptureFeedback(en ? 'Verifying the saved receipt against the exact Inbox entry…' : '正在向 Core 核验已保存回执对应的确切 Inbox 记录…');
    try {
      await refreshCaptureReceipt(receipt, sequence);
    } catch (cause) {
      if (selectedSessionRef.current !== receipt.sessionId || sequence !== captureRequestSequence.current) return;
      setCaptureSourceId(''); setCaptureStatus('');
      setCaptureFeedback(en
        ? `The exact Inbox status is unverified. The opaque receipt is retained; retry verification later. ${cause instanceof Error ? cause.message : ''}`
        : `确切 Inbox 状态尚未核验。回执标识已保留，可稍后重新核验。${cause instanceof Error ? ` ${cause.message}` : ''}`);
    }
  };

  const persistBlankChatState = (sessionIds: string[], selectedSessionId: string) => {
    const uniqueIds = [...new Set(sessionIds)];
    const next: BlankChatState = {
      sessionIds: uniqueIds,
      selectedSessionId: uniqueIds.includes(selectedSessionId) ? selectedSessionId : '',
    };
    blankSessionIdsRef.current = new Set(uniqueIds);
    setBlankState(next);
    setSessions(blankChatSessionList(uniqueIds, locale));
    try { sessionStorage.setItem(blankChatStateKey, JSON.stringify(next)); } catch { /* the current page still retains its in-memory allowlist */ }
    return next;
  };

  const reloadSessions = async (preferred = selected) => {
    if (blankMode) return sessions;
    const payload = await api<Record<string, unknown>>('/api/chat/sessions?limit=50&offset=0');
    const raw = Array.isArray(payload.sessions) ? payload.sessions : Array.isArray(payload.items) ? payload.items : Array.isArray(payload) ? payload : [];
    const next = raw.flatMap((value, index) => {
      if (!value || typeof value !== 'object') return [];
      const row = value as Record<string, unknown>;
      const id = String(row.session_id ?? row.id ?? '');
      return id ? [{ id, title: String(row.title ?? row.name ?? (en ? `Session ${index + 1}` : `会话 ${index + 1}`)), updated: row.updated_at as string | number | undefined }] : [];
    });
    setSessions(next);
    if (!preferred && next.length) await selectSession(next[0].id);
    return next;
  };

  const pendingActivityKey = (sessionId: string) => `secondbrain.chat.pendingActivity:${sessionId}`;
  const clearPendingActivity = (sessionId: string, operationId: string) => {
    try {
      const raw = sessionStorage.getItem(pendingActivityKey(sessionId));
      const saved = raw ? JSON.parse(raw) as { operation_id?: string } : null;
      if (saved?.operation_id === operationId) sessionStorage.removeItem(pendingActivityKey(sessionId));
    } catch { sessionStorage.removeItem(pendingActivityKey(sessionId)); }
  };

  const resetJournalInboxView = () => {
    journalInboxSequenceRef.current += 1;
    setJournalInboxAttempt(null); setJournalInboxReceipt(null); setJournalInboxStatus(''); setJournalInboxFeedback('');
  };

  const verifyJournalInboxReceipt = async (receipt: JournalInboxReceipt, sequence: number) => {
    try {
      const response = await fetch(`/api/inbox/entries/${encodeURIComponent(receipt.inboxId)}`, { credentials: 'same-origin' });
      const payload = await response.json().catch(() => ({})) as unknown;
      if (!response.ok) {
        if (selectedSessionRef.current === receipt.sessionId && sequence === journalInboxSequenceRef.current) {
          setJournalInboxStatus('');
          setJournalInboxFeedback(en ? `Inbox returned HTTP ${response.status} for the read-only status check. The POST was accepted; no Journal entry was created. Retry status verification later.` : `Inbox 状态只读核验返回 HTTP ${response.status}。此前 POST 已受理，但没有创建 Journal 日记；可稍后重新核验。`);
        }
        return;
      }
      const status = parseJournalInboxGet(payload, receipt);
      if (!status) {
        if (selectedSessionRef.current === receipt.sessionId && sequence === journalInboxSequenceRef.current) {
          setJournalInboxStatus('');
          setJournalInboxFeedback(en ? 'Core returned a different or incomplete Inbox entry. The Journal was not created.' : 'Core 返回了其他或不完整的 Inbox 记录；尚未创建日记。');
        }
        return;
      }
      if (selectedSessionRef.current !== receipt.sessionId || sequence !== journalInboxSequenceRef.current) return;
      setJournalInboxReceipt(receipt); setJournalInboxStatus(status);
      setJournalInboxFeedback(en ? 'Original text is in the pending Inbox. No Journal entry has been created.' : '原文已进入待处理 Inbox；尚未创建 Journal 日记。');
      journalInboxAttemptsRef.current.delete(receipt.sessionId);
      try { sessionStorage.removeItem(journalInboxAttemptKey(receipt.sessionId)); } catch { /* the exact receipt remains available */ }
    } catch {
      if (selectedSessionRef.current === receipt.sessionId && sequence === journalInboxSequenceRef.current) {
        setJournalInboxStatus(''); setJournalInboxFeedback(en ? 'Inbox accepted the original text, but the read-only status check had no confirmed response. No Journal entry was created; retry status verification later.' : 'Inbox 已受理原文，但状态只读核验未收到确定响应。没有创建 Journal 日记；可稍后重新核验。');
      }
    }
  };

  const loadJournalInboxState = (sessionId: string) => {
    let attempt: JournalInboxAttempt | null = null;
    let receipt: JournalInboxReceipt | null = null;
    try {
      attempt = parseJournalInboxAttempt(sessionStorage.getItem(journalInboxAttemptKey(sessionId)), sessionId);
      receipt = parseJournalInboxReceipt(sessionStorage.getItem(journalInboxReceiptKey(sessionId)), sessionId);
      if (!attempt && sessionStorage.getItem(journalInboxAttemptKey(sessionId))) sessionStorage.removeItem(journalInboxAttemptKey(sessionId));
      if (!receipt && sessionStorage.getItem(journalInboxReceiptKey(sessionId))) sessionStorage.removeItem(journalInboxReceiptKey(sessionId));
    } catch { /* keep the UI fail-closed when tab storage is unavailable */ }
    if (attempt) journalInboxAttemptsRef.current.set(sessionId, attempt);
    else journalInboxAttemptsRef.current.delete(sessionId);
    setJournalInboxAttempt(attempt); setJournalInboxReceipt(receipt); setJournalInboxStatus('');
    setJournalInboxFeedback(attempt ? (en ? 'The prior result is not confirmed. The original text, event ID, time, and full request are retained for an exact retry.' : '上次结果尚未确认；原文、事件 ID、时间和完整请求均已保留，可原样重试。') : '');
    if (attempt) setInput((current) => current || attempt!.body.original_text);
    if (receipt) {
      const sequence = ++journalInboxSequenceRef.current;
      setJournalInboxFeedback(en ? 'Checking the exact Inbox entry; no Journal write will be made.' : '正在核对确切的 Inbox 记录；不会写入 Journal。');
      void verifyJournalInboxReceipt(receipt, sequence);
    }
  };

  const restoreCitationReferences = async (sessionId: string, contentRequestId: number) => {
    citationHistoryAbortRef.current?.abort();
    const controller = new AbortController();
    citationHistoryAbortRef.current = controller;
    const locators = blankMode ? [] : readCitationRunLocators(sessionId);
    if (!locators.length) {
      if (contentRequestId === contentLoadRef.current && selectedSessionRef.current === sessionId) {
        setCitationBundles([]);
        setCitationHistoryLoading(false);
      }
      return;
    }
    setCitationBundles([]);
    setCitationHistoryLoading(true);
    const restored: KnowledgeCitationBundle[] = [];
    for (const locator of locators) {
      if (controller.signal.aborted) return;
      try {
        const response = await fetch(`/api/chat/sessions/${encodeURIComponent(sessionId)}/runs/${encodeURIComponent(locator.run_id)}/knowledge-citations`, {
          credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
          headers: { Accept: 'application/json' },
        });
        if (!response.ok) {
          restored.push(citationErrorBundle(locator, response.status));
          continue;
        }
        const payload: unknown = await response.json();
        restored.push(parseKnowledgeCitationBundle(payload, locator) ?? citationErrorBundle(locator, 502));
      } catch (cause) {
        if (controller.signal.aborted || (cause instanceof DOMException && cause.name === 'AbortError')) return;
        restored.push(citationErrorBundle(locator, 503));
      }
    }
    if (controller.signal.aborted || contentRequestId !== contentLoadRef.current
      || selectedSessionRef.current !== sessionId) return;
    setCitationBundles(restored);
    setCitationHistoryLoading(false);
  };

  const loadSessionContent = async (sessionId: string) => {
    if (blankMode && !blankSessionIdsRef.current.has(sessionId)) return;
    const requestId = ++contentLoadRef.current;
    const [historyResult, activityResult] = await Promise.allSettled([
      api<Record<string, unknown>>(`/api/chat/sessions/${encodeURIComponent(sessionId)}/messages`),
      api<Record<string, unknown>>(`/api/chat/sessions/${encodeURIComponent(sessionId)}/activities`),
    ]);
    if (requestId !== contentLoadRef.current || selectedSessionRef.current !== sessionId) return;
    loadJournalInboxState(sessionId);
    if (historyResult.status === 'fulfilled') {
      const payload = historyResult.value;
      const raw = Array.isArray(payload.messages) ? payload.messages : Array.isArray(payload.items) ? payload.items : Array.isArray(payload) ? payload : [];
      setMessages(raw.flatMap((value, index) => {
        if (!value || typeof value !== 'object') return [];
        const row = value as Record<string, unknown>;
        const role = String(row.role ?? row.type ?? '');
        if (role !== 'user' && role !== 'assistant') return [];
        let text = row.text ?? row.content ?? row.message ?? '';
        if (Array.isArray(text)) text = text.flatMap((part) => part && typeof part === 'object' && typeof (part as Record<string, unknown>).text === 'string' ? [(part as Record<string, unknown>).text] : []).join('\n');
        if (typeof row.text === 'string') text = row.text;
        return typeof text === 'string' && text ? [{ id: String(row.id ?? index), role, text,
          timestamp: typeof row.timestamp === 'string' || typeof row.timestamp === 'number' ? row.timestamp : null } as ChatMessage] : [];
      }));
    }
    if (activityResult.status === 'fulfilled') {
      const payload = activityResult.value;
      const loaded = Array.isArray(payload.activities) ? payload.activities as ChatActivity[] : [];
      const scoped = loaded.filter((item) => item.session_id === sessionId);
      setActivities(scoped);
      const rawPending = sessionStorage.getItem(pendingActivityKey(sessionId));
      if (rawPending) {
        try {
          const pending = JSON.parse(rawPending) as { session_id: string; operation_id: string; text: string; kind: 'journal' | 'task' };
          if (pending.session_id === sessionId) {
            const resolved = scoped.find((item) => item.operation_id === pending.operation_id && item.status === 'succeeded');
            if (resolved) {
              clearPendingActivity(sessionId, pending.operation_id);
              if (activityRetryRef.current?.key === pending.operation_id) activityRetryRef.current = null;
            } else {
              activityRetryRef.current = { sessionId, text: pending.text, key: pending.operation_id, kind: pending.kind };
              setInput((current) => current || pending.text);
              if (!scoped.some((item) => item.operation_id === pending.operation_id)) {
                setActivities((current) => [...current.filter((item) => item.operation_id !== pending.operation_id), {
                  event_id: `pending:${pending.operation_id}`, operation_id: pending.operation_id, session_id: sessionId,
                  kind: pending.kind, status: 'unknown', original_text: pending.text, occurred_at: new Date().toISOString(), transient: true,
                }]);
              }
            }
          }
        } catch { sessionStorage.removeItem(pendingActivityKey(sessionId)); }
      }
    }
    if (historyResult.status === 'rejected') setError(historyResult.reason instanceof Error
      ? chatFailureLabel(historyResult.reason.message, locale) : chatFailureLabel('Could not load session history', locale));
    else if (activityResult.status === 'rejected') setError(en ? 'System operation history is temporarily unavailable.' : '系统操作历史暂时不可用。');
    void restoreCitationReferences(sessionId, requestId);
  };

  const resetCaptureState = () => {
    captureRequestSequence.current += 1;
    setCaptureSuggestion(null); setCaptureApproval(null); setCaptureReceipt(null); setCaptureStatus('');
    setCaptureConfirmation(''); setCaptureFeedback(''); setCaptureSourceId(''); setCaptureBusy(false);
  };

  const selectSession = async (sessionId: string) => {
    if (blankMode && !blankSessionIdsRef.current.has(sessionId)) return;
    selectionIntentRef.current += 1;
    journalInboxSequenceRef.current += 1;
    abortRef.current?.abort(); abortRef.current = null;
    resetCaptureState(); resetJournalInboxView(); setBusy(false); setRunId(''); setProgress('');
    citationHistoryAbortRef.current?.abort(); setCitationBundles([]); setCitationHistoryLoading(false); setCitationPersistenceIssue(false);
    contextPreviewSequenceRef.current += 1; contextPreviewAbortRef.current?.abort();
    setContextPreview(null); setContextPreviewLoading(false); setContextPreviewError('');
    naturalContextSequenceRef.current += 1; naturalContextAbortRef.current?.abort();
    setNaturalContext(null); setNaturalContextLoading(false); setNaturalContextError('');
    selectedSessionRef.current = sessionId;
    setSelected(sessionId);
    if (blankMode) persistBlankChatState([...blankSessionIdsRef.current], sessionId);
    else localStorage.setItem('secondbrain.chat.session', sessionId);
    setError(''); setMessages([]); setActivities([]); setInput('');
    try { await loadSessionContent(sessionId); } catch (cause) { setError(cause instanceof Error ? chatFailureLabel(cause.message, locale) : chatFailureLabel('Could not load session history', locale)); }
  };

  const previewContext = async () => {
    const sessionId = selectedSessionRef.current;
    if (!sessionId || blankMode || busy) return;
    contextPreviewAbortRef.current?.abort();
    const controller = new AbortController();
    contextPreviewAbortRef.current = controller;
    const sequence = ++contextPreviewSequenceRef.current;
    setContextPreview(null); setContextPreviewError(''); setContextPreviewLoading(true);
    try {
      const result = await fetchContextPreview(sessionId, input, controller.signal);
      if (controller.signal.aborted || sequence !== contextPreviewSequenceRef.current || selectedSessionRef.current !== sessionId) return;
      setContextPreview(result);
    } catch (cause) {
      if (controller.signal.aborted || sequence !== contextPreviewSequenceRef.current || selectedSessionRef.current !== sessionId) return;
      const status = (cause as Error & { status?: number }).status;
      setContextPreviewError(status === 401
        ? (en ? 'Sign in again to check authorized context.' : '请重新登录后再核验获准的上下文。')
        : status === 403 ? (en ? 'Context access was denied. Refresh to check current permissions.' : '上下文访问已被拒绝；权限变化后请重新核验。')
          : status === 400 ? (en ? 'Enter a query between 1 and 200 characters.' : '请输入 1 到 200 个字符的查询内容。')
            : status === 404 ? (en ? 'This session is unavailable.' : '此会话不可用。')
              : status === 503 ? (en ? 'Authorized sources are temporarily unavailable.' : '获准来源暂时不可用。')
                : (en ? 'Context could not be verified. No metadata is shown.' : '上下文未能核验，未展示任何元数据。'));
    } finally {
      if (sequence === contextPreviewSequenceRef.current) setContextPreviewLoading(false);
    }
  };

  const checkNaturalContext = async (sessionId: string, userInput: string) => {
    if (blankMode || !userInput.trim() || [...userInput.trim()].length > 2000) return;
    naturalContextAbortRef.current?.abort();
    const controller = new AbortController(); naturalContextAbortRef.current = controller;
    const sequence = ++naturalContextSequenceRef.current;
    setNaturalContext(null); setNaturalContextError(''); setNaturalContextLoading(true);
    try {
      const result = await fetchContextCandidates(sessionId, userInput, controller.signal);
      if (!controller.signal.aborted && sequence === naturalContextSequenceRef.current && selectedSessionRef.current === sessionId) setNaturalContext(result);
    } catch (cause) {
      if (controller.signal.aborted || sequence !== naturalContextSequenceRef.current || selectedSessionRef.current !== sessionId) return;
      const status = (cause as Error & { status?: number }).status;
      setNaturalContextError(status === 401 ? (en ? 'Sign in again to check related sources.' : '请重新登录后查看相关来源。')
        : status === 403 ? (en ? 'Source access was denied; no candidates are shown.' : '来源访问被拒绝，未展示候选。')
          : status === 404 ? (en ? 'This session is unavailable.' : '此会话不可用。')
            : en ? 'Related sources could not be verified. Chat continued without them.' : '无法核验相关来源；对话已继续，未展示候选。');
    } finally { if (sequence === naturalContextSequenceRef.current) setNaturalContextLoading(false); }
  };

  const pollRun = async (activeRun: string, sessionId: string) => {
    if (blankMode && !blankSessionIdsRef.current.has(sessionId)) return false;
    const terminal = new Set(['completed', 'failed', 'error', 'cancelled', 'canceled', 'interrupted', 'expired']);
    for (let attempt = 0; attempt < 60; attempt += 1) {
      const result = await api<Record<string, unknown>>(`/api/chat/runs/${encodeURIComponent(activeRun)}`);
      const status = String(result.status ?? 'unknown').toLowerCase();
      if (terminal.has(status)) {
          if (status === 'failed' || status === 'error' || status === 'interrupted') setError(chatFailureLabel(String(result.error ?? (status === 'interrupted' ? 'Hermes run was interrupted' : 'Hermes run failed')), locale));
        setProgress(chatStatusLabel(status, locale));
        if (selectedSessionRef.current === sessionId) await loadSessionContent(sessionId);
        await reloadSessions(sessionId);
        if (!blankMode) {
          sessionStorage.removeItem('secondbrain.chat.activeRun');
          sessionStorage.removeItem('secondbrain.chat.activeSession');
        }
        return true;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
    }
    setProgress(en ? 'Run is still active; reconnect to check its result.' : '任务仍在运行；重新进入 Chat 可继续核对结果。');
    return false;
  };

  useEffect(() => { void (async () => {
    try {
      if (blankMode) {
        if (blankState.selectedSessionId && blankSessionIdsRef.current.has(blankState.selectedSessionId)) {
          await selectSession(blankState.selectedSessionId);
        }
        return;
      }
      const preferred = localStorage.getItem('secondbrain.chat.session') ?? '';
      const next = await reloadSessions(preferred);
      if (preferred && next.some((session) => session.id === preferred)) await selectSession(preferred);
      else if (preferred) {
        localStorage.removeItem('secondbrain.chat.session');
        if (next.length) await selectSession(next[0].id);
      }
      const activeRun = sessionStorage.getItem('secondbrain.chat.activeRun') ?? '';
      const activeSession = sessionStorage.getItem('secondbrain.chat.activeSession') ?? preferred;
      if (activeRun && activeSession) {
        selectedSessionRef.current = activeSession; setSelected(activeSession); setBusy(true); setRunId(activeRun);
        setProgress(en ? 'Checking the interrupted connection…' : '正在核对中断的连接…');
        try { await pollRun(activeRun, activeSession); }
        catch (cause) { setError(cause instanceof Error ? chatFailureLabel(cause.message, locale) : chatFailureLabel('Could not recover run status', locale)); }
        finally { setBusy(false); setRunId(''); }
      }
    } catch (cause) { setError(cause instanceof Error ? chatFailureLabel(cause.message, locale) : chatFailureLabel('Hermes API unavailable', locale)); }
  })(); }, []);

  useEffect(() => {
    if (!selected) return;
    let stored: CaptureReceipt | null = null;
    try {
      const raw = sessionStorage.getItem(captureReceiptKey(selected));
      const value = raw ? JSON.parse(raw) as Partial<CaptureReceipt> : null;
      if (value && value.sessionId === selected && typeof value.inboxId === 'string' && captureIdPattern.test(value.inboxId)
        && typeof value.sourceEventId === 'string' && typeof value.proposalId === 'string' && captureIdPattern.test(value.proposalId)
        && Number.isInteger(value.proposalVersion) && typeof value.sourceVersion === 'string' && value.sourceVersion
        && ['journal', 'review', 'project'].includes(String(value.kind))) {
        stored = value as CaptureReceipt;
      } else if (raw) sessionStorage.removeItem(captureReceiptKey(selected));
    } catch { sessionStorage.removeItem(captureReceiptKey(selected)); }
    if (!stored) return;
    const receipt = stored;
    const sequence = ++captureRequestSequence.current;
    setCaptureReceipt(receipt); setCaptureSourceId(''); setCaptureStatus('');
    setCaptureFeedback(en ? 'Checking the exact Inbox entry for this session…' : '正在核对本会话对应的 Inbox 记录…');
    void verifyCaptureReceipt(receipt, sequence);
  }, [selected]);

  const newSession = async () => {
    const selectionIntent = ++selectionIntentRef.current;
    setError('');
    try {
      const payload = await api<Record<string, unknown>>('/api/chat/sessions', { method: 'POST', body: '{}' });
      const id = String(payload.session_id ?? '');
      if (!id) throw new Error('Hermes did not return a session identifier');
      if (blankMode) {
        const ids = [...blankSessionIdsRef.current, id];
        const stillCurrent = selectionIntent === selectionIntentRef.current;
        const nextSelected = stillCurrent ? id : selectedSessionRef.current;
        persistBlankChatState(ids, nextSelected);
        if (stillCurrent) {
          resetCaptureState(); resetJournalInboxView();
          selectedSessionRef.current = id; setSelected(id); setMessages([]); setActivities([]); setInput('');
        }
        return;
      }
      await reloadSessions(id);
      if (selectionIntent !== selectionIntentRef.current) return;
      resetCaptureState(); resetJournalInboxView();
      selectedSessionRef.current = id; setSelected(id); setMessages([]); setActivities([]); setInput('');
      localStorage.setItem('secondbrain.chat.session', id);
    } catch (cause) {
      if (selectionIntent === selectionIntentRef.current) setError(cause instanceof Error ? chatFailureLabel(cause.message, locale) : chatFailureLabel('Could not create session', locale));
    }
  };

  const forkSession = async () => {
    if (blankMode) return;
    if (!selected) return;
    const selectionIntent = ++selectionIntentRef.current;
    try {
      const result = await api<Record<string, unknown>>(`/api/chat/sessions/${encodeURIComponent(selected)}/fork`, { method: 'POST', body: '{}' });
      const id = String(result.session_id ?? '');
      if (!id) throw new Error('Hermes did not return a forked session identifier');
      await reloadSessions(id);
      if (selectionIntent === selectionIntentRef.current) await selectSession(id);
    } catch (cause) {
      if (selectionIntent === selectionIntentRef.current) setError(cause instanceof Error ? chatFailureLabel(cause.message, locale) : chatFailureLabel('Could not fork session', locale));
    }
  };

  const ensureSelectedSession = async () => {
    const existing = selectedSessionRef.current;
    if (existing && (!blankMode || blankSessionIdsRef.current.has(existing))) return existing;
    if (blankMode) throw new Error(en ? 'Create a blank test session first.' : '请先明确创建一个空白合成会话。');
    const payload = await api<Record<string, unknown>>('/api/chat/sessions', { method: 'POST', body: '{}' });
    const sessionId = String(payload.session_id ?? '');
    if (!sessionId) throw new Error('Hermes did not return a session identifier');
    resetCaptureState(); resetJournalInboxView();
    selectedSessionRef.current = sessionId; setSelected(sessionId); setMessages([]); setActivities([]);
    localStorage.setItem('secondbrain.chat.session', sessionId);
    await reloadSessions(sessionId);
    return sessionId;
  };

  const updateVisibleActivity = (sessionId: string, activity: ChatActivity) => {
    if (selectedSessionRef.current !== sessionId) return;
    setActivities((current) => [...current.filter((item) => item.event_id !== activity.event_id && item.operation_id !== activity.operation_id), activity]);
  };

  const submitExplicitActivity = async (kind: 'journal' | 'task', originalText: string,
                                       taskCommand?: { title: string; due_date: string | null }) => {
    setError(''); setBusy(true); setProgress(en ? 'Saving system operation…' : '正在保存系统操作…');
    let sessionId = '';
    try {
      sessionId = await ensureSelectedSession();
      let saved: { session_id?: string; operation_id?: string; text?: string; kind?: 'journal' | 'task'; key?: string } | null = null;
      try { saved = JSON.parse(sessionStorage.getItem(pendingActivityKey(sessionId)) ?? 'null'); } catch { saved = null; }
      const retry = activityRetryRef.current?.sessionId === sessionId && activityRetryRef.current.text === originalText
        && activityRetryRef.current.kind === kind
        ? activityRetryRef.current.key
        : saved?.session_id === sessionId && saved.text === originalText && saved.kind === kind
          ? String(saved.operation_id ?? saved.key ?? crypto.randomUUID()) : crypto.randomUUID();
      activityRetryRef.current = { sessionId, text: originalText, key: retry, kind };
      sessionStorage.setItem(pendingActivityKey(sessionId), JSON.stringify({ session_id: sessionId,
        operation_id: retry, text: originalText, kind }));
      updateVisibleActivity(sessionId, { event_id: `pending:${retry}`, operation_id: retry, session_id: sessionId,
        kind, status: 'processing', original_text: originalText, occurred_at: new Date().toISOString(), transient: true });

      const url = kind === 'journal' ? '/api/journal/entries' : '/api/tasks';
      const body = kind === 'journal'
        ? { text: originalText, session_id: sessionId }
        : { title: taskCommand?.title, due_date: taskCommand?.due_date, original_command: originalText, session_id: sessionId };
      const response = await fetch(url, { method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': retry }, body: JSON.stringify(body) });
      const result = await response.json().catch(() => ({})) as {
        detail?: string; status?: string; date?: string;
        task?: { id?: string; title?: string; due_date?: string | null; status?: 'open' | 'completed'; created_at?: string };
        activity?: ChatActivity;
      };
      if (!response.ok) {
        if (response.status === 401) { window.location.reload(); return; }
        const currentError = kind === 'journal' && response.status === 503 && result.detail === 'Journal is not enabled'
          ? (en ? 'Journal is not enabled in this environment. Your text is still here.' : '当前环境未启用日记，原文仍保留在输入框中。')
          : kind === 'task' && response.status === 503 && result.detail === 'Task is not enabled'
            ? (en ? 'Task storage is not enabled in this environment. Your command is still here.' : '当前环境未启用待办存储，原命令仍保留在输入框中。')
            : response.status === 409
              ? (en ? 'This retry key conflicts with a different operation. Your input is still here.' : '该重试标识与其他操作冲突，原文仍保留在输入框中。')
              : apiFailureLabel(result.detail, response.status, locale, 'chat');
        const failed = result.activity ?? { event_id: `local:${kind}:${retry}`, operation_id: retry, session_id: sessionId,
          kind, status: response.status >= 500 ? 'unknown' as const : 'failed' as const, original_text: originalText,
          occurred_at: new Date().toISOString(), transient: true };
        updateVisibleActivity(sessionId, failed);
        if (selectedSessionRef.current === sessionId) { setInput(originalText); setProgress(''); setError(currentError); }
        return;
      }

      const activity = result.activity ?? (kind === 'journal'
        ? { event_id: `journal:${retry}`, operation_id: retry, session_id: sessionId, kind: 'journal' as const,
          status: 'succeeded' as const, original_text: originalText, occurred_at: new Date().toISOString(), journal_date: result.date }
        : { event_id: `task:${retry}`, operation_id: retry, session_id: sessionId, kind: 'task' as const,
          status: 'succeeded' as const, original_text: originalText, occurred_at: result.task?.created_at ?? new Date().toISOString(),
          task_id: result.task?.id, task_title: result.task?.title ?? taskCommand?.title,
          task_due_date: result.task?.due_date ?? taskCommand?.due_date, task_status: result.task?.status ?? 'open' });
      updateVisibleActivity(sessionId, activity);
      clearPendingActivity(sessionId, retry);
      activityRetryRef.current = null;
      if (selectedSessionRef.current === sessionId) { setInput(''); setProgress(''); }
      await loadSessionContent(sessionId);
    } catch (cause) {
      const errorMessage = cause instanceof Error ? chatFailureLabel(cause.message, locale)
        : kind === 'journal' ? (en ? 'Journal save failed. Your text is still here.' : '日记保存失败，原文仍保留在输入框中。')
          : (en ? 'Task creation failed. Your command is still here.' : '待办创建失败，原命令仍保留在输入框中。');
      if (sessionId) updateVisibleActivity(sessionId, { event_id: `local:${kind}:${activityRetryRef.current?.key ?? 'unknown'}`,
        operation_id: activityRetryRef.current?.key ?? 'unknown', session_id: sessionId, kind, status: 'unknown',
        original_text: originalText, occurred_at: new Date().toISOString(), transient: true });
      if (!sessionId || selectedSessionRef.current === sessionId) { setProgress(''); setError(errorMessage); setInput(originalText); }
    } finally {
      setBusy(false);
    }
  };

  const submitJournalIntentToInbox = async (originalText: string) => {
    if (journalInboxSubmittingRef.current) return;
    journalInboxSubmittingRef.current = true;
    setError(''); setBusy(true); setProgress(en ? 'Saving the original text to Inbox…' : '正在将原文保存到 Inbox…');
    let sessionId = '';
    let attempt: JournalInboxAttempt | null = null;
    let sequence = 0;
    try {
      sessionId = await ensureSelectedSession();
      attempt = journalInboxAttemptsRef.current.get(sessionId) ?? null;
      if (!attempt) {
        try { attempt = parseJournalInboxAttempt(sessionStorage.getItem(journalInboxAttemptKey(sessionId)), sessionId); }
        catch { attempt = null; }
      }
      if (attempt && attempt.body.original_text !== originalText) {
        if (selectedSessionRef.current === sessionId) {
          setJournalInboxAttempt(attempt);
          setJournalInboxFeedback(en ? 'A prior Inbox result is still unknown. Restore its exact text before retrying; no new request was sent.' : '上一条 Inbox 结果仍未知。请先恢复完全相同的原文再重试；本次没有发送新请求。');
        }
        return;
      }
      if (!attempt) {
        attempt = makeJournalInboxAttempt(sessionId, originalText, crypto.randomUUID(), new Date().toISOString());
      }
      journalInboxAttemptsRef.current.set(sessionId, attempt);
      // Persist the complete immutable request before every send so storage
      // failures cannot leave a retryable in-memory request that was never made durable.
      sessionStorage.setItem(journalInboxAttemptKey(sessionId), JSON.stringify(attempt));
      if (selectedSessionRef.current === sessionId) {
        setJournalInboxAttempt(attempt); setJournalInboxReceipt(null); setJournalInboxStatus('');
        setJournalInboxFeedback(en ? 'Submitting the exact original text to the pending Inbox; this does not create a Journal entry.' : '正在将完全相同的原文提交到待处理 Inbox；此操作不会创建 Journal 日记。');
      }
      sequence = ++journalInboxSequenceRef.current;
      const response = await fetch('/api/inbox/entries', { method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' }, body: attempt.bodyJson });
      const payload = await response.json().catch(() => ({})) as unknown;
      if (response.status !== 202) {
        if (selectedSessionRef.current === sessionId && sequence === journalInboxSequenceRef.current) {
          setJournalInboxStatus(''); setJournalInboxFeedback(journalInboxFailureLabel(response.status, en)); setProgress('');
        }
        return;
      }
      const accepted = parseJournalInboxPostReceipt(payload, attempt);
      if (!accepted) {
        if (selectedSessionRef.current === sessionId && sequence === journalInboxSequenceRef.current) {
          setJournalInboxStatus(''); setJournalInboxFeedback(en ? 'Core returned an unverified acceptance. The exact request and original text are retained for safe retry.' : 'Core 返回的受理回执无法核验；完整请求和原文已保留，可安全重试。'); setProgress('');
        }
        return;
      }
      const receipt: JournalInboxReceipt = { sessionId, inboxId: accepted.inboxId,
        sourceEventId: attempt.body.source_event_id, occurredAt: attempt.body.occurred_at };
      try {
        sessionStorage.setItem(journalInboxReceiptKey(sessionId), JSON.stringify(receipt));
        sessionStorage.removeItem(journalInboxAttemptKey(sessionId));
        journalInboxAttemptsRef.current.delete(sessionId);
      } catch {
        if (selectedSessionRef.current === sessionId && sequence === journalInboxSequenceRef.current) {
          setJournalInboxReceipt(receipt); setJournalInboxStatus('');
          setJournalInboxFeedback(en ? 'Core accepted the Inbox entry, but this tab could not persist its receipt. Your text remains available; retry uses the same event identity.' : 'Core 已受理 Inbox 原文，但当前标签页无法保存回执；输入内容仍保留，重试会复用同一事件身份。');
          setProgress('');
        }
        return;
      }
      if (selectedSessionRef.current === sessionId && sequence === journalInboxSequenceRef.current) {
        setJournalInboxAttempt(null); setJournalInboxReceipt(receipt); setJournalInboxStatus('');
        setJournalInboxFeedback(en ? 'Original text is in the pending Inbox. No Journal entry has been created.' : '原文已进入待处理 Inbox；尚未创建 Journal 日记。');
        setProgress('');
        setInput((current) => current === originalText ? '' : current);
      }
      await verifyJournalInboxReceipt(receipt, sequence);
    } catch {
      if (sessionId && attempt) journalInboxAttemptsRef.current.set(sessionId, attempt);
      if (sessionId && selectedSessionRef.current === sessionId && (!sequence || sequence === journalInboxSequenceRef.current)) {
        setJournalInboxAttempt(attempt); setJournalInboxStatus('');
        setJournalInboxFeedback(sequence
          ? journalInboxFailureLabel(null, en)
          : (en ? 'Could not safely retain the exact request in this tab, so nothing was sent. Retry only after storage is available.' : '无法在当前标签页安全保存完整请求，因此没有发送任何写入；请等存储可用后再重试。'));
        setProgress('');
      } else if (!sessionId) {
        setError(en ? 'Could not prepare the Inbox request. Your original text is still in the composer.' : '无法准备 Inbox 请求；原文仍保留在输入框中。');
        setProgress('');
      }
    } finally {
      journalInboxSubmittingRef.current = false;
      setBusy(false);
    }
  };

  const send = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const prompt = input.trim();
    if (!prompt || busy) return;
    if (blankMode && (!selectedSessionRef.current || !blankSessionIdsRef.current.has(selectedSessionRef.current))) {
      setError(en ? 'Create a blank test session before sending.' : '发送前请先明确创建空白合成会话。');
      return;
    }
    if (!pendingAttachment && isExplicitJournalIntent(input)) {
      await submitJournalIntentToInbox(input);
      return;
    }
    const taskCommand = !pendingAttachment ? parseExplicitTaskCommand(input) : null;
    if (taskCommand) {
      await submitExplicitActivity('task', input, taskCommand);
      return;
    }
    setError(''); setBusy(true); setProgress(en ? 'Starting…' : '正在启动…');
    const messageTime = new Date().toISOString();
    setMessages((current) => [...current, { id: `local-${Date.now()}`, role: 'user', text: prompt, timestamp: messageTime }, { id: `assistant-${Date.now()}`, role: 'assistant', text: '', timestamp: messageTime }]);
    let sessionId = selected;
    let startedRunId = '';
    const runSelectionIntent = selectionIntentRef.current;
    try {
      if (!sessionId) {
        if (blankMode) throw new Error(en ? 'Create a blank test session first.' : '请先明确创建空白合成会话。');
        const created = await api<Record<string, unknown>>('/api/chat/sessions', { method: 'POST', body: '{}' });
        sessionId = String(created.session_id ?? '');
        if (!sessionId) throw new Error('Hermes did not return a session identifier');
        resetCaptureState(); resetJournalInboxView(); selectedSessionRef.current = sessionId; setSelected(sessionId); localStorage.setItem('secondbrain.chat.session', sessionId);
        await reloadSessions(sessionId);
      }
      const idempotencyKey = crypto.randomUUID();
      const started = await api<Record<string, unknown>>(`/api/chat/sessions/${encodeURIComponent(sessionId)}/runs`, {
        method: 'POST', headers: { 'Idempotency-Key': idempotencyKey }, body: JSON.stringify({ input: prompt }),
      });
      const activeRun = String(started.run_id ?? '');
      if (!activeRun) throw new Error('Hermes did not return a run identifier');
      if (!blankMode && !pendingAttachment) void checkNaturalContext(sessionId, prompt);
      startedRunId = activeRun;
      if (!blankMode && !rememberCitationRun({ session_id: sessionId, run_id: activeRun })) setCitationPersistenceIssue(true);
      setInput('');
      setRunId(activeRun); setProgress(en ? 'Connected to Hermes' : '已连接 Hermes');
      if (!blankMode) {
        sessionStorage.setItem('secondbrain.chat.activeRun', activeRun);
        sessionStorage.setItem('secondbrain.chat.activeSession', sessionId);
      }
      const controller = new AbortController(); abortRef.current = controller;
      const response = await fetch(`/api/chat/runs/${encodeURIComponent(activeRun)}/events`, { credentials: 'same-origin', signal: controller.signal, headers: { Accept: 'text/event-stream' } });
      if (!response.ok || !response.body) throw new Error(`Hermes stream failed (HTTP ${response.status})`);
      const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = '';
      let sawTerminal = false;
      const consume = (frame: string) => {
        if (selectedSessionRef.current !== sessionId || runSelectionIntent !== selectionIntentRef.current) return;
        const data: string[] = [];
        for (const line of frame.split(/\r?\n/)) {
          if (line.startsWith(':')) continue;
          if (line.startsWith('data:')) data.push(line.slice(5).trimStart());
        }
        if (!data.length) return;
        let payload: Record<string, unknown> = {};
        try { payload = JSON.parse(data.join('\n')) as Record<string, unknown>; } catch { payload = { text: data.join('\n') }; }
        const eventName = String(payload.event ?? 'message');
        const name = String(payload.name ?? payload.tool_name ?? payload.tool ?? 'tool');
        if (eventName === 'knowledge.citations') {
          const locator: CitationRunLocator = { session_id: sessionId, run_id: activeRun };
          const parsed = parseKnowledgeCitationBundle(payload, locator);
          if (!parsed) {
            setCitationBundles((current) => [...current.filter((bundle) => bundle.run_id !== activeRun), citationErrorBundle(locator, 502)]);
          } else {
            const fingerprint = JSON.stringify(parsed);
            const previous = citationFrameByRunRef.current.get(activeRun);
            if (previous && previous !== fingerprint) {
              setCitationBundles((current) => [...current.filter((bundle) => bundle.run_id !== activeRun), citationErrorBundle(locator, 409)]);
            } else if (!previous) {
              citationFrameByRunRef.current.set(activeRun, fingerprint);
              setCitationBundles((current) => [...current.filter((bundle) => bundle.run_id !== activeRun), parsed]);
            }
          }
        } else if (eventName === 'message.delta' || eventName === 'assistant.delta' || eventName === 'response.output_text.delta' || eventName === 'text.delta') {
          const delta = String(payload.delta ?? payload.text ?? payload.output_text ?? payload.content ?? '');
          if (delta) setMessages((current) => current.map((message, index) => index === current.length - 1 && message.role === 'assistant' ? { ...message, text: message.text + delta } : message));
        } else if (eventName.startsWith('tool.')) {
          const detail = typeof payload.preview === 'string' && payload.preview ? ` · ${payload.preview}` : '';
          const failed = payload.error === true;
          const failure = typeof payload.error === 'string' && payload.error ? ` · ${chatFailureLabel(payload.error, locale)}` : failed ? (en ? ' · tool reported an error' : ' · 工具报告错误') : '';
          setProgress(`${chatToolStageLabel(eventName.replace('tool.', ''), locale)}: ${name}${detail}${failure}`);
        } else if (eventName === 'approval.request') {
          const card = parseRunToolApproval(payload, activeRun, sessionId);
          if (card) {
            setPendingApproval(card); setApprovalResolving(false);
            setProgress(en ? 'A file or terminal action is waiting for your approval.' : '文件或终端操作等待你的审批。');
          } else {
            setError(en ? 'An invalid approval request was blocked.' : '无效审批请求已被拦截。');
          }
        } else if (eventName === 'approval.blocked') {
          setPendingApproval(null);
          setError(en ? 'The approval request could not be verified and was blocked.' : '审批请求无法核验，已拦截。');
        } else if (eventName === 'capture.suggestion') {
          const approvedProposalId = payload.approved_proposal_id;
          const approvedProposalVersion = payload.approved_proposal_version;
          const sourceEventId = payload.source_event_id;
          const occurredAt = payload.occurred_at;
          const originalText = payload.original_text;
          if ((approvedProposalId === undefined || (typeof approvedProposalId === 'string' && captureIdPattern.test(approvedProposalId)))
            && (approvedProposalVersion === undefined || (Number.isInteger(approvedProposalVersion) && (approvedProposalVersion as number) > 0))
            && typeof sourceEventId === 'string' && /^[A-Za-z0-9._:-]{1,128}$/.test(sourceEventId)
            && typeof occurredAt === 'string' && !Number.isNaN(Date.parse(occurredAt))
            && typeof originalText === 'string' && originalText.trim().length > 0 && originalText.length <= 200000) {
            const suggestion: CaptureSuggestion = { approvedProposalId: typeof approvedProposalId === 'string' ? approvedProposalId : '',
              approvedProposalVersion: typeof approvedProposalVersion === 'number' ? approvedProposalVersion : null,
              sourceEventId, occurredAt, originalText, sessionId };
            setCaptureSuggestion(suggestion); setCaptureApproval(null); setCaptureReceipt(null); setCaptureStatus('');
            setCaptureConfirmation(''); setCaptureFeedback(''); setCaptureSourceId('');
          } else {
            setCaptureSuggestion(null);
            setError(en ? 'An invalid capture suggestion was ignored.' : '无效的收录建议已忽略。');
          }
        } else if (eventName === 'run.completed' || eventName === 'assistant.completed') {
          sawTerminal = true;
          setPendingApproval(null);
          const output = typeof payload.output === 'string' ? payload.output : '';
          setMessages((current) => current.map((message, index) => index === current.length - 1 && message.role === 'assistant' && !message.text && output ? { ...message, text: output } : message));
          setProgress(en ? 'Completed' : '已完成');
        } else if (eventName === 'run.failed' || eventName === 'run.cancelled' || eventName === 'run.interrupted') {
          sawTerminal = true;
          setPendingApproval(null);
          const detail = String(payload.error ?? (eventName === 'run.cancelled' ? (en ? 'Stopped' : '已停止') : eventName));
          const statusLabel = chatStatusLabel(eventName.replace('run.', ''), locale);
          setProgress(eventName === 'run.cancelled' ? statusLabel : chatFailureLabel(detail, locale));
          if (eventName === 'run.failed' || eventName === 'run.interrupted') { setError(chatFailureLabel(detail, locale)); setInput((current) => current || prompt); }
        }
      };
      while (true) {
        const part = await reader.read();
        buffer += decoder.decode(part.value ?? new Uint8Array(), { stream: !part.done });
        const frames = buffer.split(/\r?\n\r?\n/); buffer = frames.pop() ?? '';
        frames.forEach(consume);
        if (part.done) { if (buffer.trim()) consume(buffer); break; }
      }
      if (sawTerminal) {
        await loadSessionContent(sessionId); await reloadSessions(sessionId);
        if (!blankMode) {
          sessionStorage.removeItem('secondbrain.chat.activeRun'); sessionStorage.removeItem('secondbrain.chat.activeSession');
        }
      } else {
        setProgress(en ? 'Stream ended; checking run status…' : '连接结束，正在核对任务状态…');
        await pollRun(activeRun, sessionId);
      }
    } catch (cause) {
      if (selectedSessionRef.current !== sessionId || runSelectionIntent !== selectionIntentRef.current) return;
      setInput((current) => current || prompt);
      if (!(cause instanceof DOMException && cause.name === 'AbortError')) {
        setProgress(en ? 'Connection interrupted; checking run status…' : '连接中断，正在核对任务状态…');
        try {
          const pendingRun = blankMode ? startedRunId : sessionStorage.getItem('secondbrain.chat.activeRun') ?? '';
          const pendingSession = blankMode ? sessionId : sessionStorage.getItem('secondbrain.chat.activeSession') ?? selected;
          if (pendingRun && pendingSession) await pollRun(pendingRun, pendingSession);
          else setError(cause instanceof Error ? chatFailureLabel(cause.message, locale) : chatFailureLabel('Chat failed', locale));
        } catch (recoveryError) { setError(recoveryError instanceof Error ? chatFailureLabel(recoveryError.message, locale) : chatFailureLabel('Could not recover run status', locale)); }
      }
    } finally {
      if (selectedSessionRef.current === sessionId && runSelectionIntent === selectionIntentRef.current) {
        abortRef.current = null; setRunId(''); setBusy(false);
      }
    }
  };

  const verifyCaptureApproval = async () => {
    const suggestion = captureSuggestion;
    if (!suggestion?.approvedProposalId || !suggestion.approvedProposalVersion || captureBusy
      || selectedSessionRef.current !== suggestion.sessionId) return;
    setCaptureBusy(true); setCaptureApproval(null); setCaptureFeedback('');
    const sequence = ++captureRequestSequence.current;
    try {
      const body = await api<unknown>(`/api/inbox/proposals/${encodeURIComponent(suggestion.approvedProposalId)}/history`);
      if (selectedSessionRef.current !== suggestion.sessionId || sequence !== captureRequestSequence.current) return;
      const approval = parseCaptureApproval(body, suggestion);
      if (!approval) throw new Error(en ? 'No current Core approval exactly matches this suggestion.' : '没有与此建议精确匹配且仍有效的 Core 批准记录。');
      setCaptureApproval(approval);
      setCaptureFeedback(en ? 'Current Core approval verified. This is not an Inbox write.' : '已核验当前 Core 批准；尚未写入 Inbox。');
    } catch (cause) {
      if (selectedSessionRef.current !== suggestion.sessionId || sequence !== captureRequestSequence.current) return;
      setCaptureFeedback(cause instanceof Error ? cause.message : (en ? 'Core approval could not be verified.' : '无法核验 Core 批准。'));
    } finally { if (sequence === captureRequestSequence.current) setCaptureBusy(false); }
  };

  const confirmCaptureSuggestion = async () => {
    const suggestion = captureSuggestion;
    const approval = captureApproval;
    if (!suggestion || !approval || captureBusy || captureConfirmation !== '确认收录'
      || selectedSessionRef.current !== suggestion.sessionId) return;
    setCaptureBusy(true); setCaptureFeedback(''); setCaptureSourceId(''); setCaptureStatus('');
    const receipt: CaptureReceipt = { sessionId: suggestion.sessionId, inboxId: '', sourceEventId: suggestion.sourceEventId,
      proposalId: approval.proposalId, proposalVersion: approval.version, sourceVersion: approval.sourceVersion, kind: approval.kind };
    const sequence = ++captureRequestSequence.current;
    try {
      const response = await fetch('/api/inbox/entries', { method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ original_text: suggestion.originalText,
          source_channel: 'web', source_event_id: suggestion.sourceEventId, occurred_at: suggestion.occurredAt,
          intent: 'approved_suggestion', approved_proposal_id: approval.proposalId,
          approved_proposal_version: approval.version }) });
      const result = await response.json().catch(() => ({})) as Record<string, unknown>;
      if (response.status !== 202) {
        if (response.status === 409) { setCaptureApproval(null); setCaptureConfirmation(''); }
        throw new Error(apiFailureLabel(result.detail, response.status, locale, 'chat'));
      }
      const inboxId = result.inbox_id;
      if (typeof inboxId !== 'string' || !captureIdPattern.test(inboxId) || typeof result.captured_at !== 'string'
        || Number.isNaN(Date.parse(result.captured_at)) || typeof result.replayed !== 'boolean'
        || result.intent !== 'approved_suggestion') throw new Error(en ? 'Core returned an invalid 202 receipt.' : 'Core 返回的 202 回执无效。');
      const completedReceipt = { ...receipt, inboxId };
      if (!parseCaptureReceiptResponse(result, completedReceipt)) throw new Error(en ? 'Core returned a mismatched or incomplete approval receipt.' : 'Core 返回的审批绑定回执不匹配或不完整。');
      if (selectedSessionRef.current !== suggestion.sessionId || sequence !== captureRequestSequence.current) return;
      try { sessionStorage.setItem(captureReceiptKey(suggestion.sessionId), JSON.stringify(completedReceipt)); }
      catch { throw new Error(en ? 'The exact receipt could not be saved for session recovery; confirm the status before retrying.' : '无法保存用于本会话恢复的精确回执；重试前请先核对状态。'); }
      setCaptureReceipt(completedReceipt); setCaptureSourceId(''); setCaptureStatus('');
      setCaptureFeedback(en ? 'Core accepted the receipt; verifying the exact Inbox entry…' : 'Core 已受理回执；正在核验确切的 Inbox 记录…');
      await verifyCaptureReceipt(completedReceipt, sequence);
    } catch (cause) {
      if (selectedSessionRef.current !== suggestion.sessionId || sequence !== captureRequestSequence.current) return;
      setCaptureFeedback(cause instanceof Error ? cause.message : (en ? 'Core could not verify this entry. The original remains available.' : 'Core 无法核验此记录，原文仍保留。'));
    } finally { if (sequence === captureRequestSequence.current) setCaptureBusy(false); }
  };

  const resolveRunToolApproval = async (choice: 'once' | 'deny') => {
    const approval = pendingApproval;
    if (!approval || approvalResolving) return;
    setApprovalResolving(true);
    try {
      await api(`/api/chat/sessions/${encodeURIComponent(approval.sessionId)}/runs/${encodeURIComponent(approval.runId)}/approval`, {
        method: 'POST', body: JSON.stringify({ approval_id: approval.approvalId,
          command_sha256: approval.commandSha256, choice }),
      });
      setPendingApproval(null);
      setProgress(choice === 'once'
        ? (en ? 'Approved once; waiting for the Run result.' : '已批准本次操作，等待运行结果。')
        : (en ? 'Rejected; this command was not authorized.' : '已拒绝，本次命令未获授权。'));
    } catch (cause) {
      // The request may have reached Core despite a broken response. Never retry an ambiguous one-use decision.
      setError(cause instanceof Error ? chatFailureLabel(cause.message, locale) : (en ? 'Approval status is unknown.' : '审批状态未知。'));
    }
  };

  const stop = async () => {
    if (!runId) return;
    try { await api(`/api/chat/runs/${encodeURIComponent(runId)}/stop`, { method: 'POST', body: '{}' }); }
    catch (cause) { setError(cause instanceof Error ? chatFailureLabel(cause.message, locale) : chatFailureLabel('Could not stop run', locale)); }
    const activeSession = blankMode ? selectedSessionRef.current : sessionStorage.getItem('secondbrain.chat.activeSession') ?? selected;
    setProgress(en ? 'Stopping…' : '正在停止…');
    try { await pollRun(runId, activeSession); }
    catch (cause) { setError(cause instanceof Error ? chatFailureLabel(cause.message, locale) : chatFailureLabel('Could not confirm stop status', locale)); }
    abortRef.current?.abort();
    setPendingApproval(null);
    setBusy(false); setRunId('');
  };

  const enterCaptureMode = (file?: File) => {
    if (file) setPendingAttachment(file);
    setAttachmentNotice('');
    setInputMode('capture');
  };
  const handleChatPaste = (event: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const item = Array.from(event.clipboardData.items).find((entry) => entry.type.startsWith('image/'));
    const blob = item?.getAsFile();
    if (!blob) return; // Native text paste remains unchanged.
    event.preventDefault();
    const extension = blob.type === 'image/jpeg' ? 'jpg' : (blob.type.split('/')[1] || 'png');
    const file = new File([blob], `pasted-image.${extension}`, { type: blob.type, lastModified: Date.now() });
    setPendingAttachment(file);
    setAttachmentNotice(en ? 'Hermes chat has no verified image attachment support. Choose “Switch to capture” to preserve this file.' : '目前尚未验证 Hermes 对话的图片附件解析。你可以选择“切换到收录”来保留此文件。');
  };
  const handleChatFile = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      setPendingAttachment(file);
      setAttachmentNotice(en ? 'Hermes chat attachment parsing is not verified. Switch to capture to continue.' : 'Hermes 对话附件解析尚未验证；如需处理此文件，请明确切换到收录。');
    }
    event.currentTarget.value = '';
  };
  const handleChatDrop = (event: React.DragEvent<HTMLFormElement>) => {
    const file = event.dataTransfer.files[0];
    if (!file) return;
    event.preventDefault(); setChatDragOver(false); setPendingAttachment(file);
    setAttachmentNotice(en ? 'This Hermes chat does not verify attachment parsing. Switch to capture to continue.' : '当前 Hermes 对话附件解析能力未验证；请明确切换到收录再继续。');
  };

  return <section className="chat-page">
    <aside className="chat-sessions"><div className="chat-session-heading"><h1>{blankMode ? (en ? 'Blank acceptance' : '空白验收') : (en ? 'Chat' : '对话')}</h1><button type="button" onClick={() => void newSession()}>{blankMode ? (en ? 'Create test session' : '创建合成会话') : (en ? 'New chat' : '新对话')}</button></div>
      {blankMode && <p className="chat-attachment-warning" role="status">{en ? 'This frontend entry avoids loading the regular session list. It does not isolate the authenticated backend account.' : '此入口仅避免前端加载普通会话列表，不提供已认证后端账户的服务端隔离。'}</p>}
      <div className="chat-session-list">{sessions.map((session) => <button type="button" key={session.id} className={session.id === selected ? 'is-selected' : ''} onClick={() => void selectSession(session.id)}><strong>{session.title}</strong><small>{session.updated ? formatDate(session.updated, locale) : session.id.slice(0, 16)}</small></button>)}</div></aside>
    <div className="chat-conversation"><header><div><p className="eyebrow">SECONDBRAIN <span>/</span> {blankMode ? (en ? 'BLANK ACCEPTANCE' : '空白验收') : (en ? 'CHAT' : '对话')}</p><h2>{sessions.find((session) => session.id === selected)?.title ?? (en ? 'New conversation' : '新对话')}</h2></div>{!blankMode && <button type="button" onClick={() => void forkSession()} disabled={!selected || busy}>{en ? 'Fork' : '分支会话'}</button>}</header>
      <div className="chat-message-list">{timeline.map((item) => item.type === 'message'
        ? <article key={item.id} className={`chat-message ${item.message.role}`}><span>{item.message.role === 'user' ? (en ? 'You' : '你') : 'Hermes'}</span><p>{item.message.text || (busy && item.message.role === 'assistant' ? progress : '')}</p></article>
        : <article key={item.id} className={`chat-activity-card status-${item.activity.status}`}>
          <div className="chat-activity-heading"><strong>{en ? 'System operation' : '系统操作'}</strong><span>{item.activity.status === 'succeeded' ? (en ? 'Succeeded' : '成功') : item.activity.status === 'failed' ? (en ? 'Failed' : '失败') : item.activity.status === 'processing' ? (en ? 'Processing' : '处理中') : (en ? 'Result unknown · retry safely' : '结果待确认 · 可安全重试')}</span></div>
          <p className="chat-activity-original">{item.activity.original_text}</p>
          <div className="chat-activity-detail">{item.activity.kind === 'journal'
            ? <><span>{en ? 'Journal' : '日记'}{item.activity.journal_date ? ` · ${item.activity.journal_date}` : ''}</span><button type="button" onClick={onGoJournal}>{en ? 'Open Journal' : '打开日记'}</button></>
            : <><span>{item.activity.task_title ?? (en ? 'Task' : '待办')}{item.activity.task_status ? ` · ${item.activity.task_status === 'completed' ? (en ? 'completed' : '已完成') : (en ? 'open' : '未完成')}` : ''}</span><button type="button" onClick={onGoToday}>{en ? 'Open Today' : '打开今日'}</button></>}
            <time>{activityTimeLabel(item.activity.occurred_at, locale)}</time>
          </div>
          {item.activity.detail && <small>{item.activity.detail}</small>}
        </article>)}{!timeline.length && <div className="chat-empty">{en ? 'Continue a Hermes session or start a new conversation.' : '继续 Hermes 会话，或开始新的对话。'}</div>}</div>
      {!blankMode && <ChatContextPreview preview={contextPreview} loading={contextPreviewLoading} error={contextPreviewError}
        onRefresh={() => void previewContext()} disabled={!selected || busy || input.trim().length === 0 || [...input.trim()].length > 200} locale={locale} />}
      {!blankMode && <ChatNaturalCandidates preview={naturalContext} loading={naturalContextLoading} error={naturalContextError} locale={locale} />}
      {!blankMode && <ChatGroundingCandidates sessionId={selected} query={input} locale={locale} disabled={!selected || busy} />}
      <ChatKnowledgeCitations bundles={citationBundles.filter((bundle) => bundle.session_id === selected)} loading={citationHistoryLoading}
        persistenceIssue={citationPersistenceIssue} locale={locale} />
      {!blankMode && selected && <PlanningPanel key={selected} locale={locale} sessionId={selected} />}
      {journalInboxAttempt?.sessionId === selected && <section className="chat-capture-suggestion" aria-label={en ? 'Journal intent retry status' : '日记意图重试状态'}>
        <h3>{en ? 'Inbox save is not confirmed' : 'Inbox 保存结果尚未确认'}</h3>
        <p role="alert">{journalInboxFeedback || (en ? 'The original text and exact request are retained.' : '原文和完整请求已保留。')}</p>
        <button type="button" disabled={busy} onClick={() => void submitJournalIntentToInbox(journalInboxAttempt.body.original_text)}>{en ? 'Retry the same request' : '使用同一请求重试'}</button>
      </section>}
      {journalInboxReceipt?.sessionId === selected && <section className="chat-capture-suggestion" aria-label={en ? 'Journal intent Inbox receipt' : '日记意图 Inbox 回执'}>
        <h3>{en ? 'Original text saved to Inbox' : '原文已保存到 Inbox'}</h3>
        <p>{en ? 'This is a pending Inbox entry only. No Journal entry has been created.' : '这只表示原文进入待处理 Inbox；尚未创建 Journal 日记。'}</p>
        {journalInboxStatus && <p role="status">{en ? 'Verified Inbox status' : '已核验 Inbox 状态'}: {journalInboxStatus}</p>}
        {journalInboxFeedback && !journalInboxStatus && <p role="alert">{journalInboxFeedback}</p>}
        <button type="button" disabled={busy} onClick={() => {
          const sequence = ++journalInboxSequenceRef.current;
          setJournalInboxStatus('');
          setJournalInboxFeedback(en ? 'Checking the exact Inbox entry using a read-only request…' : '正在通过只读请求核对确切的 Inbox 记录…');
          void verifyJournalInboxReceipt(journalInboxReceipt, sequence);
        }}>{en ? 'Refresh Inbox status' : '刷新 Inbox 状态'}</button>
        {journalInboxStatus && <a href={`/inbox#capture-${encodeURIComponent(journalInboxReceipt.inboxId)}`}>{en ? 'Open Inbox entry' : '打开 Inbox 条目'}</a>}
      </section>}
      {captureSuggestion?.sessionId === selected && <section className="chat-capture-suggestion" aria-label={en ? 'Hermes capture suggestion' : 'Hermes 收录建议'}>
        <h3>{en ? 'Hermes suggests saving this to Inbox' : 'Hermes 建议将以下内容收录到 Inbox'}</h3>
        <p>{en ? 'A chat suggestion and typed confirmation are not Core approval. Verify a current Core-approved proposal before submitting.' : '聊天建议和输入确认短语都不等于 Core 批准；提交前必须核验仍有效的 Core 批准记录。'}</p>
        <blockquote>{captureSuggestion.originalText}</blockquote>
        {!captureApproval && !captureSourceId && !captureReceipt && <>
          {captureSuggestion.approvedProposalId && captureSuggestion.approvedProposalVersion
            ? <button type="button" disabled={captureBusy} onClick={() => void verifyCaptureApproval()}>{captureBusy ? (en ? 'Checking Core approval…' : '正在核验 Core 批准…') : (en ? 'Verify current Core approval' : '核验当前 Core 批准')}</button>
            : <p role="status">{en ? 'No Core-approved proposal ID and version are attached. Submission is disabled.' : '缺少 Core 已批准 Proposal ID 与版本，已禁用提交。'}</p>}
        </>}
        {captureApproval && !captureSourceId && !captureReceipt && <><p role="status">{en ? `Core approval verified: ${captureApproval.kind}, version ${captureApproval.version}.` : `已核验 Core 批准：${captureApproval.kind}，版本 ${captureApproval.version}。`}</p><label htmlFor="capture-suggestion-confirm">{en ? 'Type “确认收录” to continue' : '输入“确认收录”以继续'}</label>
          <input id="capture-suggestion-confirm" value={captureConfirmation} onChange={(event) => setCaptureConfirmation(event.target.value)} autoComplete="off" />
          <button type="button" disabled={captureBusy || captureConfirmation !== '确认收录'} onClick={() => void confirmCaptureSuggestion()}>{captureBusy ? (en ? 'Submitting…' : '正在提交…') : (en ? 'Confirm and submit to Core' : '确认并提交给 Core')}</button></>}
        {captureFeedback && <p role={captureSourceId ? 'status' : 'alert'}>{captureFeedback}{captureStatus ? ` · ${en ? 'Status' : '状态'}: ${captureStatus}` : ''}</p>}
        {captureReceipt && captureReceipt.sessionId === selected && <button type="button" disabled={captureBusy} onClick={() => void verifyCaptureReceipt(captureReceipt, ++captureRequestSequence.current)}>{en ? 'Refresh Core status' : '刷新 Core 状态'}</button>}
        {captureSourceId && <a href={`/inbox#capture-${encodeURIComponent(captureSourceId)}`}>{en ? 'Open Inbox source' : '打开 Inbox 来源'}</a>}
      </section>}
      {!captureSuggestion && captureReceipt?.sessionId === selected && <section className="chat-capture-suggestion" aria-label={en ? 'Inbox capture status' : 'Inbox 收录状态'}>
        <h3>{en ? 'Inbox entry for this session' : '本会话的 Inbox 记录'}</h3>
        {captureFeedback && <p role={captureStatus ? 'status' : 'alert'}>{captureFeedback}{captureStatus ? ` · ${en ? 'Status' : '状态'}: ${captureStatus}` : ''}</p>}
        <button type="button" disabled={captureBusy} onClick={() => void verifyCaptureReceipt(captureReceipt, ++captureRequestSequence.current)}>{en ? 'Refresh Core status' : '刷新 Core 状态'}</button>
        {captureSourceId && <a href={`/inbox#capture-${encodeURIComponent(captureSourceId)}`}>{en ? 'Open Inbox source' : '打开 Inbox 来源'}</a>}
      </section>}
      {progress && <div className="chat-progress" role="status">{progress}</div>}{error && <p className="chat-error" role="alert">{error}</p>}
      {pendingApproval && <section className="terminal-approval-card" aria-labelledby="terminal-approval-title">
        <h3 id="terminal-approval-title">{en ? 'Run action approval' : '运行操作审批'}</h3>
        <p>{pendingApproval.scope}</p>
        <p>{en ? 'Review the exact request. Approval applies once to this Run and this tool call only.' : '请核对完整请求；批准仅对本次 Run 的这一次工具调用生效。'}</p>
        <pre>{pendingApproval.command}</pre>
        {pendingApproval.workdir && <p>{en ? 'Working directory: ' : '工作目录：'}<code>{pendingApproval.workdir}</code></p>}
        <details open={pendingApproval.tool === 'write_file' || pendingApproval.tool === 'patch'}><summary>{en ? 'All tool arguments' : '完整工具参数'}</summary><pre>{JSON.stringify(pendingApproval.arguments, null, 2)}</pre></details>
        {pendingApproval.tool === 'terminal' || pendingApproval.tool === 'process_manage' || pendingApproval.tool === 'execute_code'
          ? <p className="terminal-approval-warning">{en ? 'This is not an OS sandbox. The approved action runs with Hermes worker permissions.' : '这不是操作系统沙箱。获批操作会以 Hermes worker 的系统权限运行。'}</p>
          : <p className="terminal-approval-warning">{en ? 'Only this exact file operation is approved. Knowledge, Private, Hermes state, and Skills protections remain in force.' : '批准仅覆盖这一次精确文件操作；Knowledge、Private、Hermes 状态及 Skills 保护仍有效。'}</p>}
        <div><button type="button" disabled={approvalResolving} onClick={() => void resolveRunToolApproval('once')}>{en ? 'Approve once' : '批准一次'}</button>
          <button type="button" disabled={approvalResolving} onClick={() => void resolveRunToolApproval('deny')}>{en ? 'Reject' : '拒绝'}</button></div>
      </section>}
      <div className="unified-mode-switch" role="group" aria-label={en ? 'Input destination' : '输入去向'}><button type="button" className={inputMode === 'chat' ? 'is-active' : ''} onClick={() => setInputMode('chat')}>{en ? 'Chat' : '对话'}</button><button type="button" className={inputMode === 'capture' ? 'is-active' : ''} onClick={() => setInputMode('capture')}>{en ? 'Save to SecondBrain' : '收录到第二大脑'}</button></div>
      {inputMode === 'chat' ? <form className={`chat-composer ${chatDragOver ? 'is-drag-over' : ''}`} onSubmit={send} onDragOver={(event) => { if (event.dataTransfer.types.includes('Files')) { event.preventDefault(); setChatDragOver(true); } }} onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setChatDragOver(false); }} onDrop={handleChatDrop}><textarea value={input} onChange={(event) => setInput(event.target.value)} onPaste={handleChatPaste} placeholder={en ? 'Message Hermes…' : '发送消息给 Hermes…'} rows={3} disabled={busy} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && event.nativeEvent.keyCode !== 229) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} /><div><small>{en ? 'Enter to send · Shift+Enter for a new line' : 'Enter 发送 · Shift+Enter 换行'}</small><button type="button" onClick={() => attachmentInput.current?.click()} disabled={busy}>{en ? '＋ Attachment' : '＋ 附件'}</button><input ref={attachmentInput} className="unified-file-input" type="file" accept=".txt,.md,.markdown,.pdf,.png,.jpg,.jpeg,.webp,.gif,.wav,.mp3,.m4a,.aac,.ogg,.flac" onChange={handleChatFile} />{busy ? <button type="button" onClick={() => void stop()} disabled={!runId}>{en ? 'Stop' : '停止'}</button> : <button type="submit" disabled={!input.trim() || Boolean(pendingAttachment)}>{en ? 'Send' : '发送'}</button>}</div>{pendingAttachment && <div className="chat-attachment-warning" role="status">{pendingPreview && <img src={pendingPreview} alt={pendingAttachment.name} />}<span>{pendingAttachment.name} · {(pendingAttachment.size / 1048576).toFixed(2)} MiB</span><button type="button" onClick={() => enterCaptureMode(pendingAttachment)}>{en ? 'Switch to capture' : '切换到收录'}</button><button type="button" onClick={() => { setPendingAttachment(null); setAttachmentNotice(''); }}>{en ? 'Remove' : '移除'}</button></div>}{attachmentNotice && <p className="chat-attachment-warning" role="status">{attachmentNotice}</p>}</form> : <UnifiedCaptureComposer key={pendingAttachment ? `${pendingAttachment.name}-${pendingAttachment.lastModified}` : 'capture'} locale={locale} onComplete={() => window.dispatchEvent(new Event('sb-inbox-refresh'))} onGoInbox={onGoInbox} initialFile={pendingAttachment} initialValue={input} onDraftChange={setInput} onAttachmentChange={setPendingAttachment} onAttachmentConsumed={() => setPendingAttachment(null)} />}
    </div>
  </section>;
}

type OrganizeSettings = { enabled: boolean; mode: 'fixed_time' | 'interval'; interval_hours: number; daily_time: string; timezone: string };
type OrganizerModelSettings = { provider: 'siliconflow'; model: string; model_enabled: boolean; scheduler_enabled: boolean; monthly_soft_budget_cny: number; api_key_configured: boolean };
type OrganizeStatus = { execution_available: boolean; state: string; last_run_at?: string | null; next_run_at?: string | null; configured_next_run_at?: string | null; last_draft_count?: number | null; last_error?: { message?: string } | null; blocked_reason?: string; coverage_warnings?: { session_id: string; state: string }[]; budget?: { daily_requests?: number; daily_limit?: number; daily_remaining?: number; monthly_estimated_cny?: number; monthly_soft_limit_cny?: number; monthly_remaining_estimate_cny?: number } };

function organizerTime(value: string | null | undefined, locale: Locale) {
  if (!value) return locale === 'en' ? 'None' : '尚无记录';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? (locale === 'en' ? 'Unknown' : '时间未知') : date.toLocaleString(locale === 'en' ? 'en-US' : 'zh-CN');
}

export function AutomationSettingsPage({ locale }: { locale: Locale }) {
  const en = locale === 'en';
  const [settings, setSettings] = useState<OrganizeSettings | null>(null);
  const [status, setStatus] = useState<OrganizeStatus | null>(null);
  const [modelSettings, setModelSettings] = useState<OrganizerModelSettings | null>(null);
  const [apiKey, setApiKey] = useState('');
  const [reason, setReason] = useState('');
  const [message, setMessage] = useState('');
  const [mockMessage, setMockMessage] = useState('');
  const [saving, setSaving] = useState(false);
  const [mockCheck, setMockCheck] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  useEffect(() => {
    void Promise.all([
      fetch('/api/automation/organize/settings', { credentials: 'same-origin' }).then((response) => response.ok ? response.json() : Promise.reject(new Error('settings_unavailable'))),
      fetch('/api/automation/organize/status', { credentials: 'same-origin' }).then((response) => response.ok ? response.json() : Promise.reject(new Error('status_unavailable'))),
      fetch('/api/automation/organize/model-settings', { credentials: 'same-origin' }).then((response) => response.ok ? response.json() : Promise.reject(new Error('model_settings_unavailable'))),
    ]).then(([config, currentStatus, modelConfig]) => { setSettings(config); setStatus(currentStatus); setReason(String(currentStatus.blocked_reason ?? '')); setModelSettings(modelConfig); })
      .catch(() => setMessage(en ? 'Settings could not be loaded.' : '自动整理设置暂时无法读取。'));
  }, [en]);
  const update = (values: Partial<OrganizeSettings>) => setSettings((current) => current ? { ...current, ...values } : current);
  const save = async () => {
    if (!settings || !modelSettings || saving) return;
    setSaving(true); setMessage('');
    try {
      const response = await fetch('/api/automation/organize/settings', { method: 'PUT', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(settings) });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) { setMessage(en ? 'Settings could not be saved.' : '设置保存失败，请稍后重试。'); return; }
      setSettings(payload); setMessage(en ? 'Settings saved.' : '设置已保存。');
      const modelResponse = await fetch('/api/automation/organize/model-settings', { method: 'PUT', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(modelSettings) });
      const modelPayload = await modelResponse.json().catch(() => ({}));
      if (!modelResponse.ok) { setMessage(en ? 'Model settings could not be saved.' : '模型设置保存失败。'); return; }
      setModelSettings(modelPayload);
      void fetch('/api/automation/organize/status', { credentials: 'same-origin' }).then((result) => result.ok ? result.json() : null)
        .then((currentStatus) => { if (currentStatus) { setStatus(currentStatus); setReason(String(currentStatus.blocked_reason ?? '')); } }).catch(() => undefined);
    } catch { setMessage(en ? 'Settings could not be saved.' : '设置保存失败，请稍后重试。'); }
    finally { setSaving(false); }
  };
  const saveKey = async () => {
    if (!apiKey || saving) return;
    setSaving(true); setMessage('');
    try {
      const response = await fetch('/api/automation/organize/api-key', { method: 'PUT', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ api_key: apiKey }) });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) { setMessage(en ? 'API key could not be saved.' : 'API Key 保存失败。'); return; }
      setApiKey(''); setModelSettings((current) => current ? { ...current, api_key_configured: Boolean(payload.api_key_configured) } : current);
      setMessage(en ? 'API key saved; its value is not shown again.' : 'API Key 已安全保存，不会再次显示。');
    } catch { setMessage(en ? 'API key could not be saved.' : 'API Key 保存失败。'); }
    finally { setSaving(false); }
  };
  const deleteKey = async () => {
    if (!modelSettings || saving) return;
    setSaving(true);
    try {
      const response = await fetch('/api/automation/organize/api-key', { method: 'DELETE', credentials: 'same-origin' });
      if (!response.ok) { setMessage(en ? 'API key could not be deleted.' : 'API Key 删除失败。'); return; }
      setModelSettings({ ...modelSettings, api_key_configured: false, model_enabled: false });
      setMessage(en ? 'API key deleted.' : 'API Key 已删除。');
    } catch { setMessage(en ? 'API key could not be deleted.' : 'API Key 删除失败。'); }
    finally { setSaving(false); }
  };
  const mockConnectionTest = async () => {
    if (mockCheck === 'loading' || saving) return;
    setMockCheck('loading');
    setMockMessage('');
    try {
      const response = await fetch('/api/automation/organize/connection-test', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = typeof payload.detail === 'string' ? payload.detail : '';
        setMockMessage(detail || (response.status === 401 || response.status === 403
          ? (en ? 'Your session expired or is not authorized. Sign in again and retry.' : '登录已失效或无权检查，请重新登录后重试。')
          : (en ? `Local mock check failed (HTTP ${response.status}).` : `本地 Mock 检查失败（HTTP ${response.status}）。`)));
        setMockCheck('error');
        return;
      }
      if (payload.kind !== 'local_mock') throw new Error('unexpected_check_response');
      setMockMessage(en
        ? 'Local mock check passed. SiliconFlow was not contacted; no provider charges were incurred.'
        : '本地 Mock 检查通过，未连接 SiliconFlow，不产生供应商费用。');
      setMockCheck('success');
    } catch {
      setMockMessage(en ? 'Could not reach the local check API. Check your connection and retry.' : '无法连接本地检查接口，请检查网络后重试。');
      setMockCheck('error');
    }
  };
  return <section className="automation-settings-page">
    <header><p className="eyebrow">SECONDBRAIN <span>/</span> {en ? 'SETTINGS' : '设置'}</p><h1>{en ? 'AI smart organization' : 'AI 智能整理'}</h1><p>{en ? 'Choose how new Hermes conversations may be proposed as Review drafts.' : '设置如何从新增 Hermes 对话中提取 Review 草稿。'}</p></header>
    {!settings || !modelSettings ? <p role="status">{message || (en ? 'Loading…' : '正在加载…')}</p> : <>
      <div className="organizer-settings-grid">
      <section className="organizer-settings-card organizer-model-settings" aria-label={en ? 'Organizer model settings' : 'Organizer 模型设置'}>
        <h2>{en ? 'Model configuration' : '模型配置'}</h2>
        <div className="organizer-readonly-field"><span>{en ? 'Provider' : '服务商'}</span><output>SiliconFlow</output></div>
        <div className="organizer-readonly-field"><span>{en ? 'Supported model' : '当前支持模型'}</span><output>deepseek-ai/DeepSeek-V4-Flash</output></div>
        <p className="organizer-note">{en ? 'This is the only verified model currently supported.' : '当前仅支持此已验证模型。'}</p>
        <div className="organizer-key-row"><span>{en ? 'API key' : 'API Key'}：{modelSettings.api_key_configured ? (en ? 'Configured' : '已配置') : (en ? 'Not configured' : '未配置')}</span><button type="button" disabled={!modelSettings.api_key_configured || saving} onClick={() => void deleteKey()}>{en ? 'Delete key' : '删除密钥'}</button></div>
        <label className="organizer-input-label">{en ? 'Set or replace API key' : '设置或替换 API Key'} <input type="password" autoComplete="new-password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} /></label>
        <div className="organizer-actions"><button type="button" disabled={!apiKey || saving} onClick={() => void saveKey()}>{en ? 'Save key' : '保存密钥'}</button><button type="button" disabled={saving || mockCheck === 'loading'} onClick={() => void mockConnectionTest()}>{mockCheck === 'loading' ? (en ? 'Checking…' : '检查中…') : (en ? 'Run local mock check' : '执行本地 Mock 检查')}</button></div>
        <p className="organizer-note">{en ? 'Mock check only verifies local configuration; it never contacts SiliconFlow.' : 'Mock 检查仅验证本地配置，不会连接 SiliconFlow。'}</p>
        {mockCheck === 'loading' && <p className="organizer-check-result" role="status">{en ? 'Checking local configuration…' : '正在检查本地配置…'}</p>}
        {mockCheck !== 'idle' && mockCheck !== 'loading' && <p className={`organizer-check-result ${mockCheck}`} role={mockCheck === 'error' ? 'alert' : 'status'}>{mockMessage}</p>}
      </section>

      <section className="organizer-settings-card organizer-run-settings">
        <h2>{en ? 'Automatic organization' : '自动整理'}</h2>
        <label className="automation-toggle"><input type="checkbox" checked={modelSettings.model_enabled} onChange={(event) => setModelSettings({ ...modelSettings, model_enabled: event.target.checked })} />{en ? 'Enable model for manual runs' : '允许手动整理使用模型'}</label>
        <label className="automation-toggle"><input type="checkbox" checked={modelSettings.scheduler_enabled} onChange={(event) => setModelSettings({ ...modelSettings, scheduler_enabled: event.target.checked })} />{en ? 'Enable Scheduler' : '启用 Scheduler'}</label>
        <label className="automation-toggle"><input type="checkbox" checked={settings.enabled} onChange={(event) => update({ enabled: event.target.checked })} />{en ? 'Allow scheduled runs' : '允许按计划整理'}</label>
        <fieldset><legend>{en ? 'Schedule' : '执行计划'}</legend>
        <label><input type="radio" name="organize-mode" checked={settings.mode === 'interval'} onChange={() => update({ mode: 'interval' })} />{en ? 'Every interval' : '按固定间隔'}</label>
        {settings.mode === 'interval' && <select aria-label={en ? 'Interval in hours' : '间隔小时数'} value={settings.interval_hours} onChange={(event) => update({ interval_hours: Number(event.target.value) })}>{[1, 2, 3, 4, 6, 8, 12, 24].map((hours) => <option key={hours} value={hours}>{en ? `Every ${hours} hours` : `每 ${hours} 小时`}</option>)}</select>}
        <label><input type="radio" name="organize-mode" checked={settings.mode === 'fixed_time'} onChange={() => update({ mode: 'fixed_time' })} />{en ? 'Daily at a fixed time' : '每天固定时间'}</label>
        {settings.mode === 'fixed_time' && <input aria-label={en ? 'Daily time' : '每天执行时间'} type="time" value={settings.daily_time} onChange={(event) => update({ daily_time: event.target.value })} />}
        <p>{en ? `Time zone: ${settings.timezone}` : `时区：${settings.timezone}`}</p>
        </fieldset>
      </section>

      <section className="organizer-settings-card organizer-budget-settings">
        <h2>{en ? 'Budget and activity' : '预算与运行'}</h2>
        <dl className="organizer-budget-grid">
          <div><dt>{en ? 'Monthly soft limit' : '月度软预算'}</dt><dd>¥{modelSettings.monthly_soft_budget_cny}</dd></div>
          <div><dt>{en ? 'Estimated remaining' : '估算剩余'}</dt><dd>¥{status?.budget?.monthly_remaining_estimate_cny ?? modelSettings.monthly_soft_budget_cny}</dd></div>
          <div><dt>{en ? 'Today’s requests' : '今日请求'}</dt><dd>{status?.budget?.daily_requests ?? 0}/{status?.budget?.daily_limit ?? 12} · {status?.budget?.daily_remaining ?? 12} {en ? 'left' : '次剩余'}</dd></div>
          <div><dt>{en ? 'Estimated spend' : '本月估算用量'}</dt><dd>¥{status?.budget?.monthly_estimated_cny ?? 0}</dd></div>
        </dl>
        <p className="organizer-note">{en ? 'Local estimates are not provider billing.' : '本地估算不等于供应商账单。'}</p>
      <dl className="automation-status-list"><div><dt>{en ? 'Current state' : '当前状态'}</dt><dd>{status?.execution_available ? (status.state === 'running' ? (en ? 'Running' : '运行中') : status.state === 'needs_attention' ? (en ? 'Needs attention' : '需要核对') : status.state === 'disabled' ? (en ? 'Disabled' : '已停用') : (en ? 'Scheduled' : '等待执行')) : (en ? 'Settings only; automatic organization has not run.' : '仅保存设置，自动整理尚未运行。')}</dd></div><div><dt>{en ? 'Last run' : '上次执行'}</dt><dd>{organizerTime(status?.last_run_at, locale)}</dd></div><div><dt>{en ? 'Next estimate' : '下次预计执行'}</dt><dd>{status?.execution_available ? organizerTime(status.next_run_at, locale) : (status?.configured_next_run_at ? `${en ? 'Saved plan (not active): ' : '设置的计划时间（尚未运行）：'}${organizerTime(status.configured_next_run_at, locale)}` : (en ? 'Unavailable until the runner is verified' : '执行器通过验证前不可用'))}</dd></div><div><dt>{en ? 'New drafts last run' : '上次新增草稿'}</dt><dd>{status?.last_draft_count ?? '—'}</dd></div></dl>
      </section>
      </div>
      {reason && <p className="automation-blocked" role="status">{reason}</p>}
      {status?.last_error?.message && <p className="automation-blocked" role="alert">{status.last_error.message}</p>}
      {Boolean(status?.coverage_warnings?.length) && <p className="automation-blocked" role="status">{en ? 'Some source sessions are unavailable or discontinuous; their missing history will not be skipped.' : '部分来源会话已删除或历史不连续；系统不会静默跳过缺失消息。'}</p>}
      <button type="button" onClick={() => void save()} disabled={saving}>{saving ? (en ? 'Saving…' : '正在保存…') : (en ? 'Save settings' : '保存设置')}</button>
      {message && <p role="status">{message}</p>}
    </>}
  </section>;
}

function localizeStatus(status: string, locale: Locale) {
  if (status.toLowerCase() === 'online') return locale === 'en' ? 'Online' : '在线';
  return status;
}

function Icon({ name, size = 18 }: { name: string; size?: number }) {
  const paths: Record<string, string[]> = {
    brain: ['M9 4.5a3 3 0 0 0-5.5 1.6A3.2 3.2 0 0 0 4 12a3.2 3.2 0 0 0 2.5 5.4A3 3 0 0 0 12 17V7a2.5 2.5 0 0 0-3-2.5Z', 'M15 4.5a3 3 0 0 1 5.5 1.6A3.2 3.2 0 0 1 20 12a3.2 3.2 0 0 1-2.5 5.4A3 3 0 0 1 12 17V7a2.5 2.5 0 0 1 3-2.5Z', 'M8 9h1M15 9h1M8 14h1M15 14h1'],
    home: ['m3 10 9-7 9 7', 'M5 9v11h14V9', 'M9 20v-6h6v6'], message: ['M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8v.5Z'],
    calendar: ['M8 2v4M16 2v4M3 10h18', 'M5 4h14a2 2 0 0 1 2 2v14H3V6a2 2 0 0 1 2-2Z', 'M8 14h3v3H8z'], inbox: ['M4 4h16v16H4z', 'M4 13h4l2 3h4l2-3h4'], check: ['M20 6 9 17l-5-5'], folder: ['M3 6a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z', 'M3 9h18'],
    book: ['M4 5.5A2.5 2.5 0 0 1 6.5 3H20v17H6.5A2.5 2.5 0 0 1 4 17.5z', 'M4 17.5A2.5 2.5 0 0 1 6.5 15H20'], file: ['M14 2H6a2 2 0 0 0-2 2v16h16V8z', 'M14 2v6h6', 'M8 13h8M8 17h8'], activity: ['M22 12h-4l-3 9L9 3l-3 9H2'], journal: ['M5 3h14v18H5z', 'M8 7h8M8 11h8M8 15h5'], settings: ['M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z', 'm19.4 15 .1.1 1.4 1.1-1.4 2.4-1.8-.5a8 8 0 0 1-1.4.8l-.3 1.9h-2.8l-.4-1.8a8 8 0 0 1-1.5-.8l-1.8.5-1.4-2.4 1.4-1.2a8 8 0 0 1 0-1.7l-1.4-1.2 1.4-2.4 1.8.5a8 8 0 0 1 1.5-.8l.4-1.8H16l.4 1.8a8 8 0 0 1 1.4.8l1.8-.5 1.4 2.4-1.4 1.2a8 8 0 0 1-.2 1.6Z'],
    notes: ['M5 3h14v18H5z', 'M8 7h8M8 11h8M8 15h5'], chevron: ['m7 10 5 5 5-5'], chevrons: ['m7 10 5-5 5 5', 'm7 14 5 5 5-5'], menu: ['M4 6h16M4 12h16M4 18h16'], close: ['m6 6 12 12M18 6 6 18'], bolt: ['m13 2-3 8h7l-6 12 2-9H6z'], capture: ['M12 20h9', 'M16.5 3.5a2.1 2.1 0 0 1 3 3L9 17l-4 1 1-4z'],
  };
  return <svg className={`icon icon-${name}`} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{(paths[name] ?? paths.file).map((d, i) => <path key={i} d={d} />)}</svg>;
}

function ClockWeather({ locale }: { locale: Locale }) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => { const timer = window.setInterval(() => setNow(new Date()), 60_000); return () => window.clearInterval(timer); }, []);
  const date = now.toLocaleDateString(locale === 'en' ? 'en-US' : 'zh-CN', { weekday: 'long', month: 'long', day: 'numeric' });
  return <div className="clock-card" aria-label="Local date and demo weather">
    <strong>{now.toLocaleTimeString(locale === 'en' ? 'en-US' : 'zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })}</strong>
    <span>{date}</span>
    <span className="weather-line"><Icon name="activity" size={12} />{DEMO_WEATHER.city} · {DEMO_WEATHER.temperature}<em>{DEMO_WEATHER.label}</em></span>
  </div>;
}

function MiniChart({ type }: { type: 'bars' | 'line' | 'orb' }) {
  if (type === 'orb') return <img className="mini-chart-agent" src={hermesOrbUrl} alt="" aria-hidden="true" />;
  if (type === 'line') return <svg className="mini-chart line-chart" viewBox="0 0 120 48" aria-hidden="true"><defs><linearGradient id="sb-line-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="currentColor" stopOpacity=".42"/><stop offset="1" stopColor="currentColor" stopOpacity="0"/></linearGradient></defs><path className="chart-area" d="M5 35 Q25 33 39 23 T66 24 Q81 18 92 12 T116 6 V47 H5Z"/><path className="chart-stroke" d="M5 35 Q25 33 39 23 T66 24 Q81 18 92 12 T116 6"/><circle cx="66" cy="24" r="2.6"/><circle cx="92" cy="12" r="2.6"/><circle cx="116" cy="6" r="3.3"/></svg>;
  const bars = [{ h: 14, x: 2 }, { h: 20, x: 13 }, { h: 28, x: 24 }, { h: 18, x: 35 }, { h: 32, x: 46 }, { h: 40, x: 57 }, { h: 34, x: 68 }, { h: 26, x: 79 }, { h: 30, x: 90 }, { h: 22, x: 101 }];
  return <svg className="mini-chart bar-chart" viewBox="0 0 110 42" aria-hidden="true"><defs><linearGradient id="sb-bars-gradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#38bdf8"/><stop offset="1" stopColor="#0284c7" stopOpacity=".2"/></linearGradient></defs>{bars.map((bar, index) => <rect key={index} x={bar.x} y={42 - bar.h} width="6.5" height={bar.h} rx="3" />)}</svg>;
}

function KpiCard({ icon, tone, title, value, detail, source, chart, locale, demoDelta }: { icon: string; tone: string; title: string; value: string; detail: string; source: DataKind; chart: 'bars' | 'line' | 'orb'; locale: Locale; demoDelta?: number }) {
  const badge = source === 'REAL' ? 'REAL' : source === 'DEMO' ? 'DEMO' : '—';
  return <article className={`kpi-card tone-${tone}`}>
    <div className="kpi-top"><span className={`kpi-icon icon-tile ${tone}`}><Icon name={icon} size={17} /></span><span className="kpi-label">{title}</span><span className={`source-badge ${source.toLowerCase()}`}>{badge}</span></div>
    <div className="kpi-main"><div className="kpi-value-copy"><strong className={`kpi-value ${chart === 'orb' ? 'kpi-value-status' : 'kpi-value-number'} ${source === 'UNAVAILABLE' ? 'is-unavailable' : ''}`}>{value}</strong><small>{detail}</small>{demoDelta !== undefined && <span className="kpi-demo-delta"><i aria-hidden="true">↑</i> +{demoDelta} · DEMO <small>{messages[locale].demoDelta}</small></span>}</div><div className="kpi-chart-slot"><MiniChart type={chart} /></div></div>
    <span className="chart-caption">{chart === 'orb' ? (source === 'REAL' ? 'LIVE · REAL' : '—') : `${locale === 'en' ? 'Trend' : '趋势'} · DEMO`}</span>
  </article>;
}

function Donut({ locale }: { locale: Locale }) {
  return <article className="donut-card">
    <div className="donut-heading"><div className="icon-tile source-icon"><Icon name="activity" size={16} /></div><div><strong>{locale === 'en' ? 'Source mix' : '知识来源'}</strong><small>DEMO</small></div></div>
    <div className="donut-body"><div className="donut-graphic"><div className="donut-center"><strong>DEMO</strong><small>{locale === 'en' ? 'visual only' : '视觉示意'}</small></div></div>
      <div className="legend">{DEMO_SOURCE_SPLIT.map((item) => <span key={item.label}><i style={{ background: item.color }} />{item.label}<b>{item.value}%</b></span>)}</div>
    </div>
  </article>;
}

function ModuleTitle({ title, icon, trailing }: { title: string; icon: string; trailing?: React.ReactNode }) {
  return <div className="module-title"><span className={`module-icon ${icon}`}><Icon name={icon} size={17} /></span><h2>{title}</h2>{trailing ?? <span className="module-menu" aria-hidden="true">•••</span>}</div>;
}

function TodayCard({ state, locale, onViewCalendar, onCreateTask }: { state: ReturnType<typeof adaptHome>['today']; locale: Locale; onViewCalendar: () => void; onCreateTask: () => void }) {
  const t = messages[locale];
  return <article className="dashboard-card today-card" id="today">
    <img className="today-background" src={todayLandscapeUrl} alt="" aria-hidden="true" />
    <ModuleTitle title={t.today} icon="calendar" trailing={<button type="button" className="card-link" onClick={onViewCalendar} aria-label={t.viewCalendar}>{t.viewAll}<Icon name="chevron" size={14} /></button>} />
    <p className="today-description">{t.todayDescription}</p>
    {state.kind === 'content' ? <div className="today-items">{state.items.map((item, index) => <div className="today-item" key={`${item.title}-${index}`}><span className="timeline-dot"/><strong>{item.title}</strong></div>)}</div>
      : state.kind === 'empty' ? <IllustratedEmpty locale={locale} onCreateTask={onCreateTask} />
      : <div className="unknown-state"><span className="unknown-icon">?</span><strong>{t.noTodayData}</strong><small>UNAVAILABLE</small></div>}
  </article>;
}

function IllustratedEmpty({ locale, onCreateTask }: { locale: Locale; onCreateTask: () => void }) {
  const t = messages[locale];
  return <div className="illustrated-empty">
    <div className="empty-calendar"><Icon name="calendar" size={37} /></div>
    <strong>{t.emptyTitle}</strong><p>{t.emptyDescription}</p>
    <button type="button" className="coming-button" onClick={onCreateTask}><Icon name="capture" size={15} />{t.create}</button>
  </div>;
}

function ReviewCard({ title, items, pendingCount, source, locale }: { title: string; items: ListItem[]; pendingCount: number | null; source: DataKind; locale: Locale }) {
  const t = messages[locale];
  return <article className="dashboard-card review-card" id="waiting">
    <ModuleTitle title={title} icon="check" trailing={<span className="review-count">{pendingCount === null ? '—' : pendingCount} <small>{t.pending}</small></span>} />
    <div className="card-subheading"><span className="status-light" />{source === 'REAL' ? `${items.length} ${locale === 'en' ? 'items' : '条待审核内容'}` : t.unavailable} <span className={`source-badge ${source === 'REAL' ? 'real' : 'unavailable'}`}>{source}</span></div>
    {items.length ? <div className="review-list">{items.slice(0, 5).map((item, index) => <div className="review-row" key={`${item.title}-${index}`}>
      <span className={`review-icon review-tone-${index % 4}`}><Icon name={index % 2 ? 'file' : 'check'} size={14} /></span>
      <strong title={item.title}>{item.title}</strong>
      {formatDate(item.updated, locale) && <small>{formatDate(item.updated, locale)}</small>}
      <b>{item.status || t.statusUnavailable}</b>
    </div>)}</div> : <EmptyInline text={t.empty} />}
  </article>;
}

function formatDate(value: ListItem['updated'], locale: Locale) {
  if (value === undefined || value === null || value === '') return '';
  const date = typeof value === 'number' ? new Date(value < 10_000_000_000 ? value * 1000 : value) : new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleDateString(locale === 'en' ? 'en-US' : 'zh-CN', { month: 'numeric', day: 'numeric' });
}

function ListCard({ id, title, items, kind, source, locale }: { id: string; title: string; items: ListItem[]; kind: 'project' | 'knowledge'; source: DataKind; locale: Locale }) {
  const t = messages[locale];
  const icon = kind === 'project' ? 'folder' : 'book';
  const label = kind === 'project' ? t.projectType : t.knowledgeType;
  const technical = kind === 'project' && source === 'UNAVAILABLE';
  return <article className={`dashboard-card list-card ${kind}-card`} id={id}>
    <ModuleTitle title={title} icon={icon} trailing={<span className="section-count">{source === 'REAL' ? items.length : t.unavailable} <small>{source === 'REAL' ? t.apiEntries : source}</small></span>} />
    {technical && <p className="semantic-note">{t.technicalItems}</p>}
    {items.length ? <div className="list-items">{items.slice(0, 4).map((item, index) => <div className="list-row" key={`${item.title}-${index}`}>
      <span className={`list-icon list-tone-${index % 4}`}><Icon name={icon} size={14} /></span>
      <span className="list-item-copy"><strong title={item.title}>{item.title}</strong><small>{label}</small></span>
      <span className={`list-item-status ${item.status ? 'is-real' : 'is-unavailable'}`} title={item.status || t.statusUnavailable}>{!item.status && <i className="unavailable-status-dot" aria-hidden="true" />}{item.status || t.statusUnavailable}</span>
      <span className="list-arrow"><Icon name="chevron" size={14} /></span>
    </div>)}</div> : source === 'UNAVAILABLE' ? <EmptyInline text={t.unavailable} /> : <EmptyInline text={t.empty} />}
  </article>;
}

function AgentCard({ status, locale }: { status: string | null; locale: Locale }) {
  const t = messages[locale];
  return <article className="dashboard-card agent-card">
    <ModuleTitle title={t.agent} icon="brain" trailing={<span className={`agent-pill ${status ? 'is-online' : ''}`}><i />{status ? t.online : t.unavailable}</span>} />
    <div className="agent-visual"><div className="agent-copy"><strong>{t.agentSupport}</strong><small>{status ? `${localizeStatus(status, locale)} · REAL` : t.unavailable}</small></div><img className="agent-crystal" src={aiCubeUrl} alt="" aria-hidden="true" /></div>
    <div className="agent-visual-caption"><span className="source-badge demo">DEMO</span><span>{locale === 'en' ? 'Visual identity' : '视觉主图'}</span></div>
    <div className="agent-footer"><span><i className={status ? 'online' : ''} />{locale === 'en' ? 'Runtime status' : '运行状态'}</span><strong>{status ? localizeStatus(status, locale) : '—'}</strong></div>
  </article>;
}

function ConnectedPlaceholder({ id, title, description, locale, icon }: { id: string; title: string; description: string; locale: Locale; icon: string }) {
  const t = messages[locale];
  return <article className="dashboard-card connected-card" id={id}>
    <ModuleTitle title={title} icon={icon} trailing={<span className="coming-pill">{t.soon}</span>} />
    <div className="connected-content"><div className="connected-graphic"><Icon name={icon} size={30} /><span /><span /></div><div><strong>{t.notConnectedTitle}</strong><p>{description}</p></div></div>
  </article>;
}

function EmptyInline({ text }: { text: string }) { return <div className="empty-inline"><span>○</span>{text}</div>; }

function ActionCard({ icon, tone, title, description, soon, onClick }: { icon: string; tone: string; title: string; description: string; soon?: string; onClick?: () => void }) {
  return <button type="button" className={`action-card ${tone} ${soon ? 'is-disabled' : 'is-interactive'}`} disabled={!!soon} onClick={onClick}>
    <span className="action-icon"><Icon name={icon} size={19} /></span><span className="action-copy"><strong>{title}</strong><small>{soon || description}</small></span>{soon ? <span className="soon-dot" /> : <Icon name="chevron" size={16} />}
  </button>;
}
