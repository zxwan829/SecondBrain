import React from 'react';
import type { KnowledgeCitationBundle } from './chat-knowledge-citations';

function statusLabel(bundle: KnowledgeCitationBundle, en: boolean): string {
  if (bundle.error_status) {
    if (bundle.error_status === 401) return en ? 'Sign in again to verify these references.' : '请重新登录后核验这些检索参考。';
    if (bundle.error_status === 403) return en ? 'You do not have permission to reopen these references.' : '当前账户无权重新核验这些检索参考。';
    if (bundle.error_status === 404) return en ? 'This run or its references are unavailable.' : '此运行或其检索参考已不可用。';
    if (bundle.error_status === 409) return en ? 'The reference binding changed; references are hidden.' : '引用绑定发生冲突，已隐藏相关内容。';
    if (bundle.error_status === 410) return en ? 'These references have expired.' : '这些检索参考已失效。';
    return en ? 'References could not be verified right now.' : '暂时无法核验检索参考。';
  }
  switch (bundle.status) {
    case 'available': return en
      ? 'Core rechecked these Knowledge versions. This does not establish that the answer relied on them.'
      : 'Core 已复核这些知识文档的当前版本；这不表示回答基于这些文档。';
    case 'none': return en ? 'No retrievable references were available for this run.' : '本轮没有可展示的检索参考。';
    case 'partial': return en ? 'Some references are stale or unavailable; only current metadata is shown.' : '部分检索参考已失效或不可用；这里只显示当前可核验的元数据。';
    case 'unavailable': return en ? 'References are unavailable or could not be reverified.' : '检索参考不可用或未能重新核验。';
  }
}

export function ChatKnowledgeCitations({ bundles, loading, persistenceIssue, locale }: {
  bundles: KnowledgeCitationBundle[]; loading: boolean; persistenceIssue: boolean; locale: 'zh-CN' | 'en';
}) {
  const en = locale === 'en';
  if (!loading && !persistenceIssue && bundles.length === 0) return null;
  return <section className="chat-knowledge-citations" aria-label={en ? 'Retrieved references' : '检索参考'}>
    <h3>{en ? 'Retrieved references' : '检索参考'}</h3>
    <p className="chat-knowledge-citations-note">
      {en
        ? 'This panel shows reference metadata returned by Core; it does not prove that an answer used a reference or that its claims are true.'
        : '此处只显示 Core 返回的检索参考元数据，不证明回答使用了这些参考，也不证明回答中的陈述为真。'}
    </p>
    {persistenceIssue && <p role="alert">{en
      ? 'This browser could not save the run locator; references from this run may not be recoverable after closing the tab.'
      : '浏览器无法保存本轮的 run 定位符；关闭标签页后可能无法恢复本轮检索参考。'}</p>}
    {loading && <p role="status">{en ? 'Rechecking references for this session…' : '正在重新核验本会话的检索参考…'}</p>}
    {bundles.map((bundle) => <article className="chat-knowledge-citation-run" key={`${bundle.session_id}:${bundle.run_id}`}>
      <p className="chat-knowledge-citation-status" role={bundle.error_status ? 'alert' : 'status'}>{statusLabel(bundle, en)}</p>
      {bundle.citations.length > 0 && <ul>
        {bundle.citations.map((citation) => <li key={citation.citation_id}>
          <strong>{citation.title}</strong>
          {citation.knowledge_status === 'version_verified'
            ? <><span>{en ? 'Knowledge version verified' : '知识文档版本已核验'}</span><span>{en ? 'Original source provenance verified' : '原始来源记录已核验'}</span></>
            : <span className="is-stale">{citation.knowledge_status === 'stale'
              ? (en ? 'Knowledge version changed; this reference is stale.' : '知识文档版本已变化；此检索参考已失效。')
              : (en ? 'This reference is unavailable and is not verified.' : '此检索参考不可用，当前未核验。')}</span>}
          {citation.knowledge_status === 'version_verified' && <small>{en ? 'Version SHA-256' : '版本 SHA-256'} · {citation.sha256.slice(0, 12)}…</small>}
        </li>)}
      </ul>}
    </article>)}
  </section>;
}
