import React, { useEffect, useRef, useState } from 'react';
import { promoteApi, PromoteApiError, type PromoteOperation, type PromotePreview } from './api/promote';
import { ReviewMarkdown } from './ReviewMarkdown';

type Locale = 'zh-CN' | 'en';
type Props = {
  locale: Locale;
  reviewPath: string;
  reviewSha256: string;
  targetFilename: string;
  title: string;
  promoteEnabled: boolean;
};

type Phase = 'idle' | 'previewing' | 'preview_ready' | 'unlocking' | 'authorized' | 'confirming' | 'pending' | 'checking' | 'complete' | 'error';

function failureText(status: number | null, locale: Locale): string {
  const en = locale === 'en';
  if (status === 401) return en ? 'App sign-in or the independent Promote unlock is no longer valid.' : 'App 登录或独立入库解锁已失效。';
  if (status === 403) return en ? 'The request failed the Host, Origin, or transport security check.' : '请求未通过 Host、Origin 或传输安全校验。';
  if (status === 409) return en ? 'The selected Review or target changed. Create a new preview.' : '所选 Review 或目标已变化，请重新生成预览。';
  if (status === 410) return en ? 'This preview expired. Create a new preview.' : '预览已过期，请重新生成。';
  if (status === 423) return en ? 'Promote is disabled. No Knowledge write was confirmed.' : '正式入库已关闭；没有确认任何 Knowledge 写入。';
  if (status === 429) return en ? 'Too many attempts. Wait before trying again.' : '操作过于频繁，请稍后重试。';
  if (status === 503) return en ? 'The operation needs recovery review. Do not repeat confirmation.' : '操作需要恢复核验，请勿重复确认。';
  if (status === 0 || status === null) return en ? 'The result could not be confirmed. Check operation status before taking another action.' : '暂时无法确认操作结果；请先查询操作状态，不要重复提交。';
  return en ? 'The Promote operation could not be completed safely.' : '无法安全完成正式入库操作。';
}

function operationLabel(operation: PromoteOperation | null, locale: Locale): string {
  if (!operation) return '';
  const en = locale === 'en';
  switch (operation.status) {
    case 'promoted': return en ? 'The exact preview was written to Knowledge.' : '已将精确预览版本写入 Knowledge。';
    case 'already_promoted': return en ? 'This exact operation was already completed.' : '此精确操作此前已完成。';
    case 'confirmed': return en ? 'Confirmed; execution has not yet been verified.' : '已确认；执行结果尚未核验。';
    case 'claimed': return en ? 'Claimed; execution has not yet been verified.' : '已取得执行 claim；尚未核验写入结果。';
    case 'promoting': return en ? 'Execution is in progress; this is not a success yet.' : '正在执行，尚不能视为成功。';
    case 'recovery_required': return en ? 'Recovery is required. Do not submit confirmation again.' : '需要恢复核验，请勿再次提交确认。';
    case 'failed': return en ? `Operation failed${operation.error_code ? ` (${operation.error_code})` : ''}.` : `操作失败${operation.error_code ? `（${operation.error_code}）` : ''}。`;
  }
}

function markdownChangeSummary(summary: PromotePreview['change_summary']): string[] {
  return Array.isArray(summary) ? summary : [summary];
}

