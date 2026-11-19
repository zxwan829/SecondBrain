export type Home = Record<string, unknown>;
export async function fetchHome(signal?: AbortSignal): Promise<Home> {
  const response = await fetch('/api/home', { credentials: 'same-origin', cache: 'no-store', signal });
  if (!response.ok) throw new Error(`home HTTP ${response.status}`);
  return response.json() as Promise<Home>;
}
