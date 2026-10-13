import { useEffect, useState } from 'react';

type Event = { name: string; at: string; detail?: string };
export type Trace = {
  initCallCount: number;
  initSuccessCount: number;
  cleanupCallCount: number;
  lastCleanupReason: string;
  activeRoute: string;
  immersiveActive: boolean;
  overrideStyleInstalled: boolean;
  headerMatched: boolean;
  spacerMatched: boolean;
  headerStyle: string;
  spacerStyle: string;
  secondBrainHeaderTop: number | null;
  events: Event[];
  copyText: string;
  debug: boolean;
};

declare global {
  interface Window { __SB_IMMERSIVE_TRACE__?: Trace }
}

const ROUTES = new Set(['/secondbrain-fe-test', '/secondbrain']);
const STYLE_ID = 'secondbrain-host-immersive';
const initialTrace: Trace = {
  initCallCount: 0,
  initSuccessCount: 0,
  cleanupCallCount: 0,
  lastCleanupReason: '',
  activeRoute: '',
  immersiveActive: false,
  overrideStyleInstalled: false,
  headerMatched: false,
  spacerMatched: false,
  headerStyle: 'unmatched',
  spacerStyle: 'unmatched',
  secondBrainHeaderTop: null,
  events: [],
  copyText: '',
  debug: false,
};

export type HostElements = {
  banner: HTMLElement | null;
  mobileHeaders: HTMLElement[];
  spacers: HTMLElement[];
  sidebar: HTMLElement | null;
  contentWrapper: HTMLElement | null;
};

/** Resolve only host chrome surrounding the mounted plugin. The header match is
 * anchored to the real Hermes plugin-title heading; plugin-owned headers are
 * excluded. Tailwind signatures are used only for the separately observed
 * mobile fixed header/spacer pair. */
export function resolveHostChrome(root: ParentNode): HostElements {
  const plugin = root.querySelector('.sb-app');
  const headings = Array.from(root.querySelectorAll('h1'));
  const hostTitle = headings.find((heading) => heading.textContent?.trim() === 'SecondBrain FE Test');
  const headers = Array.from(root.querySelectorAll('header')) as HTMLElement[];
  const banner = (hostTitle?.closest('header[role="banner"]') as HTMLElement | null)
    ?? headers.find((header) => header.getAttribute('role') === 'banner' && (!plugin || !plugin.contains(header)))
    ?? null;
  const outsidePlugin = (element: Element) => !plugin || !plugin.contains(element);
  const mobileHeaders = headers.filter((header) => {
    const classes = header.classList;
    return outsidePlugin(header) && classes.contains('fixed') && classes.contains('top-0') && classes.contains('lg:hidden');
  });
  const spacers = (Array.from(root.querySelectorAll('[aria-hidden="true"]')) as HTMLElement[]).filter((element) =>
    outsidePlugin(element) && element.classList.contains('h-14') && element.classList.contains('lg:hidden'),
  );

  let contentWrapper: HTMLElement | null = null;
  let ancestor = plugin?.parentElement ?? null;
  while (ancestor && ancestor !== root) {
    const classes = ancestor.className;
    if (typeof classes === 'string' && classes.includes('relative') && /(?:^|\s)(?:pt-|sm:pt-|lg:pt-)/.test(classes)) {
      contentWrapper = ancestor as HTMLElement;
      break;
    }
    ancestor = ancestor.parentElement;
  }

  return {
    banner,
    mobileHeaders,
    spacers,
    sidebar: root.querySelector('#app-sidebar') as HTMLElement | null,
    contentWrapper,
  };
}

const routeIsActive = (pathname: string) => ROUTES.has(pathname);
const restoreAttribute = (element: Element, name: string, original: string | null) => {
  if (original === null) element.removeAttribute(name);
  else element.setAttribute(name, original);
};