export function PromotePreviewPanel({ locale, reviewPath, reviewSha256, targetFilename, title, promoteEnabled }: Props) {
  const en = locale === 'en';
  const [phase, setPhase] = useState<Phase>('idle');
  const [preview, setPreview] = useState<PromotePreview | null>(null);
  const [password, setPassword] = useState('');
  const [unlocked, setUnlocked] = useState(false);
  const [operation, setOperation] = useState<PromoteOperation | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [outcomeUnknown, setOutcomeUnknown] = useState(false);
  const [confirmedOnce, setConfirmedOnce] = useState(false);
  const [now, setNow] = useState(Date.now());
  const activeRequest = useRef<AbortController | null>(null);
  const requestSequence = useRef(0);
  const unlockedRef = useRef(false);
  const busy = ['previewing', 'unlocking', 'confirming', 'checking'].includes(phase);
  const expired = Boolean(preview?.expires_at && Date.parse(preview.expires_at) <= now);

  function beginRequest() {
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    const sequence = ++requestSequence.current;
    return { controller, sequence };
  }

  function isCurrent(sequence: number, controller: AbortController) {
    return sequence === requestSequence.current && !controller.signal.aborted;
  }

  useEffect(() => () => {
    requestSequence.current += 1;
    activeRequest.current?.abort();
    if (unlockedRef.current) {
      void promoteApi.lock(new AbortController().signal).catch(() => undefined);
      unlockedRef.current = false;
    }
  }, []);

  useEffect(() => {
    if (!preview?.expires_at) return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [preview?.expires_at]);

  async function preparePreview() {
    if (busy || unlocked || outcomeUnknown) return;
    const { controller, sequence } = beginRequest();
    setPhase('previewing');
    setPreview(null);
    setOperation(null);
    setErrorStatus(null);
    setOutcomeUnknown(false);
    setConfirmedOnce(false);
    try {
      const result = await promoteApi.preview({ review_path: reviewPath, review_sha256: reviewSha256, target_filename: targetFilename }, controller.signal);
      if (!isCurrent(sequence, controller)) return;
      setPreview(result);
      setPhase('preview_ready');
    } catch (error) {
      if (!isCurrent(sequence, controller)) return;
      setErrorStatus(error instanceof PromoteApiError ? error.status : null);
      setPhase('error');
    }
  }

  async function unlock() {
    if (!preview || !promoteEnabled || busy || !password) return;
    const submittedPassword = password;
    setPassword('');
    const { controller, sequence } = beginRequest();
    setPhase('unlocking');
    setErrorStatus(null);
    try {
      await promoteApi.unlock(submittedPassword, controller.signal);
      if (!isCurrent(sequence, controller)) return;
      unlockedRef.current = true;
      setUnlocked(true);
      setPhase('authorized');
    } catch (error) {
      if (!isCurrent(sequence, controller)) return;
      setErrorStatus(error instanceof PromoteApiError ? error.status : null);
      setPhase('error');
    }
  }

  async function lock() {
    if (!unlocked || busy) return;
    const { controller, sequence } = beginRequest();
    setPhase('checking');
    setErrorStatus(null);
    try {
      await promoteApi.lock(controller.signal);
      if (!isCurrent(sequence, controller)) return;
      unlockedRef.current = false;
      setUnlocked(false);
      setPreview(null);
      setOperation(null);
      setConfirmedOnce(false);
      setPhase('idle');
    } catch (error) {
      if (!isCurrent(sequence, controller)) return;
      setErrorStatus(error instanceof PromoteApiError ? error.status : null);
      setPhase('error');
    }
  }

  async function readOperation(nextPhase: 'checking' | 'pending' = 'checking') {
    if (!preview || busy) return;
    const { controller, sequence } = beginRequest();
    setPhase(nextPhase);
    setErrorStatus(null);
    try {
      const result = await promoteApi.operation(preview.request_id, controller.signal);
      if (!isCurrent(sequence, controller)) return;
      setOperation(result);
      setOutcomeUnknown(false);
      if (result.status === 'promoted' || result.status === 'already_promoted') setPhase('complete');
      else if (result.status === 'recovery_required' || result.status === 'failed') setPhase('error');
      else setPhase('pending');
    } catch (error) {
      if (!isCurrent(sequence, controller)) return;
      setErrorStatus(error instanceof PromoteApiError ? error.status : null);
      setOutcomeUnknown(true);
      setPhase('pending');
    }
  }

  async function confirm() {
    if (!preview || !unlocked || !promoteEnabled || busy || outcomeUnknown || confirmedOnce || expired) return;
    const { controller, sequence } = beginRequest();
    setConfirmedOnce(true);
    setPhase('confirming');
    setErrorStatus(null);
    setOperation(null);
    try {
      await promoteApi.confirm(preview.preview_id, preview.request_id, controller.signal);
      if (!isCurrent(sequence, controller)) return;
      setOutcomeUnknown(true);
      setPhase('pending');
      await readOperationAfterConfirm(sequence, controller);
    } catch (error) {
      if (!isCurrent(sequence, controller)) return;
      const status = error instanceof PromoteApiError ? error.status : null;
      setErrorStatus(status);
      if ([401, 403, 409, 410, 423, 429].includes(status ?? -1)) {
        if (unlockedRef.current) void promoteApi.lock(new AbortController().signal).catch(() => undefined);
        setPreview(null);
        setUnlocked(false);
        unlockedRef.current = false;
        setOutcomeUnknown(false);
        setConfirmedOnce(false);
        setPhase('error');
      } else {
        setOutcomeUnknown(true);
        setPhase('pending');
      }
    }
  }

  async function readOperationAfterConfirm(sequence: number, controller: AbortController) {
    try {
      const result = await promoteApi.operation(preview!.request_id, controller.signal);
      if (!isCurrent(sequence, controller)) return;
      setOperation(result);
      setOutcomeUnknown(false);
      if (result.status === 'promoted' || result.status === 'already_promoted') setPhase('complete');
      else if (result.status === 'recovery_required' || result.status === 'failed') setPhase('error');
      else setPhase('pending');
    } catch (error) {
      if (!isCurrent(sequence, controller)) return;
      setErrorStatus(error instanceof PromoteApiError ? error.status : null);
      setOutcomeUnknown(true);
      setPhase('pending');
    }
  }

  const canConfirm = Boolean(preview && unlocked && promoteEnabled && !busy && !outcomeUnknown && !confirmedOnce && !expired);
  const operationTerminal = operation && ['promoted', 'already_promoted', 'recovery_required', 'failed'].includes(operation.status);
  const canLock = !busy && !outcomeUnknown && (!operation || operationTerminal);
  const phaseLabel = phase === 'complete'
    ? (en ? 'Operation complete' : '操作已完成')
    : phase === 'pending' || (operation && !['promoted', 'already_promoted'].includes(operation.status))
      ? (en ? 'Operation status' : '操作状态') : '';

  return <section className="promote-preview-panel" aria-labelledby="promote-preview-title">
    <header className="promote-preview-heading">
      <div>
        <p className="eyebrow">SECONDBRAIN / CONTROLLED PROMOTE</p>
        <h3 id="promote-preview-title">{en ? 'Formal Knowledge entry' : '正式知识入库'}</h3>
        <p>{en ? 'Review the exact server-generated output before a separate unlock and a second confirmation.' : '先核对服务端生成的完整结果，再独立解锁并进行第二次明确确认。'}</p>
      </div>
      {unlocked && <button type="button" className="promote-secondary" onClick={() => void lock()} disabled={!canLock}>{en ? 'Lock Promote' : '锁定入库授权'}</button>}
    </header>

    {!promoteEnabled && <p className="promote-disabled-notice" role="status">{en ? 'Promote is disabled for this App. Previewing does not write; unlock and confirmation are unavailable.' : '当前 App 已关闭正式入库。预览不会写入，解锁与确认不可用。'}</p>}
    <p className="promote-selected-source">{en ? 'Selected Review' : '所选 Review'}: <strong>{title}</strong> · {reviewPath}</p>

    {(!preview || phase === 'error' && !preview) && <button type="button" className="promote-primary" onClick={() => void preparePreview()} disabled={busy || unlocked || outcomeUnknown}>
      {phase === 'previewing' ? (en ? 'Preparing preview…' : '正在生成预览…') : (en ? 'Prepare exact Promote preview' : '准备正式入库预览')}
    </button>}

    {preview && <div className="promote-preview-content">
      <dl className="promote-preview-facts">
        <dt>{en ? 'Target' : '目标'}</dt><dd>{preview.target_filename}</dd>
        <dt>{en ? 'Target precondition' : '目标前置条件'}</dt><dd><pre>{JSON.stringify(preview.target_precondition, null, 2)}</pre></dd>
        <dt>{en ? 'Source SHA-256' : '来源 SHA-256'}</dt><dd><code>{preview.source_sha256}</code></dd>
        <dt>{en ? 'Output SHA-256' : '最终输出 SHA-256'}</dt><dd><code>{preview.output_sha256}</code></dd>
        {preview.expires_at && <><dt>{en ? 'Preview expires' : '预览有效至'}</dt><dd>{preview.expires_at}</dd></>}
      </dl>
      <div className="promote-change-summary"><h4>{en ? 'Server-reported changes' : '服务端变更说明'}</h4><ul>{markdownChangeSummary(preview.change_summary).map((line, index) => <li key={index}>{line}</li>)}</ul></div>
      <div className="promote-markdown-grid">
        <section><h4>{en ? 'Exact source Markdown' : '精确来源 Markdown'}</h4><ReviewMarkdown source={preview.source_markdown} /></section>
        <section><h4>{en ? 'Exact projected Markdown' : '精确拟入库 Markdown'}</h4><ReviewMarkdown source={preview.projected_markdown} /></section>
      </div>

      {preview && !unlocked && promoteEnabled && <form className="promote-unlock-form" onSubmit={(event) => { event.preventDefault(); void unlock(); }}>
        <label htmlFor="promote-independent-password">{en ? 'Independent Promote password' : '独立正式入库口令'}</label>
        <input id="promote-independent-password" type="password" autoComplete="off" value={password}
          onChange={(event) => setPassword(event.target.value)} disabled={busy} />
        <small>{en ? 'This is separate from App sign-in. It is not saved in browser storage.' : '此口令独立于 App 登录，不会保存到浏览器存储。'}</small>
        <button type="submit" className="promote-primary" disabled={busy || !password || expired}>{phase === 'unlocking' ? (en ? 'Unlocking…' : '正在解锁…') : (en ? 'Unlock Promote' : '独立解锁')}</button>
      </form>}

      {unlocked && <div className="promote-confirm-box">
        <p>{en ? 'Read the complete projected Markdown and target above. The next action confirms only this exact preview.' : '请先完整审阅上方拟入库 Markdown 和目标。下一步只确认此精确预览版本。'}</p>
        <button type="button" className="promote-primary" onClick={() => void confirm()} disabled={!canConfirm}>
          {phase === 'confirming' ? (en ? 'Confirming…' : '正在确认…') : (en ? 'Confirm writing this exact version to Knowledge' : '确认将此版本写入 Knowledge')}
        </button>
      </div>}

      {(phase === 'pending' || outcomeUnknown || operation) && <section className="promote-operation-status" aria-labelledby="promote-operation-title">
        <h4 id="promote-operation-title">{phaseLabel || (en ? 'Operation status' : '操作状态')}</h4>
        {outcomeUnknown && <p role="alert">{en ? 'The confirmation result is unknown. Do not submit it again; query the server operation.' : '确认结果未知。请勿重复提交；改为查询服务端操作状态。'}</p>}
        {operation && <p role={['failed', 'recovery_required'].includes(operation.status) ? 'alert' : 'status'}>{operationLabel(operation, locale)}</p>}
        {operation?.output_sha256 && <p><span>{en ? 'Recorded output SHA-256' : '记录的输出 SHA-256'}：</span> <code>{operation.output_sha256}</code></p>}
        {(outcomeUnknown || (operation && !['promoted', 'already_promoted'].includes(operation.status))) && <button type="button" className="promote-secondary" onClick={() => void readOperation()} disabled={busy}>{phase === 'checking' ? (en ? 'Checking…' : '正在查询…') : (en ? 'Check operation status' : '查询操作状态')}</button>}
        {phase === 'complete' && <p>{en ? 'You may search Knowledge manually to verify the result.' : '你可以自行进入 Knowledge 检索核对结果。'}</p>}
      </section>}
    </div>}

    {errorStatus !== null && <p className="promote-error" role="alert">{failureText(errorStatus, locale)}</p>}
    {expired && <p className="promote-error" role="alert">{en ? 'This preview has expired. Do not confirm it.' : '预览已过期，不能确认。'}</p>}
    {preview && !unlocked && <button type="button" className="promote-secondary" onClick={() => void preparePreview()} disabled={busy || outcomeUnknown || unlocked}>{en ? 'Create a new preview' : '重新生成预览'}</button>}
  </section>;
}
