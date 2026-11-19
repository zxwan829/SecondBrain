// Keep upstream implementation checking separate from this host's strict types.
export const SlashMenu: new (...args: any[]) => HTMLElement & { items: any[]; context: any; onComplete: () => void; onAbort: () => void };
export function buildSlashMenuItems(...args: any[]): any[];
