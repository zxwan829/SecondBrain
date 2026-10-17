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
  };

  const MindMap: {
    new(options: Record<string, unknown> & { el: HTMLElement; data: MindMapTree }): MindMapInstance;
  };
  export default MindMap;
}
