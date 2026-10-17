const TASK_COMMAND = /^\s*(?:添加待办|建个待办)[：:]\s*([\s\S]+?)\s*$/;
const TASK_DUE_DATE = /\s+截止(?:日期)?[：:]\s*(\d{4}-\d{2}-\d{2})\s*$/;

export function parseExplicitTaskCommand(text: string): { title: string; due_date: string | null } | null {
  const match = TASK_COMMAND.exec(text);
  if (!match?.[1]) return null;
  const body = match[1].trim();
  const dueDate = TASK_DUE_DATE.exec(body);
  const title = (dueDate ? body.slice(0, dueDate.index) : body).trim();
  return title ? { title, due_date: dueDate?.[1] ?? null } : null;
}
