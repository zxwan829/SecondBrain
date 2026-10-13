import React, { useEffect, useMemo, useState } from 'react';
import { fetchHome, type Home } from './api/home';
import { adaptHome, type DataKind, type ListItem } from './api/home-adapter';
import { useImmersiveTrace } from './host-integration/immersive';
import { DEMO_KPI_DELTAS, DEMO_SOURCE_SPLIT, DEMO_WEATHER } from './demo-data';
import aiCubeUrl from './assets/ai-cube-user.png';
import hermesOrbUrl from './assets/hermes-planet-user.png';
import todayLandscapeUrl from './assets/today-lake-background.png';

type Locale = 'zh-CN' | 'en';
type Page = 'home' | 'review';
type Copy = typeof messages['zh-CN'];

const CORE_REVIEW_API = (import.meta.env.VITE_CORE_REVIEW_API ?? '').replace(/\/+$/, '');
const DASHBOARD_ORIGIN = import.meta.env.VITE_DASHBOARD_ORIGIN ?? '';

type ReviewItem = {
  review_path: string;
  review_sha256: string;
  target_filename: string;
  title: string;
  status: string;
};
type ReviewDetail = ReviewItem & { content: string };

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
    coreUnlock: '解锁 Core', coreLock: '锁定 Core', corePassphrase: 'Core 专属解锁口令',
    coreLocked: 'Review 受 Core 会话保护。输入解锁口令后读取真实列表。',
    coreLoading: '正在读取 Core Review…', coreConnected: '已连接 Core · {count} 条真实 Review · Promote 关闭',
    coreNoItems: '暂无待审核条目', coreSelectItem: '选择条目查看内容', coreStatus: '状态',
    coreNeedHttps: '请通过已配置的 Dashboard HTTPS 地址使用 Review。',
    coreNotConfigured: '尚未配置 Core Review API。请在本地构建环境中设置 VITE_CORE_REVIEW_API 和 VITE_DASHBOARD_ORIGIN。',
    coreSessionExpired: 'Core 会话已失效，请重新解锁。', coreConnectionFailed: 'Core 连接失败',
    coreUnlockFailed: '解锁失败，请检查口令后重试。', coreLockFailed: '锁定失败', backHome: '返回首页',
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
    coreUnlock: 'Unlock Core', coreLock: 'Lock Core', corePassphrase: 'Core-only passphrase',
    coreLocked: 'Review is protected by a Core session. Unlock to load the real list.',
    coreLoading: 'Loading Core Review…', coreConnected: 'Connected to Core · {count} real Review items · Promote disabled',
    coreNoItems: 'No pending Review items', coreSelectItem: 'Select an item to view its content', coreStatus: 'Status',
    coreNeedHttps: 'Open Review through the configured Dashboard HTTPS address.',
    coreNotConfigured: 'Core Review API is not configured. Set VITE_CORE_REVIEW_API and VITE_DASHBOARD_ORIGIN in the local build environment.',
    coreSessionExpired: 'Core session expired. Unlock again.', coreConnectionFailed: 'Core connection failed',
    coreUnlockFailed: 'Unlock failed. Check the passphrase and try again.', coreLockFailed: 'Could not lock Core', backHome: 'Back to Home',
  },
} as const;

