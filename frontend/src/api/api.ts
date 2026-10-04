// Thin client for the Pravaha-X backend. Token is kept in sessionStorage (cleared when the tab closes).
const BASE: string = ((import.meta as any).env?.VITE_API_URL as string | undefined) ?? 'http://localhost:8000';
const KEY = 'pravaha_token';

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export const getToken = (): string | null => sessionStorage.getItem(KEY);
export const setToken = (t: string | null) => (t ? sessionStorage.setItem(KEY, t) : sessionStorage.removeItem(KEY));

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json', ...(init.headers as any) };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(BASE + path, { ...init, headers });
  if (res.status === 401 && token) setToken(null);          // expired session
  if (!res.ok) {
    let detail = res.statusText;
    try { const j = await res.json(); detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail); } catch { /* keep statusText */ }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

const post = <T,>(p: string, body?: unknown) => request<T>(p, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  login: (municipality_id: string, password: string) =>
    post<{ token: string; user: { username: string; role: string } }>('/api/auth/login', { municipality_id, password }),
  nodes: (hours: number) => request<{ data: any[]; meta: any }>(`/api/nodes?hours=${hours}`),
  adminNodes: (hours: number) => request<{ data: any[]; meta: any }>(`/api/admin/nodes?hours=${hours}`),
  reports: () => request<{ data: any[] }>('/api/admin/reports'),
  logs: () => request<{ data: any[] }>('/api/admin/logs?limit=500'),
  createReport: (b: { name: string; phone: string; location: string; description: string; lat?: number; lon?: number }) =>
    post<{ id: string; status: string; timestamp: string }>('/api/reports', b),
  approve: (id: string, node_id?: string) => post<any>(`/api/admin/reports/${id}/approve`, node_id ? { node_id } : {}),
  reject: (id: string) => post<any>(`/api/admin/reports/${id}/reject`, {}),
  setMeasures: (id: string, measures: string) => post<any>(`/api/admin/reports/${id}/measures`, { measures }),
  blocks: () => request<{ data: any[] }>('/api/admin/blocks'),
  blockNode: (node_id: string) => post<any>('/api/admin/blocks', { node_id }),
  unblockNode: (node_id: string) => request<any>(`/api/admin/blocks/${encodeURIComponent(node_id)}`, { method: 'DELETE' }),
  setRain: (rain_mm_hr: number) => post<any>('/api/admin/rain', { rain_mm_hr }),
  reset: (clear_blocks = false) => post<any>('/api/admin/reset', { clear_blocks }),
  route: (start: { lat: number; lon: number }, destination: { lat: number; lon: number }) =>
    post<any>('/api/route', { start, destination }),
  pipes: () => request<any>('/api/pipes'),
  nodeDetail: (id: string) => request<{ data: any }>(`/api/admin/nodes/${encodeURIComponent(id)}`),
  overview: () => request<{ data: any }>('/api/admin/overview'),
};
