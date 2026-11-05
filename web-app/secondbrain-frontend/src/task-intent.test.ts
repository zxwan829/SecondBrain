import { describe, expect, it } from 'vitest';
import { parseExplicitTaskCommand } from './task-intent';

describe('explicit Chat Task intent', () => {
  it.each([
    ['添加待办：写周报', { title: '写周报', due_date: null }],
    ['请帮我创建一个待办：写周报', { title: '写周报', due_date: null }],
    ['麻烦帮我新建待办：写周报 截止日期：2026-11-10', { title: '写周报', due_date: '2026-11-10' }],
    ['提醒我：提交设计稿', { title: '提交设计稿', due_date: null }],
  ] as const)('routes the explicit request %s', (command, expected) => {
    expect(parseExplicitTaskCommand(command)).toEqual(expected);
  });

  it.each([
    '我们后面可以添加待办：写周报',
    '我想创建一个待办：写周报',
    '写周报吧',
    '提醒我提交设计稿',
  ])('keeps ambiguous or narrative text in Chat: %s', (text) => {
    expect(parseExplicitTaskCommand(text)).toBeNull();
  });
});
