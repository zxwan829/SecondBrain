import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { PlanningPanel } from './PlanningPanel';

const sessionId = 'session-synthetic-a';
const taskId = 'a'.repeat(32);
const version = 'b'.repeat(64);
const ref = { kind: 'task', id: taskId, version };
const candidateId = 'c'.repeat(32);

function preview(revision = 1, decision: 'pending' | 'approved' = 'pending') {
  return { event: 'planning.preview', version: 1, session_id: sessionId, candidate_id: candidateId, revision,
    expires_at: '2026-10-22T08:00:00Z', status: 'ready', workflow_status: 'active', objective: 'Review synthetic task',
    steps: [{ position: 1, kind: 'review_source', source_ref: ref, reason: 'review_source', priority: 'unspecified',
      depends_on: [], decision, execution_status: 'not_started' }] };
}

function retrospective() {
  return { event: 'planning.retrospective', version: 1, session_id: sessionId, candidate_id: candidateId, revision: 1,
    workflow_status: 'active', counts: { planned: 1, approved: 0, rejected: 0, completed: 0, failed: 0, stale_sources: 0 },
    steps: [{ position: 1, source_state: 'verified', decision: 'pending', execution_status: 'not_started' }], feedback: null };
}

describe('Chat planning panel', () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); sessionStorage.clear(); });

  it('waits for explicit source loading, then creates a session-bound review candidate from selected refs only', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input); calls.push({ url, init });
      if (url === '/api/tasks?status=all') return Response.json({ tasks: [{ id: taskId, title: 'Synthetic task', status: 'open', source_ref: ref }] });
      if (url === '/api/projects?limit=50&offset=0') return Response.json({ status: 'empty', items: [] });
      if (url.endsWith('/planning/candidates') && init?.method === 'POST') return Response.json({ ...preview(), event: 'planning.candidate' });
      if (url.endsWith(`/planning/candidates/${candidateId}/retrospective`)) return Response.json(retrospective());
      if (url.endsWith(`/planning/candidates/${candidateId}`)) return Response.json(preview());
      throw new Error(`Unexpected request ${url}`);
    }));

    render(<PlanningPanel locale="en" sessionId={sessionId} />);
    expect(calls).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: 'Open planning' }));
    fireEvent.click(screen.getByRole('button', { name: 'Load Task and Project choices' }));
    const checkbox = await screen.findByRole('checkbox', { name: /Synthetic task/ });
    fireEvent.click(checkbox);
    fireEvent.change(screen.getByLabelText('Objective'), { target: { value: 'Review synthetic task' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create review candidate' }));

    expect(await screen.findByText(/Ready for your review/)).toBeTruthy();
    const post = calls.find((item) => item.url.endsWith('/planning/candidates') && item.init?.method === 'POST');
    expect(JSON.parse(String(post?.init?.body))).toEqual({ objective: 'Review synthetic task', source_refs: [ref], calendar_window: null });
    expect(post?.init).toMatchObject({ credentials: 'same-origin', cache: 'no-store' });
    expect(sessionStorage.getItem(`secondbrain.planning.candidate:${sessionId}`)).toBe(candidateId);
  });

  it('restores only the current session locator and separates approval from synthetic execution', async () => {
    sessionStorage.setItem(`secondbrain.planning.candidate:${sessionId}`, candidateId);
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    let current = preview();
    let decisionAttempts = 0;
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input); calls.push({ url, init });
      if (url.endsWith(`/planning/candidates/${candidateId}/steps/1/decision`)) {
        decisionAttempts += 1;
        if (decisionAttempts === 1) throw new TypeError('synthetic connection lost after send');
        current = preview(2, 'approved');
        return Response.json({ event: 'planning.step-decision', version: 1, session_id: sessionId, candidate_id: candidateId,
          revision: 2, position: 1, decision: 'approved', execution_status: 'not_started' });
      }
      if (url.endsWith(`/planning/candidates/${candidateId}/steps/1/execute`)) {
        current = { ...preview(3, 'approved'), workflow_status: 'completed', steps: [{ ...preview(3, 'approved').steps[0]!, execution_status: 'simulated' }] };
        return Response.json({ event: 'planning.step-execution', version: 1, session_id: sessionId, candidate_id: candidateId,
          revision: 3, position: 1, execution_mode: 'synthetic', effect: 'none', status: 'simulated' });
      }
      if (url.endsWith(`/planning/candidates/${candidateId}/retrospective`)) return Response.json({ ...retrospective(), revision: current.revision, workflow_status: current.workflow_status });
      if (url.endsWith(`/planning/candidates/${candidateId}`)) return Response.json(current);
      throw new Error(`Unexpected request ${url}`);
    }));
    render(<PlanningPanel locale="en" sessionId={sessionId} />);
    expect(calls).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: 'Open planning' }));
    expect(await screen.findByText(/Ready for your review/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Approve this step' }));
    await waitFor(() => expect(calls.some((item) => item.url.endsWith('/steps/1/decision'))).toBe(true));
    expect(await screen.findByRole('alert')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Approve this step' }));
    await waitFor(() => expect(decisionAttempts).toBe(2));
    const decisionRequests = calls.filter((item) => item.url.endsWith('/steps/1/decision'));
    const decisionRequest = decisionRequests[0]!;
    expect(JSON.parse(String(decisionRequest.init?.body))).toEqual({ decision: 'approved', expected_revision: 1 });
    expect(decisionRequest.init?.headers).toMatchObject({ 'Idempotency-Key': expect.any(String) });
    expect(decisionRequests[1]?.init?.headers).toEqual(decisionRequest.init?.headers);
    expect(decisionRequests[1]?.init?.body).toBe(decisionRequest.init?.body);
    fireEvent.click(await screen.findByRole('button', { name: /Run synthetic check/ }));
    await waitFor(() => expect(calls.some((item) => item.url.endsWith('/steps/1/execute'))).toBe(true));
    const executeRequest = calls.find((item) => item.url.endsWith('/steps/1/execute'))!;
    expect(JSON.parse(String(executeRequest.init?.body))).toEqual({ expected_revision: 2 });
    expect(executeRequest.init?.headers).toMatchObject({ 'Idempotency-Key': expect.any(String) });
    expect(await screen.findByText(/completed · revision 3/)).toBeTruthy();
    expect(screen.getByText(/Core recorded the explicitly approved planning action/)).toBeTruthy();
  });

  it('submits only user-entered Task actions, requires approval, consumes the Core receipt and retries the same idempotent execution', async () => {
    sessionStorage.setItem(`secondbrain.planning.candidate:${sessionId}`, candidateId);
    const taskStep = { position: 1, kind: 'create_task', task: { title: 'Prepare synthetic review', due_date: '2026-10-30' },
      reason: 'user_submitted_task_action', priority: 'user_selected', depends_on: [], decision: 'pending', execution_status: 'not_started' };
    const candidate = (revision: number, decision: 'pending' | 'approved', execution_status: 'not_started' | 'completed') => ({
      event: 'planning.preview', version: 1, session_id: sessionId, candidate_id: candidateId, revision,
      expires_at: '2026-10-22T08:00:00Z', status: 'ready', workflow_status: execution_status === 'completed' ? 'completed' : 'active',
      objective: 'Create the task explicitly proposed by the user', steps: [{ ...taskStep, decision, execution_status }],
    });
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    let current = candidate(1, 'pending', 'not_started');
    let executionAttempts = 0;
    const taskId = 'd'.repeat(32);
    const taskVersion = 'e'.repeat(64);
    const receipt = { event: 'planning.step-execution', version: 1, session_id: sessionId, candidate_id: candidateId,
      revision: 3, position: 1, status: 'completed', execution_mode: 'core', effect: 'task_created', task_id: taskId, task_version: taskVersion };
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input); calls.push({ url, init });
      if (url.endsWith(`/planning/candidates/${candidateId}/steps/1/decision`)) {
        current = candidate(2, 'approved', 'not_started');
        return Response.json({ event: 'planning.step-decision', version: 1, session_id: sessionId, candidate_id: candidateId,
          revision: 2, position: 1, decision: 'approved', execution_status: 'not_started' });
      }
      if (url.endsWith(`/planning/candidates/${candidateId}/steps/1/execute`)) {
        executionAttempts += 1;
        if (executionAttempts === 1) {
          // Core committed the Task and planning revision; the response was lost in transit.
          current = candidate(3, 'approved', 'completed');
          throw new TypeError('synthetic connection lost after Core commit');
        }
        return Response.json(receipt);
      }
      if (url.endsWith(`/planning/candidates/${candidateId}/retrospective`)) return Response.json({ ...retrospective(), revision: current.revision, workflow_status: current.workflow_status,
        steps: [{ position: 1, source_state: 'not_applicable', decision: 'approved', execution_status: current.steps[0]!.execution_status }] });
      if (url.endsWith(`/planning/candidates/${candidateId}`)) return Response.json(current);
      if (url === '/api/tasks?status=all') return Response.json({ tasks: [{ id: taskId, title: 'Synthetic source', status: 'open', source_ref: ref }] });
      if (url === '/api/projects?limit=50&offset=0') return Response.json({ status: 'empty', items: [] });
      throw new Error(`Unexpected request ${url}`);
    }));

    render(<PlanningPanel locale="en" sessionId={sessionId} />);
    fireEvent.click(screen.getByRole('button', { name: 'Open planning' }));
    expect(await screen.findByText(/Prepare synthetic review/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Create this approved Task' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Approve this step' }));
    const createButton = await screen.findByRole('button', { name: 'Create this approved Task' });
    fireEvent.click(createButton);
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Create this approved Task' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Create this approved Task' }));
    expect(await screen.findByText(new RegExp(`Core created Task ${taskId}`))).toBeTruthy();
    expect(await screen.findByText(/approved · completed/)).toBeTruthy();

    const executions = calls.filter((item) => item.url.endsWith('/steps/1/execute'));
    expect(executions).toHaveLength(2);
    expect(JSON.parse(String(executions[0]?.init?.body))).toEqual({ expected_revision: 2 });
    expect(executions[1]?.init?.body).toBe(executions[0]?.init?.body);
    expect(executions[1]?.init?.headers).toEqual(executions[0]?.init?.headers);
    expect(executions[0]?.init?.headers).toMatchObject({ 'Idempotency-Key': expect.any(String) });
  });

  it('sends proposed Task actions only when explicitly entered', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input); calls.push({ url, init });
      if (url === '/api/tasks?status=all') return Response.json({ tasks: [{ id: taskId, title: 'Synthetic task', status: 'open', source_ref: ref }] });
      if (url === '/api/projects?limit=50&offset=0') return Response.json({ status: 'empty', items: [] });
      if (url.endsWith('/planning/candidates') && init?.method === 'POST') return Response.json({ ...preview(), event: 'planning.candidate' });
      if (url.endsWith(`/planning/candidates/${candidateId}/retrospective`)) return Response.json(retrospective());
      if (url.endsWith(`/planning/candidates/${candidateId}`)) return Response.json(preview());
      throw new Error(`Unexpected request ${url}`);
    }));
    render(<PlanningPanel locale="en" sessionId={sessionId} />);
    fireEvent.click(screen.getByRole('button', { name: 'Open planning' }));
    fireEvent.change(screen.getByLabelText('Objective'), { target: { value: 'Review source and create a task' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add Task proposal' }));
    fireEvent.change(screen.getByLabelText('Task 1 title'), { target: { value: 'Write a follow-up' } });
    fireEvent.change(screen.getByLabelText('Task 1 due date'), { target: { value: '2026-10-30' } });
    fireEvent.click(screen.getByRole('button', { name: 'Load Task and Project choices' }));
    fireEvent.click(await screen.findByRole('checkbox', { name: /Synthetic task/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Create review candidate' }));
    expect(await screen.findByText(/Ready for your review/)).toBeTruthy();
    const request = calls.find((item) => item.url.endsWith('/planning/candidates') && item.init?.method === 'POST');
    expect(JSON.parse(String(request?.init?.body))).toMatchObject({ proposed_tasks: [{ title: 'Write a follow-up', due_date: '2026-10-30' }] });
  });

  it('rejects a malformed Core Task receipt without presenting a creation success', async () => {
    sessionStorage.setItem(`secondbrain.planning.candidate:${sessionId}`, candidateId);
    const taskStep = { position: 1, kind: 'create_task', task: { title: 'Synthetic approved task', due_date: null },
      reason: 'user_submitted_task_action', priority: 'user_selected', depends_on: [], decision: 'approved', execution_status: 'not_started' };
    const current = { event: 'planning.preview', version: 1, session_id: sessionId, candidate_id: candidateId, revision: 2,
      expires_at: '2026-10-22T08:00:00Z', status: 'ready', workflow_status: 'active', objective: 'Explicit Task action', steps: [taskStep] };
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith(`/planning/candidates/${candidateId}/steps/1/execute`)) return Response.json({
        event: 'planning.step-execution', version: 1, session_id: sessionId, candidate_id: candidateId,
        revision: 3, position: 1, status: 'completed', execution_mode: 'core', effect: 'task_created',
        task_id: 'f'.repeat(32), task_version: 'invalid-version',
      });
      if (url.endsWith(`/planning/candidates/${candidateId}/retrospective`)) return Response.json(retrospective());
      if (url.endsWith(`/planning/candidates/${candidateId}`)) return Response.json(current);
      throw new Error(`Unexpected request ${url}`);
    }));
    render(<PlanningPanel locale="en" sessionId={sessionId} />);
    fireEvent.click(screen.getByRole('button', { name: 'Open planning' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Create this approved Task' }));
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.queryByText(/Core created Task/)).toBeNull();
    expect(screen.queryByText(/Core recorded the explicitly approved planning action/)).toBeNull();
  });

  it('does not restore a candidate locator from another chat session', async () => {
    sessionStorage.setItem(`secondbrain.planning.candidate:${sessionId}`, candidateId);
    const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
    render(<PlanningPanel locale="en" sessionId="session-synthetic-b" />);
    fireEvent.click(screen.getByRole('button', { name: 'Open planning' }));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Load Task and Project choices' })).toBeTruthy();
  });

  it('rejects objectives over the UTF-8 byte contract and calendar windows crossing a month before sending', async () => {
    const calls: string[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input); calls.push(url);
      if (url === '/api/tasks?status=all') return Response.json({ tasks: [{ id: taskId, title: 'Synthetic task', status: 'open', source_ref: ref }] });
      if (url === '/api/projects?limit=50&offset=0') return Response.json({ status: 'empty', items: [] });
      throw new Error(`Unexpected request ${url}`);
    }));
    render(<PlanningPanel locale="en" sessionId={sessionId} />);
    fireEvent.click(screen.getByRole('button', { name: 'Open planning' }));
    fireEvent.click(screen.getByRole('button', { name: 'Load Task and Project choices' }));
    fireEvent.click(await screen.findByRole('checkbox', { name: /Synthetic task/ }));
    fireEvent.change(screen.getByLabelText('Objective'), { target: { value: '中'.repeat(167) } });
    fireEvent.click(screen.getByRole('button', { name: 'Create review candidate' }));
    expect(await screen.findByText(/500 UTF-8 bytes/)).toBeTruthy();
    expect(calls.some((url) => url.endsWith('/planning/candidates'))).toBe(false);

    fireEvent.change(screen.getByLabelText('Objective'), { target: { value: 'Valid objective' } });
    fireEvent.click(screen.getByLabelText('Include a bounded Calendar window'));
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-03-31' } });
    fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-04-01' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create review candidate' }));
    expect(await screen.findByText(/Choose valid dates in one month/)).toBeTruthy();
    expect(calls.some((url) => url.endsWith('/planning/candidates'))).toBe(false);
  });
});
