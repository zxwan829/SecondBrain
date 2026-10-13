import { App } from './App';
import './styles/app.css';

declare global {
  interface Window { __HERMES_PLUGIN_SDK__?: { React: typeof import('react'); hooks: { useEffect: typeof import('react').useEffect }; }; __HERMES_PLUGINS__?: { register: (name: string, component: unknown) => void } }
}

const sdk = window.__HERMES_PLUGIN_SDK__;
if (sdk && window.__HERMES_PLUGINS__) {
  window.__HERMES_PLUGINS__.register(__SB_PLUGIN_ID__, App);
}
