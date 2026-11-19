export type ExplicitTaskCommand =
  | { operation: 'create'; title: string; due_date: string | null }
  | { operation: 'list_today_open' }
  | { operation: 'complete'; title: string }
  | { operation: 'set_due_date'; title: string; due_date: string };

const CREATE_TASK = /^\s*(?:(?:(?:请|麻烦)?\s*(?:帮我)?\s*(?:添加|创建|新建)(?:一个)?待办)|(?:(?:请|麻烦)?\s*(?:帮我)?\s*加(?:一个)?待办)|建个待办|待办|(?:(?:请|麻烦)?\s*提醒我))[：:]\s*([\s\S]+?)\s*$/;
const CREATE_DUE_DATE = /\s+截止(?:日期)?[：:]\s*(\d{4}-\d{2}-\d{2})\s*$/;
const LIST_TODAY_OPEN = /^\s*(?:(?:请|麻烦)?\s*)?(?:查询|查|看看|查看)(?:一下)?(?:今天|今日)(?:还)?(?:未完成|没完成|未办)(?:的)?待办\s*[？?。！!]*\s*$/;
const COMPLETE_TASK = /^\s*(?:(?:请|麻烦)?\s*)?(?:把|将)\s*(?:待办)?[“"「](.+?)[”"」]\s*(?:这个)?(?:待办)?\s*(?:标记为|标记成|设为)(?:已完成|完成)\s*[。！!]?\s*$/;
const COMPLETE_TASK_PREFIX = /^\s*(?:(?:请|麻烦)?\s*)?(?:标记|完成)待办\s*[：:]\s*(.+?)\s*$/;
const SET_DUE_DATE = /^\s*(?:(?:请|麻烦)?\s*)?(?:修改|设置|把|将)\s*(?:待办)?[“"「](.+?)[”"」]\s*(?:这个)?(?:待办)?(?:的)?截止(?:日期)?(?:改为|设为|修改为|为|：|:)\s*(\d{4}-\d{2}-\d{2})\s*[。！!]?\s*$/;
const SET_DUE_DATE_PREFIX = /^\s*(?:(?:请|麻烦)?\s*)?修改待办\s*[：:]\s*(.+?)\s+截止(?:日期)?[：:]\s*(\d{4}-\d{2}-\d{2})\s*$/;

export function parseExplicitTaskCommand(text: string): ExplicitTaskCommand | null {
  if (LIST_TODAY_OPEN.test(text)) return { operation: 'list_today_open' };
  const complete = COMPLETE_TASK.exec(text) || COMPLETE_TASK_PREFIX.exec(text);
  if (complete?.[1]) {
    const title = complete[1].trim();
    return title ? { operation: 'complete', title } : null;
  }
  const due = SET_DUE_DATE.exec(text) || SET_DUE_DATE_PREFIX.exec(text);
  if (due?.[1] && due[2]) {
    const title = due[1].trim();
    return title ? { operation: 'set_due_date', title, due_date: due[2] } : null;
  }
  const create = CREATE_TASK.exec(text);
  if (!create?.[1]) return null;
  const body = create[1].trim();
  const dueDate = CREATE_DUE_DATE.exec(body);
  const title = (dueDate ? body.slice(0, dueDate.index) : body).trim();
  return title ? { operation: 'create', title, due_date: dueDate?.[1] ?? null } : null;
}
