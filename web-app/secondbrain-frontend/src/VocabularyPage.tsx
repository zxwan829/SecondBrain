import React, { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import { vocabularyApi, type VocabularySnapshot } from './api/vocabulary';

type Locale = 'zh-CN' | 'en';

export function VocabularyPage({ locale }: { locale: Locale }) {
  const en = locale === 'en';
  const [snapshot, setSnapshot] = useState<VocabularySnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [typeName, setTypeName] = useState('');
  const [tagName, setTagName] = useState('');
  const [alias, setAlias] = useState('');
  const [tagTarget, setTagTarget] = useState('');
  const [typeConfirmed, setTypeConfirmed] = useState(false);
  const [tagConfirmed, setTagConfirmed] = useState(false);
  const [aliasConfirmed, setAliasConfirmed] = useState(false);
  const activeTags = useMemo(() => snapshot?.tags.filter((tag) => tag.enabled) ?? [], [snapshot]);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try { setSnapshot(await vocabularyApi.read()); }
    catch (cause) { setError(cause instanceof Error ? cause.message : (en ? 'Vocabulary could not be loaded.' : '词库读取失败。')); }
    finally { setLoading(false); }
  }, [en]);

  useEffect(() => { void load(); }, [load]);

  const mutate = async (operation: (current: VocabularySnapshot) => Promise<VocabularySnapshot>) => {
    if (!snapshot || busy) return false;
    setBusy(true); setError(''); setMessage('');
    try {
      setSnapshot(await operation(snapshot));
      setMessage(en ? 'Saved to Core vocabulary with an audit revision.' : '已保存至 Core 词库并记录审计版本。');
      return true;
    } catch (cause) {
      const status = (cause as Error & { status?: number }).status;
      if (status === 412) {
        await load();
        setError(en ? 'The vocabulary changed elsewhere. Reloaded the latest revision; review and retry.' : '词库已被其他操作更新，已重新加载最新版本；请检查后重试。');
      } else setError(cause instanceof Error ? cause.message : (en ? 'Vocabulary update failed.' : '词库更新失败。'));
      return false;
    } finally { setBusy(false); }
  };

  const addType = async (event: FormEvent) => {
    event.preventDefault();
    if (!typeConfirmed) return;
    if (await mutate((current) => vocabularyApi.addType(current, typeName))) { setTypeName(''); setTypeConfirmed(false); }
  };
  const addTag = async (event: FormEvent) => {
    event.preventDefault();
    if (!tagConfirmed) return;
    if (await mutate((current) => vocabularyApi.addTag(current, tagName))) { setTagName(''); setTagConfirmed(false); }
  };
  const addAlias = async (event: FormEvent) => {
    event.preventDefault();
    if (!aliasConfirmed || !tagTarget) return;
    if (await mutate((current) => vocabularyApi.addSynonym(current, alias, tagTarget))) { setAlias(''); setAliasConfirmed(false); }
  };
  const setEnabled = async (kind: 'type' | 'tag', id: string, name: string, enabled: boolean) => {
    const prompt = enabled
      ? (en ? `Enable ${name}?` : `确认重新启用“${name}”？`)
      : (en ? `Disable ${name}? Historical note references will remain.` : `确认停用“${name}”？历史笔记中的引用会保留。`);
    if (!window.confirm(prompt)) return;
    await mutate((current) => kind === 'type'
      ? vocabularyApi.setTypeEnabled(current, id, enabled)
      : vocabularyApi.setTagEnabled(current, id, enabled));
  };

  return <section className="vocabulary-page" aria-labelledby="vocabulary-title">
    <header className="workspace-header">
      <div className="workspace-heading"><p className="eyebrow">SECONDBRAIN <span>/</span> NOTES</p>
        <h1 id="vocabulary-title">{en ? 'Tags & Types' : '标签与类型'}</h1>
        <p className="workspace-subtitle">{en ? 'Core-owned vocabulary for future metadata suggestions.' : '由 Core 管理，供后续笔记元数据建议使用。'}</p>
      </div>
    </header>
    <p className="capture-processing-note">{en ? 'Source of truth: private Core state. This page never scans or edits Markdown/frontmatter. A future Vault inventory must be separately authorized and read-only.' : '权威来源：Core 私有状态。本页不扫描或改写 Markdown/frontmatter。未来 Vault 盘点须另行授权且仅只读。'}</p>
    {message && <p className="capture-processing-note" role="status">{message}</p>}
    {error && <p className="capture-alert" role="alert">{error}</p>}
    {loading || !snapshot ? <p role="status">{loading ? (en ? 'Loading…' : '正在加载…') : (en ? 'Vocabulary unavailable.' : '词库当前不可用。')}</p> : <>
      <p>{en ? `Revision ${snapshot.revision} · ${snapshot.types.length}/10 types` : `版本 ${snapshot.revision} · 类型 ${snapshot.types.length}/10`}</p>
      <div className="organizer-settings-grid">
        <section className="organizer-settings-card" aria-labelledby="vocabulary-types-title">
          <h2 id="vocabulary-types-title">{en ? 'Types' : '类型'}</h2>
          <p>{en ? 'One primary type per note. Initial five values follow the business specification.' : '每篇笔记最多一个主类型；初始五种来自业务规范。'}</p>
          <ul>{snapshot.types.map((type) => <li key={type.id}>
            <span>{type.name}{type.built_in ? (en ? ' · initial' : ' · 初始类型') : ''}{!type.enabled ? (en ? ' · disabled' : ' · 已停用') : ''}</span>
            <button type="button" disabled={busy} onClick={() => void setEnabled('type', type.id, type.name, !type.enabled)}>{type.enabled ? (en ? 'Disable' : '停用') : (en ? 'Enable' : '启用')}</button>
          </li>)}</ul>
          <form onSubmit={(event) => void addType(event)}>
            <label>{en ? 'Propose new type' : '新增类型'}<input value={typeName} onChange={(event) => { setTypeName(event.target.value); setTypeConfirmed(false); }} maxLength={40} required /></label>
            <label><input type="checkbox" checked={typeConfirmed} onChange={(event) => setTypeConfirmed(event.target.checked)} />{en ? 'I confirm adding this type to the Core vocabulary.' : '我确认将此类型加入 Core 词库。'}</label>
            <button type="submit" disabled={busy || !typeName.trim() || !typeConfirmed || snapshot.types.length >= 10}>{en ? 'Confirm and add type' : '确认新增类型'}</button>
          </form>
        </section>
        <section className="organizer-settings-card" aria-labelledby="vocabulary-tags-title">
          <h2 id="vocabulary-tags-title">{en ? 'Tags' : '标签'}</h2>
          <p>{en ? 'Disabled tags remain in the catalog for historical references; deletion and bulk replacement are not available.' : '停用标签保留在词库中供历史引用；本切片不提供删除或批量替换。'}</p>
          {snapshot.tags.length ? <ul>{snapshot.tags.map((tag) => <li key={tag.id}>
            <span>{tag.name}{!tag.enabled ? (en ? ' · disabled' : ' · 已停用') : ''}</span>
            <button type="button" disabled={busy} onClick={() => void setEnabled('tag', tag.id, tag.name, !tag.enabled)}>{tag.enabled ? (en ? 'Disable' : '停用') : (en ? 'Enable' : '启用')}</button>
          </li>)}</ul> : <p role="status">{en ? 'No tags are seeded. A real Vault inventory requires separate read-only authorization.' : '尚无已盘点标签；真实 Vault 只读盘点需另行授权。'}</p>}
          <form onSubmit={(event) => void addTag(event)}>
            <label>{en ? 'Propose new tag' : '新增标签'}<input value={tagName} onChange={(event) => { setTagName(event.target.value); setTagConfirmed(false); }} maxLength={40} required /></label>
            <label><input type="checkbox" checked={tagConfirmed} onChange={(event) => setTagConfirmed(event.target.checked)} />{en ? 'I confirm adding this tag to the Core vocabulary.' : '我确认将此标签加入 Core 词库。'}</label>
            <button type="submit" disabled={busy || !tagName.trim() || !tagConfirmed}>{en ? 'Confirm and add tag' : '确认新增标签'}</button>
          </form>
        </section>
        <section className="organizer-settings-card" aria-labelledby="vocabulary-synonyms-title">
          <h2 id="vocabulary-synonyms-title">{en ? 'Synonyms' : '同义词'}</h2>
          <p>{en ? 'Persistent aliases require explicit confirmation and target an active canonical tag.' : '持久同义词映射需明确确认，并指向已启用的规范标签。'}</p>
          <ul>{snapshot.synonyms.map((item) => <li key={item.id}>{item.alias} → {snapshot.tags.find((tag) => tag.id === item.tag_id)?.name ?? '—'}</li>)}</ul>
          {!activeTags.length ? <p>{en ? 'Add an approved tag before creating aliases.' : '请先新增并确认规范标签，再添加同义词。'}</p> : <form onSubmit={(event) => void addAlias(event)}>
            <label>{en ? 'Alias' : '同义词'}<input value={alias} onChange={(event) => { setAlias(event.target.value); setAliasConfirmed(false); }} maxLength={40} required /></label>
            <label>{en ? 'Canonical tag' : '规范标签'}<select value={tagTarget} onChange={(event) => { setTagTarget(event.target.value); setAliasConfirmed(false); }} required><option value="">{en ? 'Select a tag' : '请选择'}</option>{activeTags.map((tag) => <option key={tag.id} value={tag.id}>{tag.name}</option>)}</select></label>
            <label><input type="checkbox" checked={aliasConfirmed} onChange={(event) => setAliasConfirmed(event.target.checked)} />{en ? 'I confirm saving this permanent mapping.' : '我确认保存此持久映射。'}</label>
            <button type="submit" disabled={busy || !alias.trim() || !tagTarget || !aliasConfirmed}>{en ? 'Confirm mapping' : '确认映射'}</button>
          </form>}
        </section>
        <section className="organizer-settings-card" aria-labelledby="vocabulary-audit-title">
          <h2 id="vocabulary-audit-title">{en ? 'Recent audit' : '最近审计记录'}</h2>
          <ul>{snapshot.audit.slice(-10).reverse().map((event) => <li key={event.revision}>r{event.revision} · {event.operation} · {event.at}</li>)}</ul>
        </section>
      </div>
    </>}
  </section>;
}
