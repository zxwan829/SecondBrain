import { describe, expect, it } from 'vitest';
import { mergeChatTimeline } from './chat-activity';

const activity = (event_id: string, occurred_at: string, session_id = 'session-a') => ({
  event_id, operation_id: event_id, session_id, kind: 'journal' as const,
  status: 'succeeded' as const, original_text: event_id, occurred_at,
});

describe('Chat timeline', () => {
  it('merges Hermes messages and durable system operations by recorded time', () => {
    const timeline = mergeChatTimeline([
      { id: 'm2', role: 'assistant', text: 'answer', timestamp: '2026-10-17T10:02:00Z' },
      { id: 'm1', role: 'user', text: 'question', timestamp: '2026-10-17T10:00:00Z' },
    ], [activity('journal-1', '2026-10-17T10:01:00Z')]);
    expect(timeline.map((item) => item.type === 'message' ? item.message.id : item.activity.event_id))
      .toEqual(['m1', 'journal-1', 'm2']);
  });

  it('keeps a stable order for equal and unknown times', () => {
    const timeline = mergeChatTimeline([
      { id: 'm1', role: 'user', text: 'one' },
      { id: 'm2', role: 'assistant', text: 'two' },
    ], [activity('journal-1', 'invalid')]);
    expect(timeline.map((item) => item.type === 'message' ? item.message.id : item.activity.event_id))
      .toEqual(['m1', 'm2', 'journal-1']);
  });

  it('sorts Hermes Unix-second and millisecond timestamps with ISO activity times', () => {
    const timeline = mergeChatTimeline([
      { id: 'after', role: 'assistant', text: 'after', timestamp: 1792195380000 },
      { id: 'before', role: 'user', text: 'before', timestamp: 1792195200 },
    ], [activity('journal-mid', '2026-10-17T00:02:00Z')]);
    expect(timeline.map((item) => item.type === 'message' ? item.message.id : item.activity.event_id))
      .toEqual(['before', 'journal-mid', 'after']);
  });
});
