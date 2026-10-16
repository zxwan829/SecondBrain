import { describe, expect, it } from 'vitest';
import { parseTerminalApproval } from './chat-approval';

const event = {
  event: 'approval.request', run_id: 'run-1', session_id: 'session-1', approval_id: 'req-1',
  tool: 'terminal', command: 'pwd', arguments: { command: 'pwd' }, command_sha256: 'a'.repeat(64),
  expires_at: Date.now() + 30_000, scope: 'Local Hermes terminal',
};

describe('terminal approval event binding', () => {
  it('accepts a current card only for the active Run and Session', () => {
    expect(parseTerminalApproval(event, 'run-1', 'session-1')?.command).toBe('pwd');
    expect(parseTerminalApproval(event, 'run-other', 'session-1')).toBeNull();
    expect(parseTerminalApproval(event, 'run-1', 'session-other')).toBeNull();
  });

  it('rejects malformed, expired, or digest-less requests', () => {
    expect(parseTerminalApproval({ ...event, expires_at: Date.now() - 1 }, 'run-1', 'session-1')).toBeNull();
    expect(parseTerminalApproval({ ...event, command_sha256: 'bad' }, 'run-1', 'session-1')).toBeNull();
    expect(parseTerminalApproval({ ...event, event: 'approval.responded' }, 'run-1', 'session-1')).toBeNull();
  });
});
