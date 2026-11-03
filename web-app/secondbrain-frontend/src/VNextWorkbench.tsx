import React, { useEffect, useMemo, useState } from 'react';
import './vnext-workbench.css';

export type WorkbenchTask = {
  id: string;
  title: string;
  planDate: string | null;
  dueDate: string | null;
  reminderAt: string | null;
  importance: 'normal' | 'important';
  completed: boolean;
};

export type TaskPresentation = 'loading' | 'unavailable' | 'empty' | 'ready';
export type WorkbenchCardId = 'tasks' | 'review' | 'projects' | 'knowledge';

type VNextWorkbenchProps = {
  now?: Date;
  initialTasks?: WorkbenchTask[];
  initialCardIds?: WorkbenchCardId[];
  taskPresentation?: TaskPresentation;
};

const cardLabels: Record<WorkbenchCardId, string> = {
  tasks: '今日待办', review: '待审核', projects: '项目进度', knowledge: '最近知识',
};

function dateKey(date: Date) {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(date);
  const part = (type: string) => parts.find((item) => item.type === type)?.value ?? '00';
  return `${part('year')}-${part('month')}-${part('day')}`;
}
function shiftDay(date: Date, delta: number) {
  const value = new Date(`${dateKey(date)}T12:00:00+08:00`);
  value.setDate(value.getDate() + delta);
  return dateKey(value);
}
function displayDate(value: string | null) {
  if (!value) return null;
  const date = new Date(`${value}T00:00:00+08:00`);
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: 'numeric', day: 'numeric' }).format(date);
}
function demoTasks(now: Date): WorkbenchTask[] {
  return [
    { id: 'task-overdue', title: '完成首页导航与待办信息层级梳理', planDate: dateKey(now), dueDate: shiftDay(now, -1), reminderAt: '18:00', importance: 'important', completed: false },
    { id: 'task-no-deadline', title: '整理明天会议材料', planDate: shiftDay(now, 1), dueDate: null, reminderAt: null, importance: 'normal', completed: false },
    { id: 'task-with-reminder', title: '回顾本周项目进展', planDate: null, dueDate: shiftDay(now, 3), reminderAt: '17:30', importance: 'normal', completed: false },
  ];
}

function SmallIcon({ name, size = 18 }: { name: 'brain' | 'home' | 'calendar' | 'inbox' | 'check' | 'folder' | 'book' | 'plus' | 'arrow' | 'cloud' | 'chat'; size?: number }) {
  const paths: Record<typeof name, React.ReactNode> = {
    brain: <><path d="M9 4.5A3 3 0 0 0 4.8 7.3 3 3 0 0 0 5.4 13 3 3 0 0 0 9 17.5M15 4.5a3 3 0 0 1 4.2 2.8 3 3 0 0 1-.6 5.7 3 3 0 0 1-3.6 4.5M9 4.5v13m6-13v13M9 9h3m-3 4h6" /></>,
    home: <><path d="m3 10 9-7 9 7" /><path d="M5 9v11h14V9M9 20v-6h6v6" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18" /></>,
    inbox: <><path d="M4 4h16l2 11h-6l-2 3h-4l-2-3H2L4 4Z" /><path d="M3 15h5l2 3h4l2-3h5" /></>,
    check: <><path d="m5 12 4 4L19 6" /><circle cx="12" cy="12" r="9" /></>,
    folder: <><path d="M3 6a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6Z" /></>,
    book: <><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v17H6.5A2.5 2.5 0 0 0 4 22V5.5Z" /><path d="M4 18a2.5 2.5 0 0 1 2.5-2.5H20" /></>,
    plus: <><path d="M12 5v14M5 12h14" /></>,
    arrow: <><path d="m8 5 7 7-7 7" /></>,
    cloud: <><path d="M7 18h10a4 4 0 0 0 .5-8A6 6 0 0 0 6 8.5 4.5 4.5 0 0 0 7 18Z" /></>,
    chat: <><path d="M20 11.5a7.5 7.5 0 0 1-8 7.5 8.5 8.5 0 0 1-4-.9L4 20l1.2-3.5A7.2 7.2 0 0 1 4 12c0-4.1 3.6-7.5 8-7.5s8 3.1 8 7Z" /></>,
  };
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}