const navItems = [
  { id: 'home', key: 'home', icon: 'home', section: 'top' },
  { id: 'chat', key: 'chat', icon: 'message', section: 'top' },
  { id: 'today', key: 'today', icon: 'calendar', section: 'work' },
  { id: 'inbox', key: 'inbox', icon: 'inbox', section: 'work' },
  { id: 'review', key: 'review', icon: 'check', section: 'work' },
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
  const trace = useImmersiveTrace();
  const [locale, setLocale] = useState<Locale>(() => localStorage.getItem('secondbrain.locale') === 'en' ? 'en' : 'zh-CN');
  const [home, setHome] = useState<Home | null>(null);
  const [error, setError] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [copyState, setCopyState] = useState('');
  const [page, setPage] = useState<Page>('home');
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

  const view = useMemo(() => adaptHome(home), [home]);
  const changeLocale = () => setLocale((current) => current === 'zh-CN' ? 'en' : 'zh-CN');
  const navigate = (item: string) => {
    if (item === 'chat') { window.location.href = '/chat'; return; }
    if (item === 'review') { setPage('review'); setMenuOpen(false); return; }
    if (page === 'review') setPage('home');
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

      <section className="dashboard">
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
            <button type="button" className="settings-button" disabled title={t.settingsSoon} aria-label={t.settingsSoon}><Icon name="settings" size={17} /></button>
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
            <ActionCard icon="message" tone="action-blue" title={t.chat} description={t.chatDescription} onClick={() => { window.location.href = '/chat'; }} />
            <ActionCard icon="check" tone="action-violet" title={t.review} description={t.reviewDescription} onClick={() => navigate('review')} />
            <ActionCard icon="capture" tone="action-teal" title={t.capture} description={t.captureDescription} soon={t.soon} />
            <ActionCard icon="journal" tone="action-slate" title={t.newJournal} description={t.journalDescription} soon={t.soon} />
          </div>
        </section>

        {trace.debug && <TracePanel trace={trace} locale={locale} copied={copyState} setCopied={setCopyState} />}
        </> : <ReviewPage locale={locale} onBack={() => setPage('home')} />}
      </section>
    </main>
  );
}

