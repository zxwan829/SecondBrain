import React, { useEffect, useMemo, useRef, useState } from 'react';
import { fetchHome, type Home } from './api/home';
import { adaptHome, type DataKind, type ListItem } from './api/home-adapter';
import { DEMO_KPI_DELTAS, DEMO_SOURCE_SPLIT, DEMO_WEATHER } from './demo-data';
import { parseReviewDocument, ReviewMarkdown } from './ReviewMarkdown';
import aiCubeUrl from './assets/ai-cube-user.png';
import hermesOrbUrl from './assets/hermes-planet-user.png';
import todayLandscapeUrl from './assets/today-lake-background.png';
import { UnifiedCaptureComposer } from './UnifiedCaptureComposer';
import { apiFailureLabel, captureFailureLabel, captureStatusLabel, chatFailureLabel, chatStatusLabel, chatToolStageLabel, isImageOcrDescriptionUnavailable, reviewStatusLabel } from './user-messages';

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

function pageFromPath(path: string): Page {
  const route = navItems.find((item) => 'route' in item && item.route !== '/' &&
    (path === item.route || path.startsWith(`${item.route}/`)));
  if (route) return route.id;
  return 'home';
}

const messages = {
  'zh-CN': {
    brand: 'SecondBrain', workspace: '你的工作台', subtitle: '一眼掌握当前状态，专注今日最重要的事情',
    home: '首页', chat: '对话', today: '今日', inbox: '收件箱', review: '待审核', projects: '项目',
    knowledge: '知识库', brief: '简报', activity: '动态', journal: '日志', settings: '设置',
    projectOverview: '项目概览', knowledgeOverview: '知识总览', agent: '智能助手', online: '在线',
    todayDescription: '专注当下，记录并推进你的重要事项',
    returnedItems: 'API 返回条目', agentSupport: 'SecondBrain V1', source: '数据来源',
    emptyTitle: '暂无今日记录', emptyDescription: '你可以记录日程，想法或待办事项', create: '新建记录',
    empty: '暂无内容', notConnected: '功能即将上线', notConnectedTitle: '功能即将上线',
    notConnectedDescription: '接入后将为你提供每日重点和重要更新', waiting: '待我处理',
    recentKnowledge: '最近知识', quick: '快捷操作', quickDescription: '常用能力，一键直达',
    capture: '快速收录', newJournal: '新建日记', soon: '即将开放',
    localeLabel: '中文', menu: '打开导航菜单', closeMenu: '关闭导航菜单', demo: 'DEMO', real: 'REAL',
    demoTrend: '趋势示意', demoSources: '来源占比示意', pending: '待审核', apiEntries: 'API 返回条目',
    unavailable: '尚未统计', noTodayData: '今日数据结构暂不可识别', technicalItems: 'Home API 当前返回的是项目目录文件，尚非业务项目列表。',
    viewAll: '查看全部', reviewStatus: '待审核', projectType: '项目条目', knowledgeType: '知识条目',
    statusUnavailable: '状态未提供', demoDelta: '趋势示意',
    briefDescription: '每日为你生成关键信息摘要', activityDescription: '聚合与你协作的动态',
    chatDescription: '与 SecondBrain 对话', reviewDescription: '查看待处理内容',
    captureDescription: '快速保存想法与资料', journalDescription: '记录今日思考',
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
    home: 'Home', chat: 'Chat', today: 'Today', inbox: 'Inbox', review: 'Review', projects: 'Projects',
    knowledge: 'Knowledge', brief: 'Brief', activity: 'Activity', journal: 'Journal', settings: 'Settings',
    projectOverview: 'Project overview', knowledgeOverview: 'Knowledge overview', agent: 'AI assistant', online: 'Online',
    todayDescription: 'Stay present, capture ideas, and move important things forward.',
    returnedItems: 'API entries', agentSupport: 'SecondBrain V1', source: 'Data source',
    emptyTitle: 'Nothing planned today', emptyDescription: 'Capture a schedule, idea, or task when you are ready', create: 'New entry',
    empty: 'Nothing here yet', notConnected: 'Coming soon', notConnectedTitle: 'Coming soon',
    notConnectedDescription: 'Daily highlights and important updates will appear here once connected', waiting: 'Waiting for me',
    recentKnowledge: 'Recent knowledge', quick: 'Quick actions', quickDescription: 'Your most-used destinations',
    capture: 'Quick capture', newJournal: 'New journal', soon: 'Coming soon',
    localeLabel: 'EN', menu: 'Open navigation', closeMenu: 'Close navigation', demo: 'DEMO', real: 'REAL',
    demoTrend: 'illustrative trend', demoSources: 'illustrative source mix', pending: 'Pending',
    apiEntries: 'API returned entries', unavailable: 'Not available', noTodayData: 'Today data shape is not recognized',
    technicalItems: 'The Home API currently returns project-directory files, not business project records.',
    viewAll: 'View all', reviewStatus: 'Pending review', projectType: 'Project entry', knowledgeType: 'Knowledge entry',
    statusUnavailable: 'Status unavailable', demoDelta: 'illustrative change',
    briefDescription: 'A daily summary of the information that matters', activityDescription: 'A view of the work happening around you',
    chatDescription: 'Talk with SecondBrain', reviewDescription: 'Review items waiting for you',
    captureDescription: 'Save an idea or a useful reference', journalDescription: 'Record a thought from today',
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
  { id: 'today', key: 'today', icon: 'calendar', section: 'work' },
  { id: 'inbox', key: 'inbox', icon: 'inbox', section: 'work', route: '/inbox' },
  { id: 'review', key: 'review', icon: 'check', section: 'work', route: '/review' },
  { id: 'projects', key: 'projects', icon: 'folder', section: 'library' },
  { id: 'knowledge', key: 'knowledge', icon: 'book', section: 'library' },
  { id: 'brief', key: 'brief', icon: 'file', section: 'library' },
  { id: 'activity', key: 'activity', icon: 'activity', section: 'library' },
  { id: 'journal', key: 'journal', icon: 'journal', section: 'library', soon: true },
  { id: 'settings', key: 'settings', icon: 'settings', section: 'bottom', soon: true },
] as const;

const anchorByNav: Record<string, string> = {
  home: 'top', today: 'today', inbox: 'waiting', review: 'waiting',
  projects: 'projects', knowledge: 'knowledge', brief: 'brief', activity: 'activity',
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

function loginFailureMessage(status: number): string {
  if (status === 401) return '登录未通过 App 凭据校验（HTTP 401）。';
  if (status === 403) return '请求来源校验失败（HTTP 403）。请使用配置的 SecondBrain HTTPS 地址。';
  if (status === 429) return '登录尝试过多（HTTP 429），请稍后再试。';
  if (status >= 500) return `SecondBrain App 服务异常（HTTP ${status}），请稍后重试。`;
  return `登录请求被拒绝（HTTP ${status}）。`;
}

function WorkspaceApp({ onLogout }: { onLogout: () => void }) {
  const [locale, setLocale] = useState<Locale>(() => localStorage.getItem('secondbrain.locale') === 'en' ? 'en' : 'zh-CN');
  const [home, setHome] = useState<Home | null>(null);
  const [error, setError] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [page, setPage] = useState<Page>(() => pageFromPath(location.pathname));
  const [routeRevision, setRouteRevision] = useState(0);
  const [captureOpen, setCaptureOpen] = useState(false);
  const t = messages[locale];

  useEffect(() => {
    localStorage.setItem('secondbrain.locale', locale);
    document.documentElement.lang = locale;
  }, [locale]);
  useEffect(() => {
    let mounted = true;
    fetchHome().then((data) => { if (mounted) setHome(data); }).catch(() => { if (mounted) setError(true); });
    return () => { mounted = false; };
  }, []);
  useEffect(() => {
    const onPop = () => { setPage(pageFromPath(location.pathname)); setRouteRevision((value) => value + 1); };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  const view = useMemo(() => adaptHome(home), [home]);
  const changeLocale = () => setLocale((current) => current === 'zh-CN' ? 'en' : 'zh-CN');
  const navigate = (item: string) => {
    const destination = navItems.find((entry) => entry.id === item);
    if (destination && 'route' in destination && destination.route) {
      if (location.pathname !== destination.route || location.search) history.pushState({}, '', destination.route);
      setPage(destination.id); setRouteRevision((value) => value + 1); setMenuOpen(false); return;
    }
    if (page !== 'home') {
        history.pushState({}, '', '/'); setPage('home');
    }
    const target = document.getElementById(anchorByNav[item] ?? 'top');
    window.requestAnimationFrame(() => target?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
    setMenuOpen(false);
  };

  const nav = (mobile = false) => (
    <nav className={mobile ? 'nav-list mobile-nav-list' : 'nav-list'} aria-label={t.brand}>
      {(['top', 'work', 'library', 'bottom'] as const).map((section) => (
        <div className={`nav-section nav-section-${section}`} key={section}>
          {navItems.filter((item) => item.section === section).map((item) => (
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
              {'soon' in item && item.soon && <span className="nav-soon">{t.soon}</span>}
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

        {page === 'home' ? <>
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
          <TodayCard state={view.today} locale={locale} />
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
            <ActionCard icon="capture" tone="action-teal" title={t.capture} description={t.captureDescription} onClick={() => setCaptureOpen(true)} />
            <ActionCard icon="journal" tone="action-slate" title={t.newJournal} description={t.journalDescription} soon={t.soon} />
          </div>
        </section>

        </> : page === 'review' ? <ReviewPage key={routeRevision} locale={locale} initialReviewPath={new URLSearchParams(location.search).get('review_path')} onBack={() => navigate('home')} />
          : page === 'inbox' ? <InboxPage locale={locale} onComplete={() => window.dispatchEvent(new Event('sb-inbox-refresh'))} onGoInbox={() => navigate('inbox')} onReview={(path) => { const query = new URLSearchParams({ review_path: path }); history.pushState({}, '', `/review?${query}`); setPage('review'); setRouteRevision((value) => value + 1); }} />
          : page === 'chat' ? <ChatPage locale={locale} />
            : <div className="chat-empty" role="status">{locale === 'en' ? 'This Personal OS module is not connected yet.' : '此 Personal OS 模块尚未接入。'}</div>}
      </section>
      {captureOpen && <QuickCapture locale={locale} onClose={() => setCaptureOpen(false)} onGoInbox={() => { setCaptureOpen(false); navigate('inbox'); }} onComplete={() => { if (page === 'inbox') window.dispatchEvent(new Event('sb-inbox-refresh')); }} />}
    </main>
  );
}

export function InboxPage({ locale, onComplete = () => undefined, onGoInbox = () => undefined, onReview }: { locale: Locale; onComplete?: () => void; onGoInbox?: () => void; onReview: (reviewPath: string) => void }) {
  const [items, setItems] = useState<CaptureItem[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState<CaptureItem | null>(null);
  const [previewText, setPreviewText] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState('');
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
    const refresh = () => void load();
    window.addEventListener('sb-inbox-refresh', refresh);
    const timer = window.setInterval(refresh, 5000);
    return () => { window.removeEventListener('sb-inbox-refresh', refresh); window.clearInterval(timer); };
  }, []);
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
  return <section className="capture-page" aria-labelledby="inbox-title">
    <header className="capture-page-header"><div><p className="eyebrow">SECONDBRAIN <span>/</span> INBOX</p><h1 id="inbox-title">{text ? 'Inbox' : '收件箱'}</h1><p className="workspace-subtitle">{text ? 'Captured source material and processing status.' : '查看采集来源、原始素材和处理状态。'}</p></div></header>
    <UnifiedCaptureComposer locale={locale} onComplete={onComplete} onGoInbox={onGoInbox} />
    {error && <p role="alert" className="capture-alert">{error}</p>}
    <div className="inbox-list" aria-live="polite">{loading ? <p>{text ? 'Loading…' : '加载中…'}</p> : items.length ? items.map((item) => <article className="inbox-item" key={item.capture_id}>
      <div className="inbox-item-main"><span className="inbox-type">{item.input_type.toUpperCase()}</span><div><h2>{captureDisplayFilename(item, locale)}</h2><p>{item.source_type} · {capturedAtLabel(item.captured_at, locale)}</p></div><span className={`capture-status status-${item.status}`}>{captureStatus(item.status, text)}</span></div>
      {item.content_preview && <pre className="inbox-preview">{item.content_preview.slice(0, 500)}</pre>}
      {isVisionDescriptionOnly(item)
        ? <p className="capture-processing-note" role="status">{text ? 'Text recognition completed; image understanding is not connected yet.' : '文字识别完成，画面理解暂未接入。'}</p>
        : item.error && <p className="capture-alert">{captureFailureLabel(item.error, locale)}</p>}
      <div className="inbox-links"><button type="button" onClick={() => void openPreview(item)}>{text ? 'Preview details' : '预览与详情'}</button><a href={`/api/inbox/${encodeURIComponent(item.capture_id)}/raw`} download>{text ? 'Download Raw' : '下载原件'}</a>{item.review_path && <button type="button" onClick={() => onReview(item.review_path!)}>{text ? 'View Review' : '查看 Review'}</button>}{item.status === 'partial_success' && !isVisionDescriptionOnly(item) && <button type="button" onClick={() => void retryCapture(item)}>{text ? 'Retry' : '重试处理'}</button>}</div>
    </article>) : <p className="capture-empty">{text ? 'No captures yet.' : '还没有采集内容。'}</p>}</div>
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

function CapturePreview({ item, locale, content, error, onClose, onReview }: { item: CaptureItem; locale: Locale; content: string | null; error: string; onClose: () => void; onReview: (path: string) => void }) {
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
      <footer><a className="capture-secondary" href={`/api/inbox/${encodeURIComponent(item.capture_id)}/raw`} download>{en ? 'Download original' : '下载原件'}</a>{item.review_path && <button type="button" className="capture-primary" onClick={() => onReview(item.review_path!)}>{en ? 'View related Review' : '查看对应 Review'}</button>}<button type="button" className="capture-secondary" onClick={onClose}>{en ? 'Close' : '关闭'}</button></footer>
    </section>
  </div>;
}

export function QuickCapture({ locale, onClose, onComplete, onGoInbox }: { locale: Locale; onClose: () => void; onComplete: () => void; onGoInbox: () => void }) {
  const text = locale === 'en';
  return <div className="capture-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="capture-modal unified-capture-modal" role="dialog" aria-modal="true" aria-labelledby="capture-dialog-title">
      <header><div><p className="eyebrow">SECONDBRAIN / CAPTURE</p><h2 id="capture-dialog-title">{text ? 'Quick capture' : '快速收录'}</h2></div><button className="capture-close" type="button" onClick={onClose} aria-label={text ? 'Close' : '关闭'}>×</button></header>
      <UnifiedCaptureComposer locale={locale} onComplete={onComplete} onGoInbox={onGoInbox} />
    </section>
  </div>;
}

function captureStatus(status: string, en: boolean) {
  return captureStatusLabel(status, en ? 'en' : 'zh-CN');
}

export function ReviewPage({ locale, onBack, initialReviewPath = null }: { locale: Locale; onBack: () => void; initialReviewPath?: string | null }) {
  const t = messages[locale];
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string>(t.coreLoading);
  const [promoteEnabled, setPromoteEnabled] = useState(false);
  const [mobileListOpen, setMobileListOpen] = useState(false);
  const reviewListRef = useRef<HTMLDivElement | null>(null);
  const reviewDetailRef = useRef<HTMLElement | null>(null);
  const selectedReviewRef = useRef<HTMLButtonElement | null>(null);

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
    setBusy(true);
    setStatus(t.coreLoading);
    const requestedReviewPath = location.pathname === '/review'
      ? new URLSearchParams(location.search).get('review_path')
      : initialReviewPath;
    try {
      const result = await request<{ items?: ReviewItem[] }>('/review/items');
      let captureDates = new Map<string, Set<string>>();
      try {
        const response = await fetch('/api/inbox?limit=200', { credentials: 'same-origin' });
        if (response.ok) {
          const inbox = await response.json() as { items?: CaptureItem[] };
          for (const capture of Array.isArray(inbox.items) ? inbox.items : []) {
            if (!capture.review_path || capturedAtMillis(capture.captured_at) === null) continue;
            const dates = captureDates.get(capture.review_path) ?? new Set<string>();
            dates.add(capture.captured_at);
            captureDates.set(capture.review_path, dates);
          }
        }
      } catch { /* Review frontmatter remains the primary timestamp source. */ }
      const nextItems = sortByCapturedAt((Array.isArray(result.items) ? result.items : []).map((item) => {
        if (capturedAtMillis(item.captured_at) !== null) return item;
        const matches = captureDates.get(item.review_path);
        return { ...item, captured_at: matches?.size === 1 ? [...matches][0] : null };
      }), (item) => item.review_path);
      setItems(nextItems);
      setStatus(t.coreConnected.replace('{count}', String(nextItems.length)));
      if (requestedReviewPath) {
        const selected = nextItems.find((item) => item.review_path === requestedReviewPath);
        if (selected) await loadDetail(selected);
        else { setDetail(null); setStatus(locale === 'en' ? 'The requested Review item could not be found.' : '找不到指定的 Review 条目。'); }
      } else if (nextItems.length) await loadDetail(nextItems[0]);
      else setDetail(null);
      const promote = await request<{ promote_enabled?: boolean }>('/status');
      setPromoteEnabled(promote.promote_enabled === true);
    } catch (error) {
      setItems([]);
      setDetail(null);
      const statusCode = (error as Error & { status?: number }).status;
      if (statusCode === 401) window.location.reload();
      setStatus(error instanceof Error ? apiFailureLabel(error.message, statusCode ?? 0, locale, 'review') : t.coreConnectionFailed);
    } finally {
      setBusy(false);
    }
  };

  const loadDetail = async (item: ReviewItem) => {
    setBusy(true);
    try {
      const safePath = item.review_path.split('/').map(encodeURIComponent).join('/');
      const result = await request<ReviewDetail>(`/review/items/${safePath}`);
      setDetail({ ...result, captured_at: result.captured_at ?? item.captured_at ?? null });
    } catch (error) {
      const statusCode = (error as Error & { status?: number }).status;
      setStatus(statusCode === 401 ? t.coreSessionExpired : error instanceof Error ? apiFailureLabel(error.message, statusCode ?? 0, locale, 'review') : t.coreConnectionFailed);
      if (statusCode === 401) window.location.reload();
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void loadList();
    // Initial status check only; subsequent reads are user initiated.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialReviewPath]);

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
    const query = new URLSearchParams({ review_path: item.review_path });
    history.pushState({}, '', `/review?${query}`);
    setMobileListOpen(false);
    void loadDetail(item);
  };

  const decide = async (decision: 'approve' | 'defer') => {
    if (!detail) return;
    if (decision === 'approve' && !window.confirm(locale === 'en' ? `Approve and promote “${detail.title}” to Knowledge?` : `确认将「${detail.title}」批准并正式写入 Knowledge？`)) return;
    setBusy(true);
    try {
      const path = decision === 'approve' ? '/review/approve' : '/review/defer';
      const retryable = ['approved', 'promoting', 'failed'].includes(detail.decision?.status || '');
      const requestId = decision === 'approve' && retryable && detail.decision?.request_id
        ? detail.decision.request_id : crypto.randomUUID();
      const result = await request<{ status?: string }>(path, { method: 'POST', body: JSON.stringify({
        review_path: detail.review_path, review_sha256: detail.review_sha256,
        request_id: requestId, target_filename: detail.target_filename,
      }) });
      setStatus(reviewStatusLabel(result.status || (decision === 'approve' ? 'approved' : 'deferred'), locale));
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
            <div className="review-decisions"><button type="button" onClick={() => void decide('defer')} disabled={busy || ['approved', 'promoting', 'promoted', 'failed'].includes(detail.decision?.status || '')}>{locale === 'en' ? 'Defer' : '暂缓'}</button><button type="button" onClick={() => void decide('approve')} disabled={busy || !promoteEnabled || detail.decision?.status === 'promoted'} title={!promoteEnabled ? (locale === 'en' ? 'Promote disabled on this App build' : '当前版本已关闭正式入库') : undefined}>{['approved', 'promoting', 'failed'].includes(detail.decision?.status || '') ? (locale === 'en' ? 'Retry approved write' : '重试正式入库') : (locale === 'en' ? 'Approve to Knowledge' : '批准入库')}</button>{!promoteEnabled && <small>{locale === 'en' ? 'Knowledge writes are disabled.' : '正式入库当前关闭。'}</small>}</div></> : <p>{t.coreSelectItem}</p>}
        </article>
      </div>
  </section>;
}

type ChatSession = { id: string; title: string; updated?: string | number };
type ChatMessage = { id: string; role: 'user' | 'assistant'; text: string };

function ChatPage({ locale }: { locale: Locale }) {
  const en = locale === 'en';
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [selected, setSelected] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [progress, setProgress] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [runId, setRunId] = useState('');
  const abortRef = React.useRef<AbortController | null>(null);

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

  const reloadSessions = async (preferred = selected) => {
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

  const loadMessages = async (sessionId: string) => {
    const payload = await api<Record<string, unknown>>(`/api/chat/sessions/${encodeURIComponent(sessionId)}/messages`);
    const raw = Array.isArray(payload.messages) ? payload.messages : Array.isArray(payload.items) ? payload.items : Array.isArray(payload) ? payload : [];
    setMessages(raw.flatMap((value, index) => {
      if (!value || typeof value !== 'object') return [];
      const row = value as Record<string, unknown>;
      const role = String(row.role ?? row.type ?? '');
      if (role !== 'user' && role !== 'assistant') return [];
      let text = row.text ?? row.content ?? row.message ?? '';
      if (Array.isArray(text)) text = text.flatMap((part) => part && typeof part === 'object' && typeof (part as Record<string, unknown>).text === 'string' ? [(part as Record<string, unknown>).text] : []).join('\n');
      if (typeof row.text === 'string') text = row.text;
      return typeof text === 'string' && text ? [{ id: String(row.id ?? index), role, text } as ChatMessage] : [];
    }));
  };

  const selectSession = async (sessionId: string) => {
    setSelected(sessionId); localStorage.setItem('secondbrain.chat.session', sessionId);
    setError(''); setMessages([]);
    try { await loadMessages(sessionId); } catch (cause) { setError(cause instanceof Error ? chatFailureLabel(cause.message, locale) : chatFailureLabel('Could not load session history', locale)); }
  };

  const pollRun = async (activeRun: string, sessionId: string) => {
    const terminal = new Set(['completed', 'failed', 'error', 'cancelled', 'canceled', 'interrupted', 'expired']);
    for (let attempt = 0; attempt < 60; attempt += 1) {
      const result = await api<Record<string, unknown>>(`/api/chat/runs/${encodeURIComponent(activeRun)}`);
      const status = String(result.status ?? 'unknown').toLowerCase();
      if (terminal.has(status)) {
        if (status === 'failed' || status === 'error' || status === 'interrupted') setError(chatFailureLabel(String(result.error ?? (status === 'interrupted' ? 'Hermes run was interrupted' : 'Hermes run failed')), locale));
        setProgress(chatStatusLabel(status, locale));
        await loadMessages(sessionId); await reloadSessions(sessionId);
        sessionStorage.removeItem('secondbrain.chat.activeRun');
        sessionStorage.removeItem('secondbrain.chat.activeSession');
        return true;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
    }
    setProgress(en ? 'Run is still active; reconnect to check its result.' : '任务仍在运行；重新进入 Chat 可继续核对结果。');
    return false;
  };

  useEffect(() => { void (async () => {
    try {
      const preferred = localStorage.getItem('secondbrain.chat.session') ?? '';
      const next = await reloadSessions(preferred);
      if (preferred && next.some((session) => session.id === preferred)) await selectSession(preferred);
      const activeRun = sessionStorage.getItem('secondbrain.chat.activeRun') ?? '';
      const activeSession = sessionStorage.getItem('secondbrain.chat.activeSession') ?? preferred;
      if (activeRun && activeSession) {
        setSelected(activeSession); setBusy(true); setRunId(activeRun);
        setProgress(en ? 'Checking the interrupted connection…' : '正在核对中断的连接…');
        try { await pollRun(activeRun, activeSession); }
        catch (cause) { setError(cause instanceof Error ? chatFailureLabel(cause.message, locale) : chatFailureLabel('Could not recover run status', locale)); }
        finally { setBusy(false); setRunId(''); }
      }
    } catch (cause) { setError(cause instanceof Error ? chatFailureLabel(cause.message, locale) : chatFailureLabel('Hermes API unavailable', locale)); }
  })(); }, []);

  const newSession = async () => {
    setError('');
    try {
      const payload = await api<Record<string, unknown>>('/api/chat/sessions', { method: 'POST', body: '{}' });
      const id = String(payload.session_id ?? '');
      if (!id) throw new Error('Hermes did not return a session identifier');
      await reloadSessions(id); setSelected(id); setMessages([]); localStorage.setItem('secondbrain.chat.session', id);
    } catch (cause) { setError(cause instanceof Error ? chatFailureLabel(cause.message, locale) : chatFailureLabel('Could not create session', locale)); }
  };

  const forkSession = async () => {
    if (!selected) return;
    try {
      const result = await api<Record<string, unknown>>(`/api/chat/sessions/${encodeURIComponent(selected)}/fork`, { method: 'POST', body: '{}' });
      const id = String(result.session_id ?? '');
      if (!id) throw new Error('Hermes did not return a forked session identifier');
      await reloadSessions(id); await selectSession(id);
    } catch (cause) { setError(cause instanceof Error ? chatFailureLabel(cause.message, locale) : chatFailureLabel('Could not fork session', locale)); }
  };

  const send = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const prompt = input.trim();
    if (!prompt || busy) return;
    setError(''); setInput(''); setBusy(true); setProgress(en ? 'Starting…' : '正在启动…');
    setMessages((current) => [...current, { id: `local-${Date.now()}`, role: 'user', text: prompt }, { id: `assistant-${Date.now()}`, role: 'assistant', text: '' }]);
    try {
      let sessionId = selected;
      if (!sessionId) {
        const created = await api<Record<string, unknown>>('/api/chat/sessions', { method: 'POST', body: '{}' });
        sessionId = String(created.session_id ?? '');
        if (!sessionId) throw new Error('Hermes did not return a session identifier');
        setSelected(sessionId); localStorage.setItem('secondbrain.chat.session', sessionId);
        await reloadSessions(sessionId);
      }
      const idempotencyKey = crypto.randomUUID();
      const started = await api<Record<string, unknown>>(`/api/chat/sessions/${encodeURIComponent(sessionId)}/runs`, {
        method: 'POST', headers: { 'Idempotency-Key': idempotencyKey }, body: JSON.stringify({ input: prompt }),
      });
      const activeRun = String(started.run_id ?? '');
      if (!activeRun) throw new Error('Hermes did not return a run identifier');
      setRunId(activeRun); setProgress(en ? 'Connected to Hermes' : '已连接 Hermes');
      sessionStorage.setItem('secondbrain.chat.activeRun', activeRun);
      sessionStorage.setItem('secondbrain.chat.activeSession', sessionId);
      const controller = new AbortController(); abortRef.current = controller;
      const response = await fetch(`/api/chat/runs/${encodeURIComponent(activeRun)}/events`, { credentials: 'same-origin', signal: controller.signal, headers: { Accept: 'text/event-stream' } });
      if (!response.ok || !response.body) throw new Error(`Hermes stream failed (HTTP ${response.status})`);
      const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = '';
      let sawTerminal = false;
      const consume = (frame: string) => {
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
        if (eventName === 'message.delta' || eventName === 'assistant.delta' || eventName === 'response.output_text.delta' || eventName === 'text.delta') {
          const delta = String(payload.delta ?? payload.text ?? payload.output_text ?? payload.content ?? '');
          if (delta) setMessages((current) => current.map((message, index) => index === current.length - 1 && message.role === 'assistant' ? { ...message, text: message.text + delta } : message));
        } else if (eventName.startsWith('tool.')) {
          const detail = typeof payload.preview === 'string' && payload.preview ? ` · ${payload.preview}` : '';
          const failed = payload.error === true;
          const failure = typeof payload.error === 'string' && payload.error ? ` · ${chatFailureLabel(payload.error, locale)}` : failed ? (en ? ' · tool reported an error' : ' · 工具报告错误') : '';
          setProgress(`${chatToolStageLabel(eventName.replace('tool.', ''), locale)}: ${name}${detail}${failure}`);
        } else if (eventName === 'run.completed' || eventName === 'assistant.completed') {
          sawTerminal = true;
          const output = typeof payload.output === 'string' ? payload.output : '';
          setMessages((current) => current.map((message, index) => index === current.length - 1 && message.role === 'assistant' && !message.text && output ? { ...message, text: output } : message));
          setProgress(en ? 'Completed' : '已完成');
        } else if (eventName === 'run.failed' || eventName === 'run.cancelled' || eventName === 'run.interrupted') {
          sawTerminal = true;
          const detail = String(payload.error ?? (eventName === 'run.cancelled' ? (en ? 'Stopped' : '已停止') : eventName));
          const statusLabel = chatStatusLabel(eventName.replace('run.', ''), locale);
          setProgress(eventName === 'run.cancelled' ? statusLabel : chatFailureLabel(detail, locale));
          if (eventName === 'run.failed' || eventName === 'run.interrupted') setError(chatFailureLabel(detail, locale));
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
        await loadMessages(sessionId); await reloadSessions(sessionId);
        sessionStorage.removeItem('secondbrain.chat.activeRun'); sessionStorage.removeItem('secondbrain.chat.activeSession');
      } else {
        setProgress(en ? 'Stream ended; checking run status…' : '连接结束，正在核对任务状态…');
        await pollRun(activeRun, sessionId);
      }
    } catch (cause) {
      if (!(cause instanceof DOMException && cause.name === 'AbortError')) {
        setProgress(en ? 'Connection interrupted; checking run status…' : '连接中断，正在核对任务状态…');
        try {
          const pendingRun = sessionStorage.getItem('secondbrain.chat.activeRun') ?? '';
          const pendingSession = sessionStorage.getItem('secondbrain.chat.activeSession') ?? selected;
          if (pendingRun && pendingSession) await pollRun(pendingRun, pendingSession);
          else setError(cause instanceof Error ? chatFailureLabel(cause.message, locale) : chatFailureLabel('Chat failed', locale));
        } catch (recoveryError) { setError(recoveryError instanceof Error ? chatFailureLabel(recoveryError.message, locale) : chatFailureLabel('Could not recover run status', locale)); }
      }
    } finally { abortRef.current = null; setRunId(''); setBusy(false); }
  };

  const stop = async () => {
    if (!runId) return;
    try { await api(`/api/chat/runs/${encodeURIComponent(runId)}/stop`, { method: 'POST', body: '{}' }); }
    catch (cause) { setError(cause instanceof Error ? chatFailureLabel(cause.message, locale) : chatFailureLabel('Could not stop run', locale)); }
    const activeSession = sessionStorage.getItem('secondbrain.chat.activeSession') ?? selected;
    setProgress(en ? 'Stopping…' : '正在停止…');
    try { await pollRun(runId, activeSession); }
    catch (cause) { setError(cause instanceof Error ? chatFailureLabel(cause.message, locale) : chatFailureLabel('Could not confirm stop status', locale)); }
    abortRef.current?.abort();
    setBusy(false); setRunId('');
  };

  return <section className="chat-page">
    <aside className="chat-sessions"><div className="chat-session-heading"><h1>{en ? 'Chat' : '对话'}</h1><button type="button" onClick={() => void newSession()}>{en ? 'New chat' : '新对话'}</button></div><div className="chat-session-list">{sessions.map((session) => <button type="button" key={session.id} className={session.id === selected ? 'is-selected' : ''} onClick={() => void selectSession(session.id)}><strong>{session.title}</strong><small>{session.updated ? formatDate(session.updated, locale) : session.id.slice(0, 16)}</small></button>)}</div></aside>
    <div className="chat-conversation"><header><div><p className="eyebrow">SECONDBRAIN <span>/</span> {en ? 'CHAT' : '对话'}</p><h2>{sessions.find((session) => session.id === selected)?.title ?? (en ? 'New conversation' : '新对话')}</h2></div><button type="button" onClick={() => void forkSession()} disabled={!selected || busy}>{en ? 'Fork' : '分支会话'}</button></header>
      <div className="chat-message-list">{messages.map((message) => <article key={message.id} className={`chat-message ${message.role}`}><span>{message.role === 'user' ? (en ? 'You' : '你') : 'Hermes'}</span><p>{message.text || (busy && message.role === 'assistant' ? progress : '')}</p></article>)}{!messages.length && <div className="chat-empty">{en ? 'Continue a Hermes session or start a new conversation.' : '继续 Hermes 会话，或开始新的对话。'}</div>}</div>
      {progress && <div className="chat-progress" role="status">{progress}</div>}{error && <p className="chat-error" role="alert">{error}</p>}
      <form className="chat-composer" onSubmit={send}><textarea value={input} onChange={(event) => setInput(event.target.value)} placeholder={en ? 'Message Hermes…' : '发送消息给 Hermes…'} rows={3} disabled={busy} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} /><div><small>{en ? 'Enter to send · Shift+Enter for a new line' : 'Enter 发送 · Shift+Enter 换行'}</small>{busy ? <button type="button" onClick={() => void stop()} disabled={!runId}>{en ? 'Stop' : '停止'}</button> : <button type="submit" disabled={!input.trim()}>{en ? 'Send' : '发送'}</button>}</div></form>
    </div>
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
    chevron: ['m7 10 5 5 5-5'], chevrons: ['m7 10 5-5 5 5', 'm7 14 5 5 5-5'], menu: ['M4 6h16M4 12h16M4 18h16'], close: ['m6 6 12 12M18 6 6 18'], bolt: ['m13 2-3 8h7l-6 12 2-9H6z'], capture: ['M12 20h9', 'M16.5 3.5a2.1 2.1 0 0 1 3 3L9 17l-4 1 1-4z'],
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

function TodayCard({ state, locale }: { state: ReturnType<typeof adaptHome>['today']; locale: Locale }) {
  const t = messages[locale];
  return <article className="dashboard-card today-card" id="today">
    <img className="today-background" src={todayLandscapeUrl} alt="" aria-hidden="true" />
    <ModuleTitle title={t.today} icon="calendar" trailing={<span className="card-link">{t.viewAll}<Icon name="chevron" size={14} /></span>} />
    <p className="today-description">{t.todayDescription}</p>
    {state.kind === 'content' ? <div className="today-items">{state.items.map((item, index) => <div className="today-item" key={`${item.title}-${index}`}><span className="timeline-dot"/><strong>{item.title}</strong></div>)}</div>
      : state.kind === 'empty' ? <IllustratedEmpty locale={locale} />
      : <div className="unknown-state"><span className="unknown-icon">?</span><strong>{t.noTodayData}</strong><small>UNAVAILABLE</small></div>}
  </article>;
}

function IllustratedEmpty({ locale }: { locale: Locale }) {
  const t = messages[locale];
  return <div className="illustrated-empty">
    <div className="empty-calendar"><Icon name="calendar" size={37} /></div>
    <strong>{t.emptyTitle}</strong><p>{t.emptyDescription}</p>
    <button type="button" className="coming-button" disabled><Icon name="capture" size={15} />{t.create}<small>{t.soon}</small></button>
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
