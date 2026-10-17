export type RunToolApprovalCard = {
  runId: string;
  sessionId: string;
  approvalId: string;
  tool: 'terminal' | 'process_manage' | 'execute_code' | 'write_file' | 'patch';
  command: string;
  workdir: string | null;
  arguments: Record<string, unknown>;
  commandSha256: string;
  expiresAt: number;
  scope: string;
};

export function parseRunToolApproval(payload: Record<string, unknown>, runId: string, sessionId: string): RunToolApprovalCard | null {
  if (payload.event !== 'approval.request' || payload.run_id !== runId || payload.session_id !== sessionId) return null;
  const tool = payload.tool;
  const args = payload.arguments;
  const approvalId = payload.approval_id;
  const command = payload.command;
  const digest = payload.command_sha256;
  const expiresAt = payload.expires_at;
  const scope = payload.scope;
  if (!['terminal', 'process_manage', 'execute_code', 'write_file', 'patch'].includes(String(tool))
      || !args || typeof args !== 'object' || Array.isArray(args)
      || typeof approvalId !== 'string' || !approvalId
      || typeof command !== 'string' || !command
      || typeof digest !== 'string' || !/^[a-f0-9]{64}$/.test(digest)
      || typeof expiresAt !== 'number' || expiresAt <= Date.now()
      || typeof scope !== 'string' || !scope) return null;
  const toolArgs = args as Record<string, unknown>;
  if (tool === 'terminal'
      && (typeof toolArgs.command !== 'string' || toolArgs.command !== command
        || typeof toolArgs.workdir !== 'string' || !toolArgs.workdir.startsWith('/'))) return null;
  if (tool === 'execute_code' && (typeof toolArgs.code !== 'string' || toolArgs.code !== command)) return null;
  if (tool === 'write_file' || tool === 'patch') {
    const path = toolArgs.path;
    if (typeof path !== 'string' || !path.startsWith('/') || path.includes('\0')
        || path.split('/').some((part) => part === '.' || part === '..')
        || command !== `${tool} → ${path}`) return null;
    if (tool === 'write_file' && typeof toolArgs.content !== 'string') return null;
    if (tool === 'patch' && (typeof toolArgs.old_string !== 'string' || typeof toolArgs.new_string !== 'string')) return null;
  }
  return { runId, sessionId, approvalId, tool: tool as RunToolApprovalCard['tool'], command,
    workdir: tool === 'terminal' ? toolArgs.workdir as string : null,
    arguments: toolArgs, commandSha256: digest, expiresAt, scope };
}

// Backwards-compatible export for callers that still use the terminal-specific name.
export const parseTerminalApproval = parseRunToolApproval;
