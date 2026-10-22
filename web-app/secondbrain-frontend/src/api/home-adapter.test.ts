import { describe, expect, it } from 'vitest';
import { adaptHome } from './home-adapter';

describe('adaptHome trust states', () => {
  it('does not turn unconfigured empty arrays into confirmed empty business data', () => {
    const view = adaptHome({
      status: 'ok',
      today: { status: 'not_configured', items: [] },
      projects: { status: 'not_configured', items: [] },
      knowledge: { status: 'unavailable', items: [] },
      agent: { status: 'not_configured', source: 'hermes-runtime' },
    });

    expect(view.today).toEqual({ kind: 'unknown', source: 'UNAVAILABLE' });
    expect(view.projectSource).toBe('UNAVAILABLE');
    expect(view.knowledgeSource).toBe('UNAVAILABLE');
    expect(view.agentStatus).toBe('not_configured');
  });

  it('keeps a confirmed empty Today distinct from unavailable and only accepts explicit runtime statuses', () => {
    const view = adaptHome({
      status: 'ok',
      today: { status: 'empty', items: [] },
      agent: { status: 'unavailable', source: 'hermes-runtime' },
    });

    expect(view.today).toEqual({ kind: 'empty', source: 'REAL' });
    expect(view.agentStatus).toBe('unavailable');
    expect(adaptHome({ agent: { status: 'actually-online', source: 'hermes-runtime' } }).agentStatus).toBeNull();
  });

  it('does not publish Review metadata when the Home source is unavailable', () => {
    const view = adaptHome({
      review: { status: 'unavailable', items: [{ title: 'untrusted stale row' }], pending_count: 1 },
    });
    expect(view.reviewSource).toBe('UNAVAILABLE');
    expect(view.review).toEqual([]);
    expect(view.pendingCount).toBeNull();
  });
});
