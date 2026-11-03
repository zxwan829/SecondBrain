import React from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { VNextWorkbench } from './VNextWorkbench';

const now = new Date('2026-11-03T04:00:00.000Z');

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('VNext workbench prototype', () => {
  it('labels synthetic content and renders the first three registered cards', () => {
    const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
    render(<VNextWorkbench now={now} />);
    expect(screen.getByText(/本地演示模式/)).toBeTruthy();
    expect(screen.getByText(/不读取或写入真实 Core 数据/)).toBeTruthy();
    expect(screen.getByRole('heading', { name: '今日待办' })).toBeTruthy();
    expect(screen.getByRole('heading', { name: '待审核' })).toBeTruthy();
    expect(screen.getByRole('heading', { name: '项目进度' })).toBeTruthy();
    expect(screen.queryByRole('heading', { name: '最近知识' })).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('distinguishes plan date, hard deadline, reminder, overdue and no-deadline rows', () => {
    const { container } = render(<VNextWorkbench now={now} />);
    const firstTaskMeta = container.querySelector('.vnext-task-meta');
    expect(firstTaskMeta?.textContent).toContain('已逾期');
    expect(firstTaskMeta?.textContent).toContain('11/2');
    expect(screen.getByText(/计划 11\/3/)).toBeTruthy();
    expect(screen.getByText('提醒 18:00')).toBeTruthy();
    expect(screen.getByText('无截止日期')).toBeTruthy();
    expect(screen.getByText(/回顾本周项目进展/)).toBeTruthy();
  });

  it('toggles a demo task and restores the exact previous state with undo without a write request', () => {
    const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
    render(<VNextWorkbench now={now} />);
    fireEvent.click(screen.getByRole('button', { name: '完成：整理明天会议材料' }));
    expect(screen.getByRole('button', { name: '恢复：整理明天会议材料' }).getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(screen.getByRole('button', { name: '撤销' }));
    expect(screen.getByRole('button', { name: '完成：整理明天会议材料' }).getAttribute('aria-pressed')).toBe('false');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('shows loading, unavailable and empty task states without fabricating records', () => {
    const { rerender } = render(<VNextWorkbench now={now} taskPresentation="loading" />);
    expect(screen.getByRole('status').textContent).toContain('正在读取待办');
    rerender(<VNextWorkbench now={now} taskPresentation="unavailable" />);
    expect(screen.getByRole('alert').textContent).toContain('待办数据暂不可用');
    rerender(<VNextWorkbench now={now} taskPresentation="empty" initialTasks={[]} />);
    expect(screen.getByText('今天没有待办')).toBeTruthy();
  });

  it('keeps a very long Chinese task title present and allows it to wrap', () => {
    const title = '这是一个用于验证极长中文待办标题在窄屏和卡片布局中仍然可以自然换行而不会撑破工作台容器的合成测试标题'.repeat(3);
    render(<VNextWorkbench now={now} initialTasks={[{ id: 'long-title', title, planDate: null, dueDate: null, reminderAt: null, importance: 'normal', completed: false }]} />);
    expect(screen.getByText(title)).toBeTruthy();
  });

  it('can add the fourth registered card and reorder cards without changing their contents', () => {
    render(<VNextWorkbench now={now} />);
    fireEvent.click(screen.getByRole('button', { name: '添加卡片' }));
    fireEvent.click(screen.getByRole('button', { name: '最近知识' }));
    expect(screen.getByRole('heading', { name: '最近知识' })).toBeTruthy();
    const reviewCard = screen.getByRole('article', { name: '待审核' });
    fireEvent.click(within(reviewCard).getByRole('button', { name: '将「待审核」上移' }));
    const cards = screen.getAllByRole('article').map((card) => card.getAttribute('aria-labelledby'));
    expect(cards.slice(0, 3)).toEqual(['vnext-card-review', 'vnext-card-tasks', 'vnext-card-projects']);
    expect(within(screen.getByRole('article', { name: '待审核' })).getByText('读书笔记：第二大脑方法')).toBeTruthy();
  });

  it('keeps the existing chat route target without creating a session', () => {
    render(<VNextWorkbench now={now} />);
    expect(screen.getByRole('link', { name: /新建 AI 对话/ }).getAttribute('href')).toBe('/chat');
  });
});
