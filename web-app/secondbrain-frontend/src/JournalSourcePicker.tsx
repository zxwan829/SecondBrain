import React, { useEffect, useRef, useState } from 'react';
import { journalSourceOptionsApi, JournalSourceOptionsError, type JournalSourceOption, type JournalSourceOptions } from './api/journal-source-options';

type Locale = 'zh-CN' | 'en';
type PickerState = 'idle' | 'loading' | 'real' | 'empty' | 'unavailable' | 'unauthorized' | 'invalid-request';

function shanghaiDate(now = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(now);
  const part = (type: string) => parts.find((item) => item.type === type)?.value ?? '';
  return `${part('year')}-${part('month')}-${part('day')}`;
}

const copy = {
  'zh-CN': {
    title: '选择日记来源',
    description: '仅在你点击加载后读取当天的来源元数据；不读取日记正文，也不会生成或保存简报。',
    load: '加载 Journal 来源',
    retry: '重新加载',
    loading: '正在读取 Journal 来源…',
    empty: '当天没有可选择的 Journal 来源。',
    unavailable: 'Journal 来源暂不可用。未显示部分结果，请稍后重试。',
    unauthorized: '当前账户无权读取 Journal 来源。',
    invalid: '来源选择请求无效；没有读取或保存来源。',
    checked: '来源检查时间',
    row: (index: number, id: string) => `Journal 来源 ${index + 1} · ${id.slice(-8)}`,
    selected: (count: number) => `已选择 ${count} 条来源。选择仅保留在当前页面，不会生成或修改简报。`,
    noneSelected: '尚未选择来源。',
  },
  en: {
    title: 'Choose Journal sources',
    description: 'Journal source metadata is read only after you request it. Entry content is not read, and no brief is created or saved.',
    load: 'Load Journal sources',
    retry: 'Reload',
    loading: 'Loading Journal sources…',
    empty: 'There are no selectable Journal sources for this date.',
    unavailable: 'Journal sources are unavailable. No partial results are shown; try again later.',
    unauthorized: 'This account cannot read Journal sources.',
    invalid: 'The source selection request was invalid; no source was read or saved.',
    checked: 'Sources checked at',
    row: (index: number, id: string) => `Journal source ${index + 1} · ${id.slice(-8)}`,
    selected: (count: number) => `${count} source(s) selected. Selection remains on this page; no brief is created or changed.`,
    noneSelected: 'No sources selected.',
  },
} as const;

export function JournalSourcePicker({ locale, onSelectionChange }: {
  locale: Locale;
  onSelectionChange?: (items: JournalSourceOption[], sourceDate: string) => void;
}) {
  const words = copy[locale];
  const [state, setState] = useState<PickerState>('idle');
  const [result, setResult] = useState<JournalSourceOptions | null>(null);
  const [loadedDate, setLoadedDate] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const requestRef = useRef<AbortController | null>(null);
  const generationRef = useRef(0);

  useEffect(() => () => {
    generationRef.current += 1;
    requestRef.current?.abort();
  }, []);

  const load = async () => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    const generation = ++generationRef.current;
    // Recompute at click time so an open page crossing Shanghai midnight never
    // requests a stale date captured during initial render.
    const date = shanghaiDate();
    setState('loading');
    setResult(null);
    setSelected(new Set());
    setLoadedDate(date);
    onSelectionChange?.([], date);
    try {
      const value = await journalSourceOptionsApi.list(date, controller.signal);
      if (controller.signal.aborted || generationRef.current !== generation) return;
      setResult(value);
      setState(value.status);
    } catch (error) {
      if (controller.signal.aborted || generationRef.current !== generation) return;
      setState(error instanceof JournalSourceOptionsError ? error.reason : 'unavailable');
    }
  };

  const toggle = (id: string, checked: boolean) => {
    const next = new Set(selected);
    if (checked) next.add(id);
    else next.delete(id);
    setSelected(next);
    onSelectionChange?.(result?.items.filter((item) => next.has(item.id)) ?? [], loadedDate ?? '');
  };

  return <section className="journal-source-picker" aria-labelledby="journal-source-picker-title">
    <div className="journal-source-picker-heading">
      <div>
        <h2 id="journal-source-picker-title">{words.title}</h2>
        <p>{words.description}</p>
      </div>
      <button type="button" className="v1-page-retry" onClick={() => void load()} disabled={state === 'loading'}>
        {state === 'idle' ? words.load : words.retry}
      </button>
    </div>
    {state === 'loading' && <p role="status">{words.loading}</p>}
    {state === 'empty' && <p role="status">{words.empty}</p>}
    {state === 'unavailable' && <p role="alert">{words.unavailable}</p>}
    {state === 'unauthorized' && <p role="alert">{words.unauthorized}</p>}
    {state === 'invalid-request' && <p role="alert">{words.invalid}</p>}
    {result?.status === 'real' && loadedDate && <>
      <fieldset className="journal-source-picker-list">
        <legend>{loadedDate} · {result.items.length}</legend>
        {result.items.map((item, index) => <label className="journal-source-option" key={item.id}>
          <input type="checkbox" checked={selected.has(item.id)} onChange={(event) => toggle(item.id, event.currentTarget.checked)} />
          <span>{words.row(index, item.id)}</span>
          <code title={item.version}>{item.version.slice(0, 8)}</code>
        </label>)}
      </fieldset>
      <p className="journal-source-picker-selection" role="status">
        {selected.size ? words.selected(selected.size) : words.noneSelected}
      </p>
      <p className="journal-source-picker-freshness">{words.checked}: <time>{result.freshness.checked_at}</time></p>
    </>}
  </section>;
}
