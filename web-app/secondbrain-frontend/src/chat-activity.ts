export type ChatActivity = {
  event_id: string;
  operation_id: string;
  session_id: string;
  kind: 'journal' | 'task';
  status: 'succeeded' | 'failed' | 'processing' | 'unknown';
  original_text: string;
  occurred_at: string;
  journal_date?: string | null;
  task_id?: string | null;
  task_title?: string | null;
  task_due_date?: string | null;
  task_status?: 'open' | 'completed' | null;
  detail?: string;
  transient?: boolean;
};

export type ChatHistoryMessage = {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  timestamp?: string | null;
};

export type ChatTimelineItem =
  | { type: 'message'; id: string; timestamp?: string | null; sequence: number; message: ChatHistoryMessage }
  | { type: 'activity'; id: string; timestamp?: string | null; sequence: number; activity: ChatActivity };

function timeValue(value?: string | null): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** Merge independent stores by recorded timestamps; ties use stable source order. */
export function mergeChatTimeline(messages: ChatHistoryMessage[], activities: ChatActivity[]): ChatTimelineItem[] {
  const items: ChatTimelineItem[] = [
    ...messages.map((message, sequence) => ({ type: 'message' as const, id: `message:${message.id}`, timestamp: message.timestamp, sequence, message })),
    ...activities.map((activity, sequence) => ({ type: 'activity' as const, id: activity.event_id, timestamp: activity.occurred_at, sequence, activity })),
  ];
  return items.sort((left, right) => {
    const leftTime = timeValue(left.timestamp);
    const rightTime = timeValue(right.timestamp);
    if (leftTime !== null && rightTime !== null && leftTime !== rightTime) return leftTime - rightTime;
    if (leftTime !== null && rightTime === null) return -1;
    if (leftTime === null && rightTime !== null) return 1;
    if (left.type !== right.type) return left.type === 'message' ? -1 : 1;
    return left.sequence - right.sequence || left.id.localeCompare(right.id);
  });
}

export function activityTimeLabel(value: string, locale: 'zh-CN' | 'en'): string {
  const time = timeValue(value);
  if (time === null) return locale === 'en' ? 'Time unknown' : '时间未知';
  return new Date(time).toLocaleString(locale === 'en' ? 'en-US' : 'zh-CN');
}
