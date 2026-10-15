import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { AutomationSettingsPage } from './App';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const jsonResponse = (body: unknown, ok = true, status = 200) => ({
  ok, status, json: async () => body,
});

const setupFetch = (mockCheck: () => Promise<unknown>) => vi.fn((input: RequestInfo | URL) => {
  const path = String(input);
  if (path.endsWith('/settings')) return Promise.resolve(jsonResponse({ enabled: false, mode: 'interval', interval_hours: 4, daily_time: '00:30', timezone: 'Asia/Shanghai' }));
  if (path.endsWith('/status')) return Promise.resolve(jsonResponse({ execution_available: false, state: 'disabled', budget: { daily_requests: 0, daily_limit: 12, daily_remaining: 12, monthly_estimated_cny: 0, monthly_soft_limit_cny: 10, monthly_remaining_estimate_cny: 10 } }));
  if (path.endsWith('/model-settings')) return Promise.resolve(jsonResponse({ provider: 'siliconflow', model: 'deepseek-ai/DeepSeek-V4-Flash', model_enabled: false, scheduler_enabled: false, monthly_soft_budget_cny: 10, api_key_configured: false }));
  if (path.endsWith('/connection-test')) return mockCheck();
  throw new Error(`Unexpected request: ${path}`);
});

describe('Organizer settings interactions', () => {
  it('shows a pending state then explicit local-only success without a model run', async () => {
    let resolveCheck!: (value: unknown) => void;
    const check = new Promise((resolve) => { resolveCheck = resolve; });
    const fetchMock = setupFetch(() => check);
    vi.stubGlobal('fetch', fetchMock);
    render(<AutomationSettingsPage locale="zh-CN" />);
    const button = await screen.findByRole('button', { name: '执行本地 Mock 检查' });
    fireEvent.click(button);
    expect(await screen.findByText('正在检查本地配置…')).toBeTruthy();
    expect(screen.getByRole('button', { name: '检查中…' })).toHaveProperty('disabled', true);
    resolveCheck(jsonResponse({ kind: 'local_mock', message: 'configured' }));
    expect(await screen.findByText('本地 Mock 检查通过，未连接 SiliconFlow，不产生供应商费用。')).toBeTruthy();
    expect(fetchMock.mock.calls.some(([path]) => String(path).endsWith('/run'))).toBe(false);
    expect(screen.getByText('deepseek-ai/DeepSeek-V4-Flash')).toBeTruthy();
    expect(screen.queryByRole('combobox', { name: /当前支持模型/ })).toBeNull();
    expect(screen.getByLabelText('允许手动整理使用模型')).toHaveProperty('checked', false);
    expect(screen.getByLabelText('启用 Scheduler')).toHaveProperty('checked', false);
  });

  it('shows an understandable authorization/API failure', async () => {
    const fetchMock = setupFetch(() => Promise.resolve(jsonResponse({ detail: 'Session expired' }, false, 403)));
    vi.stubGlobal('fetch', fetchMock);
    render(<AutomationSettingsPage locale="zh-CN" />);
    fireEvent.click(await screen.findByRole('button', { name: '执行本地 Mock 检查' }));
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.getByRole('alert').textContent).toContain('Session expired');
  });

  it('shows a connection error when the local API request rejects', async () => {
    const fetchMock = setupFetch(() => Promise.reject(new TypeError('network failure')));
    vi.stubGlobal('fetch', fetchMock);
    render(<AutomationSettingsPage locale="zh-CN" />);
    fireEvent.click(await screen.findByRole('button', { name: '执行本地 Mock 检查' }));
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.getByRole('alert').textContent).toContain('无法连接本地检查接口');
  });
});
