import React from 'react';
import type { ContextPreview, ContextPreviewItem, ContextStatus } from './chat-context-preview';

function stateLabel(value: string, en: boolean): string {
  const known: Record<string, [string, string]> = {
    active: ['有效', 'Active'], expired: ['已过期', 'Expired'], revoked: ['已撤权', 'Revoked'],
    stale: ['版本已变化', 'Version changed'], unavailable: ['不可用', 'Unavailable'],
    user_stated: ['用户陈述', 'User stated'], user_confirmed: ['用户确认', 'User confirmed'],
    inferred: ['推断（不可作为事实）', 'Inferred (not a fact)'], verified: ['已核验', 'Verified'],
  };
  return known[value]?.[en ? 1 : 0] ?? value;
}

function statusLabel(status: ContextStatus, en: boolean): string {
  const labels: Record<ContextStatus, [string, string]> = {
    available: ['找到可展示的来源元数据', 'Source metadata is available'],
    none: ['没有匹配的来源', 'No matching sources'],
    partial: ['部分来源受限或不完整', 'Some sources are limited or incomplete'],
    unavailable: ['来源暂不可用', 'Sources are unavailable'],
  };
  return labels[status][en ? 1 : 0];
}

function Item({ item, en }: { item: ContextPreviewItem; en: boolean }) {
  return <li>
    <strong>{item.source_kind === 'personal_memory' ? (en ? 'Personal memory' : '个人记忆') : 'Knowledge'}</strong>
    <dl>
      <dt>{en ? 'Opaque source ID' : '来源标识'}</dt><dd>{item.source_id}</dd>
      <dt>{en ? 'Version' : '版本'}</dt><dd>{item.source_version}</dd>
      <dt>SHA-256</dt><dd>{item.sha256}</dd>
      <dt>{en ? 'Source time' : '来源时间'}</dt><dd><time dateTime={item.source_timestamp}>{item.source_timestamp}</time></dd>
      <dt>{en ? 'Fact type' : '事实类型'}</dt><dd>{item.fact_kind ?? (en ? 'Not provided' : '未提供')}</dd>
      <dt>{en ? 'Verification' : '核验标记'}</dt><dd>{stateLabel(item.verification_status, en)}</dd>
      <dt>{en ? 'State' : '状态'}</dt><dd>{stateLabel(item.state, en)}</dd>
      {item.expires_at && <><dt>{en ? 'Expires' : '过期时间'}</dt><dd><time dateTime={item.expires_at}>{item.expires_at}</time></dd></>}
    </dl>
  </li>;
}

export function ChatContextPreview({ preview, loading, error, onRefresh, disabled, locale }: {
  preview: ContextPreview | null; loading: boolean; error: string; onRefresh: () => void;
  disabled: boolean; locale: 'zh-CN' | 'en';
}) {
  const en = locale === 'en';
  return <section className="chat-context-preview" aria-label={en ? 'Context preview' : '上下文预览'}>
    <div className="chat-context-preview-heading"><h3>{en ? 'Context preview' : '上下文预览'}</h3>
      <button type="button" onClick={onRefresh} disabled={disabled || loading}>{loading ? (en ? 'Checking…' : '正在核验…') : (preview || error ? (en ? 'Refresh preview' : '刷新预览') : (en ? 'Preview available context' : '检索可用上下文'))}</button></div>
    <p className="chat-context-preview-note">{en
      ? 'Core returned source metadata only. No source text is shown or sent to Hermes; this does not mean an answer used these sources.'
      : 'Core 仅返回来源元数据。此处不展示正文，也不会把这些信息发送给 Hermes；预览不表示回答使用了这些来源。'}</p>
    {loading && <p role="status">{en ? 'Checking this session’s authorized sources…' : '正在核验本会话获准的来源…'}</p>}
    {error && <p role="alert">{error}</p>}
    {preview && <>
      <p role="status">{statusLabel(preview.status, en)} · {en ? 'Evaluated' : '核验时间'}: {preview.evaluated_at}</p>
      <p>{en ? 'Personal memory' : '个人记忆'}: {statusLabel(preview.source_status.personal_memory, en)} · Knowledge: {statusLabel(preview.source_status.knowledge, en)}</p>
      {preview.items.length > 0 && <ul>{preview.items.map((item) => <Item key={`${item.source_kind}:${item.source_id}:${item.source_version}`} item={item} en={en} />)}</ul>}
    </>}
  </section>;
}

export function ChatNaturalCandidates({ preview, loading, error, locale }: {
  preview: ContextPreview | null; loading: boolean; error: string; locale: 'zh-CN' | 'en';
}) {
  const en = locale === 'en';
  if (!preview && !loading && !error) return null;
  return <section className="chat-context-preview" aria-label={en ? 'Possible related sources' : '可能相关的来源'}>
    <div className="chat-context-preview-heading"><h3>{en ? 'Possible related sources' : '可能相关的来源'}</h3></div>
    <p className="chat-context-preview-note">{en
      ? 'Core checked authorized sources for this message. These metadata were not added to Hermes input and do not mean the response used or verified them.'
      : 'Core 为这条消息检查了获准来源。这里的信息没有加入 Hermes 输入，也不表示回答使用或核验了这些来源。'}</p>
    {loading && <p role="status">{en ? 'Checking relevant sources…' : '正在检查可能相关的来源…'}</p>}
    {error && <p role="status">{error}</p>}
    {preview && <>
      <p role="status">{statusLabel(preview.status, en)} · {en ? 'Checked' : '检查时间'}: {preview.evaluated_at}</p>
      <p>{en ? 'Personal memory' : '个人记忆'}: {statusLabel(preview.source_status.personal_memory, en)} · Knowledge: {statusLabel(preview.source_status.knowledge, en)}</p>
      {preview.items.length > 0 && <ul>{preview.items.map((item) => <Item key={`${item.source_kind}:${item.source_id}:${item.source_version}`} item={item} en={en} />)}</ul>}
    </>}
  </section>;
}