export function createImmersiveController(doc: Document, win: Window) {
  let active = false;
  let observer: MutationObserver | null = null;
  let originalBodyValue: string | null = null;
  let styleElement: HTMLStyleElement | null = null;
  const originals = new Map<Element, Map<string, string | null>>();

  const trace = () => win.__SB_IMMERSIVE_TRACE__ ?? { ...initialTrace, events: [] };
  const publish = (name: string, patch: Partial<Trace> = {}) => {
    const current = trace();
    const events = [...current.events, { name, at: new Date().toISOString() }].slice(-30);
    const next = { ...current, ...patch, activeRoute: win.location.pathname, events };
    const { copyText: _previousCopyText, ...serializable } = next;
    next.copyText = JSON.stringify(serializable, null, 2);
    win.__SB_IMMERSIVE_TRACE__ = next;
    return next;
  };
  const mark = (element: Element | null, attribute: string) => {
    if (!element) return;
    let attrs = originals.get(element);
    if (!attrs) {
      attrs = new Map();
      originals.set(element, attrs);
    }
    if (!attrs.has(attribute)) attrs.set(attribute, element.getAttribute(attribute));
    element.setAttribute(attribute, 'true');
  };
  const restoreMarks = () => {
    for (const [element, attrs] of originals) {
      for (const [attribute, value] of attrs) restoreAttribute(element, attribute, value);
    }
    originals.clear();
  };
  const installStyle = () => {
    if (doc.getElementById(STYLE_ID)) {
      styleElement = doc.getElementById(STYLE_ID) as HTMLStyleElement;
      return;
    }
    styleElement = doc.createElement('style');
    styleElement.id = STYLE_ID;
    styleElement.dataset.secondbrainDiagnosticExclude = 'true';
    styleElement.textContent = `
      body[data-secondbrain-immersive="true"] #app-sidebar,
      body[data-secondbrain-immersive="true"] [data-sb-host-banner="true"],
      body[data-secondbrain-immersive="true"] [data-sb-host-mobile-header="true"],
      body[data-secondbrain-immersive="true"] [data-sb-host-mobile-spacer="true"] { display: none !important; }
      body[data-secondbrain-immersive="true"] [data-sb-host-content-offset="true"] {
        padding-top: 0 !important; padding-inline: 0 !important; margin-top: 0 !important;
        top: auto !important; transform: none !important; width: 100% !important;
        min-height: 100vh !important; box-sizing: border-box !important;
        background: var(--sb-bg, #080810) !important;
      }
    `;
    doc.head.appendChild(styleElement);
  };
  const apply = () => {
    const root = doc.getElementById('root');
    if (!root) return;
    const elements = resolveHostChrome(root);
    mark(elements.banner, 'data-sb-host-banner');
    elements.mobileHeaders.forEach((element) => mark(element, 'data-sb-host-mobile-header'));
    elements.spacers.forEach((element) => mark(element, 'data-sb-host-mobile-spacer'));
    mark(elements.contentWrapper, 'data-sb-host-content-offset');
    if (elements.sidebar) mark(elements.sidebar, 'data-sb-host-sidebar');
    const header = elements.banner ?? elements.mobileHeaders[0] ?? null;
    const spacer = elements.spacers[0] ?? null;
    const getStyle = (element: Element | null) => element ? win.getComputedStyle(element).display : 'unmatched';
    const pluginHeader = doc.querySelector('.sb-app .workspace-header');
    publish('init:measure', {
      immersiveActive: doc.body.getAttribute('data-secondbrain-immersive') === 'true',
      overrideStyleInstalled: !!doc.getElementById(STYLE_ID),
      headerMatched: !!header,
      spacerMatched: elements.spacers.length > 0,
      headerStyle: getStyle(header),
      spacerStyle: getStyle(spacer),
      secondBrainHeaderTop: pluginHeader ? pluginHeader.getBoundingClientRect().top : null,
    });
  };
  const begin = () => {
    if (active || !routeIsActive(win.location.pathname)) return;
    const current = trace();
    originalBodyValue = doc.body.getAttribute('data-secondbrain-immersive');
    publish('init:start', { initCallCount: current.initCallCount + 1 });
    doc.body.setAttribute('data-secondbrain-immersive', 'true');
    installStyle();
    apply();
    active = true;
    const success = trace();
    publish('init:complete', { initSuccessCount: success.initSuccessCount + 1 });
    if (typeof MutationObserver !== 'undefined') {
      observer = new MutationObserver(() => apply());
      const root = doc.getElementById('root');
      if (root) observer.observe(root, { childList: true, subtree: true });
    }
  };
  const end = (reason: string) => {
    if (!active) return;
    publish('cleanup:start', { lastCleanupReason: reason });
    observer?.disconnect();
    observer = null;
    styleElement?.remove();
    styleElement = null;
    restoreMarks();
    restoreAttribute(doc.body, 'data-secondbrain-immersive', originalBodyValue);
    originalBodyValue = null;
    active = false;
    const current = trace();
    publish('cleanup:complete', {
      cleanupCallCount: current.cleanupCallCount + 1,
      lastCleanupReason: reason,
      immersiveActive: false,
      overrideStyleInstalled: false,
      headerStyle: 'restored',
      spacerStyle: 'restored',
    });
  };
  const routeChanged = () => routeIsActive(win.location.pathname) ? begin() : end('route-change');

  return {
    start(onChange?: (value: Trace) => void) {
      const refresh = () => onChange?.(trace());
      const onRoute = () => { routeChanged(); refresh(); };
      win.addEventListener('popstate', onRoute);
      win.addEventListener('hashchange', onRoute);
      const onPageHide = () => { end('pagehide'); refresh(); };
      const onPageShow = () => { routeChanged(); refresh(); };
      win.addEventListener('pagehide', onPageHide);
      win.addEventListener('pageshow', onPageShow);
      if (routeIsActive(win.location.pathname)) begin();
      else publish('init:skipped-wrong-route');
      refresh();
      return () => {
        end('component-unmount');
        win.removeEventListener('popstate', onRoute);
        win.removeEventListener('hashchange', onRoute);
        win.removeEventListener('pagehide', onPageHide);
        win.removeEventListener('pageshow', onPageShow);
        refresh();
      };
    },
  };
}

export function useImmersiveTrace(): Trace {
  const debug = new URLSearchParams(location.search).get('sb_debug') === 'layout';
  const [value, setValue] = useState<Trace>(() => ({
    ...window.__SB_IMMERSIVE_TRACE__ ?? initialTrace,
    debug,
    activeRoute: location.pathname,
  }));
  useEffect(() => createImmersiveController(document, window).start((next) => setValue({ ...next, debug })), [debug]);
  return value;
}