function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const items = [
    { label: '工作台', icon: 'home' as const, href: '/' },
    { label: '今日', icon: 'check' as const, href: '/today' },
    { label: '日历', icon: 'calendar' as const, href: '/calendar' },
    { label: '收件箱', icon: 'inbox' as const, href: '/inbox' },
  ];
  return <>
    {open && <button className="vnext-scrim" aria-label="关闭导航" onClick={onClose} />}
    <aside className={`vnext-sidebar${open ? ' is-open' : ''}`} aria-label="SecondBrain 导航">
      <a className="vnext-brand" href="/" onClick={onClose}><span className="vnext-brand-mark"><SmallIcon name="brain" size={20} /></span><span>SecondBrain</span></a>
      <span className="vnext-nav-caption">个人空间</span>
      <nav className="vnext-nav">{items.map((item) => <a key={item.href} href={item.href} onClick={onClose}><SmallIcon name={item.icon} /><span>{item.label}</span></a>)}</nav>
      <div className="vnext-sidebar-bottom"><span className="vnext-avatar">SB</span><span><strong>个人工作区</strong><small>本地预览</small></span><span className="vnext-presence" /></div>
    </aside>
  </>;
}

function TaskList({ tasks, today, presentation, onToggle }: {
  tasks: WorkbenchTask[]; today: string; presentation: TaskPresentation; onToggle: (task: WorkbenchTask) => void;
}) {
  if (presentation === 'loading') return <p className="vnext-state" role="status">正在读取待办…</p>;
  if (presentation === 'unavailable') return <p className="vnext-state is-unavailable" role="alert">待办数据暂不可用</p>;
  if (presentation === 'empty' || tasks.length === 0) return <div className="vnext-empty"><span>✓</span><strong>今天没有待办</strong><small>空状态正常显示，不影响其他卡片</small></div>;
  return <ul className="vnext-task-list">{tasks.map((task) => {
    const overdue = !task.completed && task.dueDate !== null && task.dueDate < today;
    return <li className={`vnext-task${task.completed ? ' is-complete' : ''}`} key={task.id}>
      <button type="button" className="vnext-task-check" aria-label={`${task.completed ? '恢复' : '完成'}：${task.title}`} aria-pressed={task.completed} onClick={() => onToggle(task)}><span>{task.completed ? '✓' : ''}</span></button>
      <div className="vnext-task-copy">
        <div className="vnext-task-title-line">{task.importance === 'important' && <span className="vnext-important" aria-label="重要">!</span>}<span className="vnext-task-title">{task.title}</span></div>
        <div className="vnext-task-meta">
          {task.planDate && <span>计划 {displayDate(task.planDate)}</span>}
          {task.dueDate ? <span className={overdue ? 'is-overdue' : ''}>{overdue ? '已逾期 · ' : '截止 '}{displayDate(task.dueDate)}</span> : <span className="is-no-deadline">无截止日期</span>}
          {task.reminderAt && <span>提醒 {task.reminderAt}</span>}
        </div>
      </div>
    </li>;
  })}</ul>;
}

function WorkbenchCard({ id, index, count, onMove, children }: {
  id: WorkbenchCardId; index: number; count: number; onMove: (id: WorkbenchCardId, delta: -1 | 1) => void; children: React.ReactNode;
}) {
  return <article className={`vnext-card vnext-card-${id}`} aria-labelledby={`vnext-card-${id}`}>
    <header className="vnext-card-header"><div className="vnext-card-heading"><span className={`vnext-card-icon is-${id}`}><SmallIcon name={id === 'tasks' ? 'check' : id === 'review' ? 'inbox' : id === 'projects' ? 'folder' : 'book'} /></span><div><h2 id={`vnext-card-${id}`}>{cardLabels[id]}</h2><span className="vnext-demo-tag">演示数据</span></div></div>
      <div className="vnext-card-order"><button type="button" aria-label={`将「${cardLabels[id]}」上移`} disabled={index === 0} onClick={() => onMove(id, -1)}>↑</button><button type="button" aria-label={`将「${cardLabels[id]}」下移`} disabled={index === count - 1} onClick={() => onMove(id, 1)}>↓</button></div>
    </header>
    <div className="vnext-card-body">{children}</div>
  </article>;
}

