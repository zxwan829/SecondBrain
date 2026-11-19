import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { V1ReadOnlyPage } from './V1ReadOnlyPages';
import { V1BriefHealthPage } from './V1BriefHealthPages';

const checkedAt = '2026-10-20T01:30:00Z';
const hash = 'b'.repeat(64);

function projectPayload(status: string, limit = 50, offset = 0, hasMore = false) {
  return {
    status,
    items: status === 'real' || status === 'partial' ? [{ id: 'project_ui_synth', title: 'Synthetic project card', status: 'active', next_step: 'Synthetic next action', source_ref: { id: 'project_source_opaque', version: hash } }] : [],
    pagination: { limit, offset, has_more: hasMore },
    source: status === 'not_configured' || status === 'unavailable' ? null : { kind: 'explicit-project-index' },
    freshness: { checked_at: checkedAt },
  };
}

function briefPayload(status: string, date: string) {
  const hasRecord = status === 'real';
  return {
    status,
    items: hasRecord ? [{ brief_id: 'brief_ui_synth', date, timezone: 'Asia/Shanghai', generated_at: checkedAt,
      generation_status: status === 'real' ? 'generated' : status, categories: ['Synthetic category'],
      summary: 'SYNTHETIC BRIEF BODY ONLY', source_refs: [{ kind: 'task', id: 'opaque_task_source', version: hash }] }] : [],
    source: status === 'not_configured' ? null : { kind: 'core-daily-brief-store' },
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
    expect(calls).toEqual(['/api/projects?limit=50&offset=0']);
  });

  it('renders only Core-confirmed project fields and not opaque source IDs', async () => {
    mockFetch(() => Response.json(projectPayload('real')));
    render(<V1ReadOnlyPage page="projects" locale="zh-CN" />);
    expect(await screen.findByText('Synthetic project card')).toBeTruthy();
    expect(screen.getByText('Synthetic next action')).toBeTruthy();
    expect(screen.queryByText('project_source_opaque')).toBeNull();
  });

  it('paginates the Core project registry so a brief source beyond the first page can be found', async () => {
    const calls = mockFetch((url) => {
      const offset = Number(new URL(`http://local${url}`).searchParams.get('offset'));
      return Response.json(projectPayload(offset === 0 ? 'real' : 'empty', 50, offset, offset === 0));
    });
    render(<V1ReadOnlyPage page="projects" locale="zh-CN" />);
    expect(await screen.findByText('Synthetic project card')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '更多项目' }));
    await waitFor(() => expect(calls).toContain('/api/projects?limit=50&offset=50'));
    expect(await screen.findByText(/可信项目索引已读取，但当前没有项目记录/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '上一页项目' }));
    await waitFor(() => expect(calls.filter((url) => url === '/api/projects?limit=50&offset=0')).toHaveLength(2));
    expect(await screen.findByText('Synthetic project card')).toBeTruthy();
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
    expect(screen.getByRole('link', { name: '返回待办来源' }).getAttribute('href')).toMatch(/^\/today\?task_id=opaque_task_source$/);
    expect(screen.queryByText('opaque_task_source')).toBeNull();
  });

  it('offers exact links back to synthetic Task, Project and Journal source views', async () => {
    mockFetch((url) => {
      const date = new URL(`http://local${url}`).searchParams.get('date') ?? '';
      const response = briefPayload('real', date) as { items: Array<{ source_refs: unknown[] }> };
      response.items[0].source_refs = [
        { kind: 'task', id: 'a'.repeat(32), version: hash },
        { kind: 'project', id: 'project_ui_synth', version: hash },
        { kind: 'journal', id: 'journal_entry_synth', version: hash },
      ];
      return Response.json(response);
    });
    render(<V1BriefHealthPage page="brief" locale="zh-CN" />);
    expect((await screen.findByRole('link', { name: '返回待办来源' })).getAttribute('href')).toBe(`/today?task_id=${'a'.repeat(32)}`);
    expect(screen.getByRole('link', { name: '返回项目来源列表' }).getAttribute('href')).toBe('/projects?project_id=project_ui_synth');
    expect(screen.getByRole('link', { name: '返回 Journal 日期' }).getAttribute('href')).toMatch(/^\/journal\?date=\d{4}-\d{2}-\d{2}&entry_id=journal_entry_synth$/);
  });

  it('shows stale status visibly when Core withholds the stale summary', async () => {
    mockFetch((url) => Response.json(briefPayload('stale', new URL(`http://local${url}`).searchParams.get('date') ?? '')));
    render(<V1BriefHealthPage page="brief" locale="zh-CN" />);
    expect(await screen.findByText(/简报来源已过期；Core 已隐藏摘要内容/)).toBeTruthy();
    expect(screen.queryByText('SYNTHETIC BRIEF BODY ONLY')).toBeNull();
  });

  it('shows partial source verification explicitly when Core withholds unverified content', async () => {
    mockFetch((url) => Response.json(briefPayload('partial', new URL(`http://local${url}`).searchParams.get('date') ?? '')));
    render(<V1BriefHealthPage page="brief" locale="zh-CN" />);
    expect(await screen.findByText(/简报来源尚未核验；Core 已隐藏摘要内容/)).toBeTruthy();
    expect(screen.queryByText('SYNTHETIC BRIEF BODY ONLY')).toBeNull();
  });

  it('shows failed and configured unavailable states without substituting content', async () => {
    const calls = mockFetch((url) => Response.json(briefPayload('failed', new URL(`http://local${url}`).searchParams.get('date') ?? '')));
    render(<V1BriefHealthPage page="brief" locale="zh-CN" />);
    expect(await screen.findByText(/该日期的简报处理明确失败/)).toBeTruthy();
    expect(screen.queryByText('SYNTHETIC BRIEF BODY ONLY')).toBeNull();
    expect(calls).toHaveLength(1);
    cleanup();
    vi.stubGlobal('fetch', vi.fn(async () => Response.json(briefPayload('unavailable', '2026-10-20'))));
    render(<V1BriefHealthPage page="brief" locale="zh-CN" />);
    expect(await screen.findByText(/该页面数据暂不可用/)).toBeTruthy();
  });

  it('maps authorization failures to the visible denied state', async () => {
    mockFetch(() => new Response('{}', { status: 403 }));
    render(<V1BriefHealthPage page="brief" locale="zh-CN" />);
    expect((await screen.findByRole('alert')).textContent).toContain('当前账户无权读取此页面数据。');
  });
});
