/// <reference types="vite/client" />
interface ImportMetaEnv {
  readonly VITE_PLUGIN_ID?: string;
  readonly VITE_CORE_REVIEW_API?: string;
  readonly VITE_DASHBOARD_ORIGIN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare const __SB_PLUGIN_ID__: string;