function ReviewPage({ locale, onBack }: { locale: Locale; onBack: () => void }) {
  const t = messages[locale];
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [passphrase, setPassphrase] = useState('');
  const [locked, setLocked] = useState(true);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string>(t.coreLocked);

  const request = async <T,>(path: string, init: RequestInit = {}): Promise<T> => {
    if (!CORE_REVIEW_API || !DASHBOARD_ORIGIN) {
      throw new Error(t.coreNotConfigured);
    }
    if (window.location.origin !== DASHBOARD_ORIGIN || window.location.protocol !== 'https:') {
      throw new Error(t.coreNeedHttps);
    }
    const response = await fetch(`${CORE_REVIEW_API}${path}`, {
      ...init,
      mode: 'cors',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
    });
    let payload: Record<string, unknown> = {};
    try { payload = await response.json() as Record<string, unknown>; } catch { /* retain status fallback */ }
    if (!response.ok) {
      const error = new Error(typeof payload.detail === 'string' ? payload.detail : `${t.coreConnectionFailed} (HTTP ${response.status})`);
      Object.assign(error, { status: response.status });
      throw error;
    }
    return payload as T;
  };

  const loadList = async () => {
    setBusy(true);
    setStatus(t.coreLoading);
    try {
      const result = await request<{ items?: ReviewItem[] }>('/review/items');
      const nextItems = Array.isArray(result.items) ? result.items : [];
      setItems(nextItems);
      setLocked(false);
      setStatus(t.coreConnected.replace('{count}', String(nextItems.length)));
      if (nextItems.length) await loadDetail(nextItems[0]);
      else setDetail(null);
    } catch (error) {
      setItems([]);
      setDetail(null);
      setLocked(true);
      const statusCode = (error as Error & { status?: number }).status;
      setStatus(statusCode === 401 ? t.coreLocked : error instanceof Error ? error.message : t.coreConnectionFailed);
    } finally {
      setBusy(false);
    }
  };

  const loadDetail = async (item: ReviewItem) => {
    setBusy(true);
    try {
      const safePath = item.review_path.split('/').map(encodeURIComponent).join('/');
      const result = await request<ReviewDetail>(`/review/items/${safePath}`);
      setDetail(result);
    } catch (error) {
      const statusCode = (error as Error & { status?: number }).status;
      setStatus(statusCode === 401 ? t.coreSessionExpired : error instanceof Error ? error.message : t.coreConnectionFailed);
      if (statusCode === 401) { setLocked(true); setItems([]); setDetail(null); }
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void loadList();
    // Initial status check only; subsequent reads are user initiated.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const unlock = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setStatus(t.coreLoading);
    try {
      await request('/auth/unlock', { method: 'POST', body: JSON.stringify({ passphrase }) });
      setPassphrase('');
      await loadList();
    } catch (error) {
      setPassphrase('');
      setStatus(error instanceof Error ? error.message : t.coreUnlockFailed);
      setBusy(false);
    }
  };

  const lock = async () => {
    setBusy(true);
    try {
      await request('/auth/lock', { method: 'POST', body: '{}' });
      setLocked(true); setItems([]); setDetail(null); setStatus(t.coreLocked);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : t.coreLockFailed);
    } finally { setBusy(false); }
  };

  return <section className="review-page" aria-labelledby="review-page-title">
    <header className="review-page-header">
      <div><p className="eyebrow">SECONDBRAIN <span>/</span> {t.review.toUpperCase()}</p><h1 id="review-page-title">{t.reviewPageTitle}</h1><p className="workspace-subtitle">{t.reviewPageDescription}</p></div>
      <button type="button" className="review-back-button" onClick={onBack}>{t.backHome}</button>
    </header>
    <p className={`review-connection-status ${locked ? 'is-locked' : 'is-connected'}`} role="status" aria-live="polite">{status}</p>
    {locked ? <form className="review-unlock-form" onSubmit={unlock}>
      <p>{t.coreLocked}</p><label><span>{t.corePassphrase}</span><input type="password" autoComplete="current-password" value={passphrase} onChange={(event) => setPassphrase(event.target.value)} required /></label>
      <button type="submit" disabled={busy || !passphrase}>{busy ? t.coreLoading : t.coreUnlock}</button>
    </form> : <>
      <div className="review-page-toolbar"><span>{status}</span><button type="button" onClick={lock} disabled={busy}>{t.coreLock}</button></div>
      <div className="review-page-grid">
        <div className="review-page-list" aria-label={t.reviewPageTitle}>
          {items.length ? items.map((item) => <button key={item.review_path} type="button" className={`review-page-item ${detail?.review_path === item.review_path ? 'is-selected' : ''}`} onClick={() => void loadDetail(item)}>
            <strong>{item.title || item.target_filename}</strong><small>{item.target_filename}</small><span>{t.coreStatus}: {item.status || 'unknown'}</span>
          </button>) : <p className="review-page-empty">{t.coreNoItems}</p>}
        </div>
        <article className="review-page-detail">
          {detail ? <><h2>{detail.title || detail.target_filename}</h2><p>{detail.target_filename} · {t.coreStatus}: {detail.status || 'unknown'}</p><pre>{detail.content}</pre></> : <p>{t.coreSelectItem}</p>}
        </article>
      </div>
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

function TracePanel({ trace, locale, copied, setCopied }: { trace: ReturnType<typeof useImmersiveTrace>; locale: Locale; copied: string; setCopied: (value: string) => void }) {
  const t = messages[locale];
  const text = trace.copyText || JSON.stringify(trace, null, 2);
  const copy = async () => {
    try {
      if (!navigator.clipboard?.writeText) throw new Error('clipboard unavailable');
      await navigator.clipboard.writeText(text);
      setCopied(t.copied);
    } catch {
      setCopied(t.copyManual);
      const textarea = document.querySelector<HTMLTextAreaElement>('.diagnostics textarea');
      textarea?.focus();
      textarea?.select();
    }
  };
  return <section className="diagnostics" aria-label="Immersive diagnostics">
    <div className="diagnostics-heading"><div><span>CLIENT-SIDE ONLY</span><h2>IMMERSIVE LIFECYCLE TRACE</h2></div><button type="button" onClick={copy}>{copied || t.copyTrace}</button></div>
    <div className="diagnostic-summary"><Diagnostic label="Route" value={trace.activeRoute}/><Diagnostic label="Immersive" value={String(trace.immersiveActive)}/><Diagnostic label="Header" value={trace.headerStyle}/><Diagnostic label="Spacer" value={trace.spacerStyle}/><Diagnostic label="SecondBrain top" value={trace.secondBrainHeaderTop === null ? '—' : `${trace.secondBrainHeaderTop.toFixed(1)}px`}/></div>
    <textarea readOnly value={text} aria-label="diagnostic results" />
  </section>;
}

function Diagnostic({ label, value }: { label: string; value: string }) { return <div><small>{label}</small><strong>{value}</strong></div>; }
