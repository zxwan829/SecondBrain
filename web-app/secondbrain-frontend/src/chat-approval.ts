export type TerminalApprovalCard = {
  runId: string;
  sessionId: string;
  approvalId: string;
  tool: 'terminal' | 'process_manage' | 'execute_code';
  command: string;
  arguments: Record<string, unknown>;
  commandSha256: string;
  expiresAt: number;
  scope: string;
};

export function parseTerminalApproval(payload: Record<string, unknown>, runId: string, sessionId: string): TerminalApprovalCard | null {
  if (payload.event !== 'approval.request' || payload.run_id !== runId || payload.session_id !== sessionId) return null;
  const tool = payload.tool;
  const args = payload.arguments;
  const approvalId = payload.approval_id;
  const command = payload.command;
  const digest = payload.command_sha256;
  const expiresAt = payload.expires_at;
  const scope = payload.scope;
  if (!['terminal', 'process_manage', 'execute_code'].includes(String(tool))
      || !args || typeof args !== 'object' || Array.isArray(args)
      || typeof approvalId !== 'string' || !approvalId
      || typeof command !== 'string' || !command
      || typeof digest !== 'string' || !/^[a-f0-9]{64}$/.test(digest)
      || typeof expiresAt !== 'number' || expiresAt <= Date.now()
      || typeof scope !== 'string' || !scope) return null;
  return { runId, sessionId, approvalId, tool: tool as TerminalApprovalCard['tool'], command,
    arguments: args as Record<string, unknown>, commandSha256: digest, expiresAt, scope };
}
