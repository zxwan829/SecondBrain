export type Home = Record<string, unknown>;
export async function fetchHome(): Promise<Home> {
  const response = await fetch('/api/plugins/secondbrain/home', { credentials: 'same-origin' });
  if (!response.ok) throw new Error(`home HTTP ${response.status}`);
  return response.json() as Promise<Home>;
}
