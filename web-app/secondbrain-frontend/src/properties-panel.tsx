import React, { useState } from 'react';

export type MockProperties = {
  tags: string[];
  aliases: string[];
  type: string;
  status: string;
  created: string;
  updated: string;
  description: string;
  folderCollection: string;
  docMode: 'page' | 'edgeless';
  pageWidth: 'narrow' | 'standard' | 'wide';
  edgelessTheme: 'light' | 'dark';
  journal: string;
  source: string;
  sourceUrl: string;
  related: string[];
  backlinks: string;
  captureSource: string;
  workflowStage: string;
  promotedFrom: string;
  aiSummary: string;
  aiTags: string[];
  aiStatus: string;
  custom: Array<{ name: string; value: string }>;
};

export const DEFAULT_MOCK_PROPERTIES: MockProperties = {
  tags: [], aliases: [], type: 'Note', status: 'Draft', created: '', updated: '', description: '',
  folderCollection: 'Unfiled', docMode: 'page', pageWidth: 'wide', edgelessTheme: 'light',
  journal: '', source: '', sourceUrl: '', related: [], backlinks: 'Not connected', captureSource: '',
  workflowStage: 'Not connected', promotedFrom: '', aiSummary: '', aiTags: [], aiStatus: 'Not connected', custom: [],
};

const moreFields: Array<{ key: keyof MockProperties; label: string; kind?: 'textarea' | 'readonly' | 'select'; options?: string[] }> = [
  { key: 'aliases', label: '别名' },
  { key: 'created', label: '创建时间', kind: 'readonly' },
  { key: 'description', label: '描述', kind: 'textarea' },
  { key: 'pageWidth', label: '正文宽度', kind: 'select', options: ['narrow', 'standard', 'wide'] },
  { key: 'edgelessTheme', label: '画布主题', kind: 'select', options: ['light', 'dark'] },
  { key: 'journal', label: '日志' },
  { key: 'source', label: '来源' },
  { key: 'sourceUrl', label: '来源链接' },
  { key: 'related', label: '相关内容' },
  { key: 'backlinks', label: '反向链接', kind: 'readonly' },
  { key: 'captureSource', label: '捕获来源' },
  { key: 'workflowStage', label: '工作流阶段' },
  { key: 'promotedFrom', label: '提升来源' },
  { key: 'aiSummary', label: 'AI 摘要', kind: 'textarea' },
  { key: 'aiTags', label: 'AI 标签' },
  { key: 'aiStatus', label: 'AI 状态' },
];

function parseList(value: string) {
  return value.split(',').map(item => item.trim()).filter(Boolean);
}

function propertyOptionLabel(key: keyof MockProperties, option: string) {
  const labels: Partial<Record<keyof MockProperties, Record<string, string>>> = {
    pageWidth: { narrow: '窄', standard: '标准', wide: '宽' },
    edgelessTheme: { light: '浅色', dark: '深色' },
  };
  return labels[key]?.[option] ?? option;
}

