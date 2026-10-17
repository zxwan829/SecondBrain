import { describe, expect, it } from 'vitest';
import { parseRunToolApproval, parseTerminalApproval } from './chat-approval';

const event = {
  event: 'approval.request', run_id: 'run-1', session_id: 'session-1', approval_id: 'req-1',
  tool: 'terminal', command: 'pwd', arguments: { command: 'pwd', workdir: '/tmp/synthetic' }, command_sha256: 'a'.repeat(64),
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

  it('requires displayed terminal command and workdir to match bound arguments', () => {
    expect(parseTerminalApproval({ ...event, command: 'id' }, 'run-1', 'session-1')).toBeNull();
    expect(parseTerminalApproval({ ...event, arguments: { command: 'pwd' } }, 'run-1', 'session-1')).toBeNull();
    expect(parseTerminalApproval({ ...event, arguments: { command: 'pwd', workdir: 'relative' } }, 'run-1', 'session-1')).toBeNull();
    expect(parseTerminalApproval(event, 'run-1', 'session-1')?.workdir).toBe('/tmp/synthetic');
  });
});

describe('file write approval event binding', () => {
  const fileEvent = { ...event, tool: 'write_file', command: 'write_file → /knowledge-assets/00-Inbox/synthetic.md',
    arguments: { path: '/knowledge-assets/00-Inbox/synthetic.md', content: 'synthetic' } };

  it('accepts a path-bound write only for the active Run and Session', () => {
    expect(parseRunToolApproval(fileEvent, 'run-1', 'session-1')?.tool).toBe('write_file');
    expect(parseRunToolApproval(fileEvent, 'run-other', 'session-1')).toBeNull();
    expect(parseRunToolApproval(fileEvent, 'run-1', 'session-other')).toBeNull();
  });

  it('rejects a mismatched or non-canonical target and preserves the compatibility parser', () => {
    expect(parseRunToolApproval({ ...fileEvent, command: 'write_file → /tmp/other' }, 'run-1', 'session-1')).toBeNull();
    expect(parseRunToolApproval({ ...fileEvent, arguments: { path: '/tmp/../private/file', content: 'x' } }, 'run-1', 'session-1')).toBeNull();
    expect(parseTerminalApproval(fileEvent, 'run-1', 'session-1')?.tool).toBe('write_file');
  });
});
