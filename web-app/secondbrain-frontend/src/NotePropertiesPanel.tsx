import React, { useState } from 'react';
import { notesApi, type Note } from './api/notes';
import { vocabularyApi } from './api/vocabulary';

export function NotePropertiesPanel({ note, onSaved }: { note: Note; onSaved: (note: Note) => void }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [types, setTypes] = useState<string[]>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [inactiveType, setInactiveType] = useState(false);
  const [inactiveTags, setInactiveTags] = useState<string[]>([]);
  const [selectedType, setSelectedType] = useState('');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);

  const show = async () => {
    if (open) { setOpen(false); return; }
    setOpen(true); setLoading(true); setError(''); setMessage('');
    try {
      const [properties, vocabulary] = await Promise.all([notesApi.readProperties(note), vocabularyApi.read()]);
      setSelectedType(properties.type);
      setSelectedTags(properties.tags);
      const activeTypes = vocabulary.types.filter((item) => item.enabled).map((item) => item.name);
      const activeTags = vocabulary.tags.filter((item) => item.enabled).map((item) => item.name);
      const oldTags = properties.tags.filter((tag) => !activeTags.includes(tag));
      setInactiveType(Boolean(properties.type && !activeTypes.includes(properties.type)));
      setInactiveTags(oldTags);
      setTypes(properties.type && !activeTypes.includes(properties.type) ? [...activeTypes, properties.type] : activeTypes);
      setTags([...activeTags, ...oldTags]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '笔记属性暂不支持编辑。');
    } finally { setLoading(false); }
  };

  const save = async () => {
    if (!selectedType || saving) return;
    setSaving(true); setError(''); setMessage('');
    try {
      const saved = await notesApi.saveProperties(note, selectedType, selectedTags);
      onSaved(saved);
      setMessage('类型与标签已保存；正文及其他属性保持不变。');
      setOpen(false);
    } catch (cause) {
      const status = (cause as Error & { status?: number }).status;
      setError(status === 412 ? '笔记已在其他位置修改。请关闭后重新载入，再编辑属性。' : cause instanceof Error ? cause.message : '属性保存失败；原文未被覆盖。');
    } finally { setSaving(false); }
  };

  return <section className="notes-properties">
    <button type="button" onClick={() => void show()} disabled={saving}>编辑类型与标签</button>
    {message && <p role="status">{message}</p>}
    {open && <div className="notes-properties-panel" aria-label="笔记类型与标签">
      {loading ? <p role="status">正在读取类型与标签…</p> : error && !types.length ? <p role="alert">{error}</p> : <>
        <label>类型<select value={selectedType} onChange={(event) => setSelectedType(event.target.value)}>
          <option value="">请选择</option>{types.map((value) => <option key={value} value={value}>{value}{inactiveType && value === selectedType ? '（已停用，保留或更改）' : ''}</option>)}
        </select></label>
        <fieldset><legend>标签</legend>
          {tags.length ? tags.map((value) => <label key={value}><input type="checkbox" checked={selectedTags.includes(value)} onChange={(event) => setSelectedTags((current) => event.target.checked ? [...current, value] : current.filter((item) => item !== value))} />{value}{inactiveTags.includes(value) ? '（已停用或未入库，可移除）' : ''}</label>) : <p>尚无已启用标签，请先在“标签与类型”管理中添加。</p>}
        </fieldset>
        {error && <p role="alert">{error}</p>}
        <p>保存只修改 Markdown 属性“类型”和 tags；正文和其他属性会原样保留。</p>
        <button type="button" onClick={() => void save()} disabled={saving || !selectedType}>{saving ? '保存中…' : '确认保存属性'}</button>
      </>}
      <button type="button" onClick={() => setOpen(false)} disabled={saving}>取消</button>
    </div>}
  </section>;
}