function PropertyRow({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return <label className="sb-property-row"><span className="sb-property-label">{label}</span><span className="sb-property-value">{children}{hint && <small>{hint}</small>}</span></label>;
}

export function PropertiesPanel({
  values, onChange, onModeChange, title, onTitleChange, devMode, readOnlyKeys = [],
}: {
  values: MockProperties;
  onChange: (key: keyof MockProperties, value: unknown) => void;
  onModeChange: (mode: 'page' | 'edgeless') => void;
  title: string;
  onTitleChange: (value: string) => void;
  readOnlyKeys?: Array<keyof MockProperties>;
  devMode: boolean;
}) {
  const [showAdd, setShowAdd] = useState(false);
  const [customName, setCustomName] = useState('');
  const [customValue, setCustomValue] = useState('');
  const [showAddedProperty, setShowAddedProperty] = useState<string[]>([]);
  const morePropertyCount = moreFields.filter(field => !showAddedProperty.includes(field.key as string)).length + showAddedProperty.length + values.custom.length;
  const changeString = (key: keyof MockProperties) => (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => onChange(key, event.target.value);
  const isReadOnly = (key: keyof MockProperties) => readOnlyKeys.includes(key);
  const addCustom = (event: React.FormEvent) => {
    event.preventDefault();
    const name = customName.trim();
    if (!name || values.custom.some(item => item.name.toLowerCase() === name.toLowerCase())) return;
    onChange('custom', [...values.custom, { name, value: customValue }]);
    setCustomName(''); setCustomValue(''); setShowAdd(false);
  };

  return <section className="sb-properties" aria-label="文档属性">
    <details className="sb-properties-info">
      <summary aria-label="展开或折叠属性"><span className="properties-chevron" aria-hidden="true"></span><span>属性</span></summary>
    <PropertyRow label="标题"><input className="sb-property-input" aria-label="文档标题" value={title} onChange={event => onTitleChange(event.target.value)} /></PropertyRow>
    <div className="sb-property-grid">
      <PropertyRow label="标签"><input className="sb-property-input" aria-label="标签，逗号分隔" value={values.tags.join(', ')} placeholder="添加标签" readOnly={isReadOnly('tags')} onChange={event => onChange('tags', parseList(event.target.value))} /></PropertyRow>
      <PropertyRow label="文档模式"><span className="sb-segmented" role="group" aria-label="文档模式">
        <button type="button" aria-pressed={values.docMode === 'page'} onClick={() => onModeChange('page')}>页面</button>
        <button type="button" aria-pressed={values.docMode === 'edgeless'} onClick={() => onModeChange('edgeless')}>画布</button>
      </span></PropertyRow>
      <PropertyRow label="类型"><select className="sb-property-input" aria-label="类型" value={values.type} disabled={isReadOnly('type')} onChange={changeString('type')}><option value={values.type}>{values.type || '未设置'}</option></select></PropertyRow>
      <PropertyRow label="状态"><select className="sb-property-input" aria-label="状态" value={values.status} disabled={isReadOnly('status')} onChange={changeString('status')}><option value={values.status}>{values.status || '未设置'}</option>{!isReadOnly('status') && <><option value="Draft">草稿</option><option value="Active">进行中</option><option value="Archived">已归档</option></>}</select></PropertyRow>
      <PropertyRow label="文件夹 / 集合"><input className="sb-property-input" aria-label="文件夹或集合" value={values.folderCollection} onChange={changeString('folderCollection')} /></PropertyRow>
      <PropertyRow label="更新时间"><span className="sb-property-readonly">{values.updated || '尚未保存'}</span></PropertyRow>
    </div>
    <details className="sb-more-properties">
      <summary>更多属性 <span>{morePropertyCount}</span></summary>
      <div className="sb-more-grid">
        {moreFields.filter(field => !showAddedProperty.includes(field.key as string)).map(field => {
          const value = values[field.key];
          const locked = field.kind === 'readonly';
          const hint = ['journal', 'source', 'sourceUrl', 'related', 'captureSource', 'workflowStage', 'promotedFrom', 'aiSummary', 'aiTags', 'aiStatus'].includes(field.key as string)
            ? '保存在本页的 Yjs 与快照中；不会改写普通 Markdown 属性。' : undefined;
          return <PropertyRow key={field.key} label={field.label} hint={hint}>
            {locked || isReadOnly(field.key) ? <span className="sb-property-readonly">{String(value || 'Not set')}</span>
              : field.kind === 'textarea' ? <textarea className="sb-property-input" aria-label={field.label} value={String(value ?? '')} onChange={changeString(field.key)} rows={2}/>
                : field.kind === 'select' ? <select className="sb-property-input" aria-label={field.label} value={String(value)} onChange={changeString(field.key)}>{field.options?.map(option => <option key={option} value={option}>{propertyOptionLabel(field.key, option)}</option>)}</select>
                  : <input className="sb-property-input" aria-label={field.label} value={Array.isArray(value) ? value.join(', ') : String(value ?? '')} onChange={event => onChange(field.key, ['aliases', 'related', 'aiTags'].includes(field.key as string) ? parseList(event.target.value) : event.target.value)} />}
          </PropertyRow>;
        })}
        {showAddedProperty.map(key => {
          const field = moreFields.find(item => item.key === key);
          return field ? <PropertyRow key={key} label={field.label}><span className="sb-property-readonly">已固定到主要属性</span></PropertyRow> : null;
        })}
        {values.custom.map((item, index) => <PropertyRow key={`${item.name}-${index}`} label={item.name}>
          <input className="sb-property-input" aria-label={item.name} value={item.value} onChange={event => onChange('custom', values.custom.map((current, currentIndex) => currentIndex === index ? { ...current, value: event.target.value } : current))}/>
        </PropertyRow>)}
      </div>
      <div className="sb-property-actions">
        <button type="button" onClick={() => { setShowAdd(!showAdd); setShowAddedProperty([]); }}>＋ 添加属性</button>
      </div>
      {showAdd && <form className="sb-add-property" onSubmit={addCustom}>
        <input aria-label="新属性名称" placeholder="属性名称" value={customName} onChange={event => setCustomName(event.target.value)} />
        <input aria-label="新属性值" placeholder="属性值" value={customValue} onChange={event => setCustomValue(event.target.value)} />
        <button type="submit" disabled={!customName.trim()}>添加</button>
        <small>自定义属性保存在本页的 Yjs 与快照中。</small>
      </form>}
    </details>
    </details>
  </section>;
}
