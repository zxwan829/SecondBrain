import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('./api/home', () => ({ fetchHome: vi.fn(async () => ({})) }));
vi.mock('./NotesPage', () => ({ NotesPage: () => <h1>合成 Notes 页面</h1> }));

import { App } from './App';

const syntheticCollections = { collections: [{ id: 'drafts', kind: 'drafts' }] };

function mockAppFetch(notesStatus = 200) {
  const calls: string[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input);
    calls.push(url);
    if (url === '/api/auth/session') return new Response('{}', { status: 200 });
    if (url === '/api/notes') return new Response(JSON.stringify(notesStatus === 200 ? syntheticCollections : { detail: 'synthetic gate denial' }), { status: notesStatus });
    return new Response('{}', { status: 200 });
  });
  return calls;
}

function startAt(path = '/') {
  localStorage.clear();
  history.replaceState({}, '', path);
  return render(<App />);
}

describe('Notes application navigation gate', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    history.replaceState({}, '', '/');
    localStorage.clear();
  });

  it('keeps Notes hidden and redirects a deep link when its feature flag is off', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'false');
    mockAppFetch();
    startAt('/notes/drafts/example');

    await screen.findByRole('heading', { name: '你的工作台' });
    await waitFor(() => expect(location.pathname).toBe('/'));
    expect(screen.queryByRole('button', { name: '笔记' })).toBeNull();
    expect(screen.queryByRole('heading', { name: '合成 Notes 页面' })).toBeNull();
  });

  it.each([403, 503])('keeps Notes unavailable and redirects a deep link when Core returns HTTP %i', async (status) => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    const calls = mockAppFetch(status);
    startAt('/notes');

    await screen.findByRole('heading', { name: '你的工作台' });
    await waitFor(() => expect(location.pathname).toBe('/'));
    expect(calls.filter((url) => url === '/api/notes')).toHaveLength(1);
    expect(screen.queryByRole('button', { name: '笔记' })).toBeNull();
    expect(screen.queryByRole('heading', { name: '合成 Notes 页面' })).toBeNull();
  });

  it('opens and leaves Notes through desktop navigation after the Core read gate succeeds', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    mockAppFetch();
    startAt('/');

    const notesButton = await screen.findByRole('button', { name: '笔记' });
    fireEvent.click(notesButton);
    expect(await screen.findByRole('heading', { name: '合成 Notes 页面' })).toBeTruthy();
    expect(location.pathname).toBe('/notes');

    fireEvent.click(screen.getByRole('button', { name: '首页' }));
    await screen.findByRole('heading', { name: '你的工作台' });
    expect(location.pathname).toBe('/');
  });

  it('restores the Notes route on refresh and opens it from the mobile menu', async () => {
    vi.stubEnv('VITE_ENABLE_NOTES', 'true');
    mockAppFetch();
    startAt('/notes');
    expect(await screen.findByRole('heading', { name: '合成 Notes 页面' })).toBeTruthy();
    expect(location.pathname).toBe('/notes');

    fireEvent.click(screen.getByRole('button', { name: '打开导航菜单' }));
    const sidebar = document.querySelector('aside.sidebar') as HTMLElement;
    expect(sidebar.classList.contains('is-open')).toBe(true);
    fireEvent.click(within(sidebar).getByRole('button', { name: '笔记' }));
    expect(location.pathname).toBe('/notes');
    expect(screen.getByRole('button', { name: '打开导航菜单' }).getAttribute('aria-expanded')).toBe('false');
    expect(await screen.findByRole('heading', { name: '合成 Notes 页面' })).toBeTruthy();
  });
});
