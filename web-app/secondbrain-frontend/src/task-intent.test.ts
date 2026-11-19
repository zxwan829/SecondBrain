import { describe, expect, it } from 'vitest';
import { parseExplicitTaskCommand } from './task-intent';

describe('explicit Chat Task intent', () => {
  it.each([
    ['添加待办：写周报', { operation: 'create', title: '写周报', due_date: null }],
    ['请帮我创建一个待办：写周报', { operation: 'create', title: '写周报', due_date: null }],
    ['麻烦帮我新建待办：写周报 截止日期：2026-11-10', { operation: 'create', title: '写周报', due_date: '2026-11-10' }],
    ['提醒我：提交设计稿', { operation: 'create', title: '提交设计稿', due_date: null }],
    ['查询今天未完成的待办', { operation: 'list_today_open' }],
    ['请把待办“写周报”标记为已完成', { operation: 'complete', title: '写周报' }],
    ['修改待办“写周报”的截止日期为2026-11-10', { operation: 'set_due_date', title: '写周报', due_date: '2026-11-10' }],
    ['修改待办：写周报 截止日期：2026-11-10', { operation: 'set_due_date', title: '写周报', due_date: '2026-11-10' }],
  ] as const)('routes the explicit request %s', (command, expected) => {
    expect(parseExplicitTaskCommand(command)).toEqual(expected);
  });

  it.each([
    '我们后面可以添加待办：写周报',
    '我想创建一个待办：写周报',
    '写周报吧',
    '提醒我提交设计稿',
    '我今天想查询未完成的待办',
    '等写周报的时候把待办标记完成',
    '我们应该把待办“写周报”标记为已完成',
  ])('keeps ambiguous or narrative text in Chat: %s', (text) => {
    expect(parseExplicitTaskCommand(text)).toBeNull();
  });
});