export function VNextWorkbench({ now: suppliedNow, initialTasks, initialCardIds, taskPresentation = 'ready' }: VNextWorkbenchProps) {
  const [now, setNow] = useState(() => suppliedNow ?? new Date());
  const today = dateKey(now);
  const [tasks, setTasks] = useState<WorkbenchTask[]>(() => initialTasks ?? demoTasks(suppliedNow ?? new Date()));
  const [cardIds, setCardIds] = useState<WorkbenchCardId[]>(() => initialCardIds ?? ['tasks', 'review', 'projects']);
  const [addMenuOpen, setAddMenuOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [undo, setUndo] = useState<{ tasks: WorkbenchTask[]; title: string } | null>(null);
  const [time, setTime] = useState(() => new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit', hour12: false }).format(suppliedNow ?? new Date()));
  useEffect(() => {
    if (suppliedNow) return;
    const timer = window.setInterval(() => {
      const value = new Date(); setNow(value);
      setTime(new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit', hour12: false }).format(value));
    }, 60_000);
    return () => window.clearInterval(timer);
  }, [suppliedNow]);

  const dateLabel = useMemo(() => new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', weekday: 'long', month: 'long', day: 'numeric' }).format(now), [now]);
  const moveCard = (id: WorkbenchCardId, delta: -1 | 1) => setCardIds((current) => {
    const index = current.indexOf(id); const target = index + delta;
    if (index < 0 || target < 0 || target >= current.length) return current;
    const next = [...current]; [next[index], next[target]] = [next[target], next[index]]; return next;
  });
  const addKnowledge = () => {
    setCardIds((current) => current.includes('knowledge') ? current : [...current, 'knowledge']);
    setAddMenuOpen(false);
  };
  const toggleTask = (task: WorkbenchTask) => {
    setUndo({ tasks, title: task.title });
    setTasks((current) => current.map((item) => item.id === task.id ? { ...item, completed: !item.completed } : item));
  };
  const undoTask = () => {
    if (!undo) return;
    setTasks(undo.tasks); setUndo(null);
  };

  const renderCard = (id: WorkbenchCardId, index: number) => <WorkbenchCard key={id} id={id} index={index} count={cardIds.length} onMove={moveCard}>
    {id === 'tasks' && <>
      <div className="vnext-card-summary"><strong>{tasks.filter((task) => !task.completed).length}</strong><span>项未完成</span></div>
      <TaskList tasks={tasks} today={today} presentation={taskPresentation} onToggle={toggleTask} />
      <a className="vnext-card-link" href="/today">查看全部待办 <SmallIcon name="arrow" size={15} /></a>
    </>}
    {id === 'review' && <>
      <div className="vnext-card-summary"><strong>2</strong><span>条待确认</span></div>
      <ul className="vnext-simple-list"><li><span className="vnext-list-dot is-blue" /><span>读书笔记：第二大脑方法</span><time>10:24</time></li><li><span className="vnext-list-dot is-violet" /><span>会议记录：产品规划</span><time>昨天</time></li></ul>
      <a className="vnext-card-link" href="/review">打开待审核 <SmallIcon name="arrow" size={15} /></a>
    </>}
    {id === 'projects' && <>
      <div className="vnext-project-row"><div><strong>个人知识系统</strong><span>下一步：整理本周收集</span></div><strong>68%</strong></div><div className="vnext-progress"><span style={{ width: '68%' }} /></div>
      <div className="vnext-project-row"><div><strong>年度阅读计划</strong><span>下一步：完成章节回顾</span></div><strong>42%</strong></div><div className="vnext-progress is-violet"><span style={{ width: '42%' }} /></div>
      <a className="vnext-card-link" href="/projects">查看项目 <SmallIcon name="arrow" size={15} /></a>
    </>}
    {id === 'knowledge' && <>
      <div className="vnext-card-summary"><strong>3</strong><span>条最近知识</span></div>
      <ul className="vnext-simple-list"><li><span className="vnext-list-dot is-teal" /><span>渐进式总结的四个层级</span><time>今天</time></li><li><span className="vnext-list-dot is-blue" /><span>项目复盘模板</span><time>昨天</time></li><li><span className="vnext-list-dot is-amber" /><span>读书卡片：系统思考</span><time>周一</time></li></ul>
      <a className="vnext-card-link" href="/knowledge">浏览知识库 <SmallIcon name="arrow" size={15} /></a>
    </>}
  </WorkbenchCard>;

  return <div className="vnext-shell">
    <Sidebar open={mobileNavOpen} onClose={() => setMobileNavOpen(false)} />
    <main className="vnext-main">
      <header className="vnext-topbar"><button className="vnext-menu-button" aria-label="打开导航" aria-expanded={mobileNavOpen} onClick={() => setMobileNavOpen((open) => !open)}>☰</button><div><p className="vnext-eyebrow">SECONDBRAIN <span>/</span> 工作台</p><h1>你好，今天也为重要的事留些空间。</h1></div>
        <div className="vnext-top-info"><div className="vnext-date"><strong>{dateLabel}</strong><span>{time}</span></div><div className="vnext-weather"><SmallIcon name="cloud" size={21} /><span><strong>天气暂未接入</strong><small>不显示模拟天气</small></span></div></div>
      </header>
      <div className="vnext-demo-banner"><span className="vnext-demo-dot" /><span><strong>本地演示模式</strong> · 卡片内容为合成示例，不读取或写入真实 Core 数据。</span></div>
      <div className="vnext-content-layout">
        <section className="vnext-content" aria-label="工作台卡片">
          <div className="vnext-cards">{cardIds.map((id, index) => renderCard(id, index))}</div>
          <div className="vnext-add-wrap"><button type="button" className="vnext-add-button" aria-expanded={addMenuOpen} onClick={() => setAddMenuOpen((open) => !open)}><SmallIcon name="plus" />添加卡片</button>
            {addMenuOpen && <div className="vnext-add-menu" role="group" aria-label="可添加卡片"><span>添加到工作台</span><button type="button" disabled={cardIds.includes('knowledge')} onClick={addKnowledge}>最近知识{cardIds.includes('knowledge') ? ' · 已添加' : ''}</button></div>}
          </div>
        </section>
        <aside className="vnext-workspace-rail" aria-label="工作区与快捷操作">
          <section className="vnext-rail-card"><p className="vnext-rail-label">工作区</p><div className="vnext-workspace-identity"><span className="vnext-avatar">SB</span><div><strong>个人工作区</strong><small>仅自己可见</small></div></div><div className="vnext-rail-divider" /><a href="/today">今日待办 <SmallIcon name="arrow" size={15} /></a><a href="/review">待审核内容 <SmallIcon name="arrow" size={15} /></a></section>
          <section className="vnext-rail-card vnext-ai-card"><span className="vnext-ai-icon"><SmallIcon name="chat" size={20} /></span><p className="vnext-rail-label">AI 助手</p><h2>把想法变成下一步</h2><p>从新的对话开始整理思路、记录内容或推进任务。</p><a className="vnext-ai-link" href="/chat" target="_blank" rel="noreferrer">新建 AI 对话 <SmallIcon name="arrow" size={15} /></a><small className="vnext-ai-note">前往现有对话入口；本预览不会创建会话。</small></section>
          <div className="vnext-rail-note"><span>✦</span><p>待办日期区分计划日期、截止日期和提醒时间；目前后两项需要后端数据合同支持。</p></div>
        </aside>
      </div>
      {undo && <div className="vnext-toast" role="status"><span>已更新「{undo.title}」</span><button type="button" onClick={undoTask}>撤销</button></div>}
    </main>
  </div>;
}

export { TaskList, demoTasks, dateKey };
