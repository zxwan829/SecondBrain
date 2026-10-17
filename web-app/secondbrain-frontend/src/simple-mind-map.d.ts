declare module 'simple-mind-map' {
  export type MindMapTree = {
    data: { text: string; richText?: false; [key: string]: unknown };
    children: MindMapTree[];
    [key: string]: unknown;
  };

  export type MindMapInstance = {
    getData(withConfig?: boolean): unknown;
    execCommand(name: string, ...args: unknown[]): void;
    on(name: string, callback: (...args: unknown[]) => void): void;
    off(name: string, callback: (...args: unknown[]) => void): void;
    destroy(): void;
    resize(): void;
    view?: { setTransformData(data: unknown): void };
  };

  const MindMap: {
    new(options: Record<string, unknown> & { el: HTMLElement; data: MindMapTree }): MindMapInstance;
    usePlugin(plugin: unknown): typeof MindMap;
  };
  export default MindMap;
}

declare module 'simple-mind-map/src/plugins/Drag.js' {
  const Drag: unknown;
  export default Drag;
}
