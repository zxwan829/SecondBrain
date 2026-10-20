import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { V1ReadOnlyPage } from './V1ReadOnlyPages';
import { V1BriefHealthPage } from './V1BriefHealthPages';

const checkedAt = '2026-10-20T01:30:00Z';
const hash = 'b'.repeat(64);

function projectPayload(status: string) {
  return {
    status,
    items: status === 'real' || status === 'partial' ? [{ id: 'project_ui_synth', title: 'Synthetic project card', status: 'active', next_step: 'Synthetic next action', source_ref: { id: 'project_source_opaque', version: hash } }] : [],
    pagination: { limit: 1, offset: 0, has_more: false },
    source: status === 'not_configured' || status === 'unavailable' ? null : { kind: 'explicit-project-index' },
    freshness: { checked_at: checkedAt },
  };
}

function briefPayload(status: string, date: string) {
  const hasRecord = ['real', 'partial', 'stale', 'failed'].includes(status);
  return {
    status,
    items: hasRecord ? [{ brief_id: 'brief_ui_synth', date, timezone: 'Asia/Shanghai', generated_at: checkedAt,
      generation_status: status === 'real' ? 'generated' : status, categories: ['Synthetic category'],
      summary: 'SYNTHETIC BRIEF BODY ONLY', source_refs: [{ kind: 'task', id: 'opaque_task_source', version: hash }] }] : [],
    source: status === 'not_configured' || status === 'unavailable' ? null : { kind: 'core-daily-brief-store' },
    freshness: { checked_at: checkedAt },
  };
}

function mockFetch(build: (url: string) => Response) {
  const calls: string[] = [];
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input); calls.push(url); return build(url);
  }));
  return calls;
}

describe('Projects and Daily Brief read-only UI', () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it('shows the Core not_configured Projects state without inferring or displaying preview records', async () => {
    const calls = mockFetch(() => Response.json(projectPayload('not_configured')));
    render(<V1ReadOnlyPage page="projects" locale="zh-CN" />);
    expect(await screen.findByText(/NOT BUSINESS CLOSED.*尚未配置可信项目数据源/)).toBeTruthy();
    expect(screen.queryByText('Synthetic project card')).toBeNull();
    expect(calls).toEqual(['/api/projects?limit=1&offset=0']);
  });

  it('renders only Core-confirmed project fields and not opaque source IDs', async () => {
    mockFetch(() => Response.json(projectPayload('real')));
    render(<V1ReadOnlyPage page="projects" locale="zh-CN" />);
    expect(await screen.findByText('Synthetic project card')).toBeTruthy();
    expect(screen.getByText('Synthetic next action')).toBeTruthy();
    expect(screen.queryByText('project_source_opaque')).toBeNull();
  });

  it('keeps a partial project response visibly partial', async () => {
    mockFetch(() => Response.json(projectPayload('partial')));
    render(<V1ReadOnlyPage page="projects" locale="zh-CN" />);
    expect(await screen.findByText(/部分项目来源或关联未通过核验/)).toBeTruthy();
    expect(screen.getByText('Synthetic project card')).toBeTruthy();
  });

  it('shows no configured Brief as not business closed and does not generate content', async () => {
    const calls = mockFetch((url) => Response.json(briefPayload('not_configured', new URL(`http://local${url}`).searchParams.get('date') ?? '')));
    render(<V1BriefHealthPage page="brief" locale="zh-CN" />);
    expect(await screen.findByText(/NOT BUSINESS CLOSED.*DAILY_BRIEF_NOT_CONFIGURED/)).toBeTruthy();
    expect(screen.queryByText('SYNTHETIC BRIEF BODY ONLY')).toBeNull();
    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatch(/^\/api\/daily-brief\?date=\d{4}-\d{2}-\d{2}&timezone=Asia%2FShanghai$/);
  });

  it('renders a verified synthetic Brief with the requested date and source count', async () => {
    mockFetch((url) => Response.json(briefPayload('real', new URL(`http://local${url}`).searchParams.get('date') ?? '')));
    render(<V1BriefHealthPage page="brief" locale="zh-CN" />);
    expect(await screen.findByText('SYNTHETIC BRIEF BODY ONLY')).toBeTruthy();
    expect(screen.getByText('来源已核验')).toBeTruthy();
    expect(screen.getByText('Synthetic category')).toBeTruthy();
    expect(screen.queryByText('opaque_task_source')).toBeNull();
  });

  it('warns visibly when a persisted brief is stale', async () => {
    mockFetch((url) => Response.json(briefPayload('stale', new URL(`http://local${url}`).searchParams.get('date') ?? '')));
    render(<V1BriefHealthPage page="brief" locale="zh-CN" />);
    expect(await screen.findByText(/来源版本已变化/)).toBeTruthy();
    expect(screen.getByText('SYNTHETIC BRIEF BODY ONLY')).toBeTruthy();
  });

  it('maps authorization failures to the visible denied state', async () => {
    mockFetch(() => new Response('{}', { status: 403 }));
    render(<V1BriefHealthPage page="brief" locale="zh-CN" />);
    expect((await screen.findByRole('alert')).textContent).toContain('当前账户无权读取此页面数据。');
  });
});
