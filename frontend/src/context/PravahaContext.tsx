import React, { createContext, useCallback, useContext, useEffect, useRef, useState, ReactNode } from 'react';
import { Node, Report, Log } from '../types';
import { api, setToken, getToken } from '../api/api';

// Same interface as the mock context, plus: login/logout/isAuthenticated, meta (freshness), error,
// blockNode/unblockNode, findRoute. Existing pages keep working unchanged.
interface PravahaContextType {
  nodes: Node[];
  reports: Report[];
  logs: Log[];
  addReport: (r: Omit<Report, 'id' | 'status' | 'timestamp'> & { lat?: number; lon?: number }) => Promise<{ id: string; status: string; timestamp: string }>;
  approveReport: (reportId: string, nodeId?: string) => Promise<void>;
  rejectReport: (reportId: string) => Promise<void>;
  saveMeasures: (reportId: string, measures: string) => Promise<void>;
  setRainfall: (mmHr: number) => void;
  rainfall: number;
  forecastHour: number;
  setForecastHour: (hour: number) => void;
  // new
  isAuthenticated: boolean;
  login: (id: string, password: string) => Promise<void>;
  logout: () => void;
  meta: any | null;            // freshness block: meta.stale, meta.isMockData, meta.ageSeconds ...
  error: string | null;
  blockNode: (nodeId: string) => Promise<void>;
  unblockNode: (nodeId: string) => Promise<void>;
  findRoute: typeof api.route;
  reset: (clearBlocks?: boolean) => Promise<void>;   // keeps official-approved blocks unless clearBlocks is true
}

const PravahaContext = createContext<PravahaContextType | undefined>(undefined);
const POLL_MS = 5000;

const toNode = (n: any): Node => ({ ...n, elevation: n.elevation ?? 0, imperviousness: n.imperviousness ?? 0 });

// Keep the SAME object for a node whose data did not change, so the map only redraws what really changed.
const mergeNodes = (prev: Node[], next: Node[]): Node[] => {
  const old = new Map(prev.map(n => [n.id, n] as const));
  return next.map(n => {
    const o = old.get(n.id);
    return o && JSON.stringify(o) === JSON.stringify(n) ? o : n;
  });
};

export const PravahaProvider = ({ children }: { children: ReactNode }) => {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [reports, setReports] = useState<Report[]>([]);
  const [logs, setLogs] = useState<Log[]>([]);
  const [rainfall, setRainfallState] = useState(0);
  const [forecastHour, setForecastHour] = useState(0);
  const [meta, setMeta] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isAuthenticated, setAuth] = useState<boolean>(!!getToken());
  const rainTimer = useRef<number | undefined>(undefined);

  const refresh = useCallback(async () => {
    try {
      const authed = !!getToken();
      const n = authed ? await api.adminNodes(forecastHour) : await api.nodes(forecastHour);
      setNodes(prev => mergeNodes(prev, n.data.map(toNode)));
      setMeta(n.meta);
      if (authed) {
        const [r, l] = await Promise.all([api.reports(), api.logs()]);
        setReports(r.data);
        setLogs(l.data.slice().reverse());      // oldest first, like the mock
      }
      setError(null);
    } catch (e: any) {
      if (e?.status === 401) setAuth(false);
      setError(e?.message ?? 'Cannot reach the server');
      setMeta((m: any) => (m ? { ...m, stale: true } : m));   // greyscale/warn: data is no longer fresh
    }
  }, [forecastHour]);

  useEffect(() => {
    refresh();
    const t = window.setInterval(refresh, POLL_MS);
    return () => window.clearInterval(t);
  }, [refresh, isAuthenticated]);

  const login = async (id: string, password: string) => {
    const r = await api.login(id, password);
    setToken(r.token);
    setAuth(true);
  };
  const logout = () => { setToken(null); setAuth(false); setReports([]); setLogs([]); };

  const act = async (fn: () => Promise<unknown>) => { await fn(); await refresh(); };

  const value: PravahaContextType = {
    nodes, reports, logs, rainfall, forecastHour, setForecastHour, isAuthenticated, login, logout, meta, error,
    addReport: (r) => api.createReport({ name: r.name, phone: r.phone, location: r.location, description: r.description, lat: (r as any).lat, lon: (r as any).lon }),
    // The official always chooses the node in the approve dialog, so that choice is what gets blocked.
    approveReport: (id, nodeId) => act(() => api.approve(id, nodeId)),
    rejectReport: (id) => act(() => api.reject(id)),
    saveMeasures: (id, text) => act(() => api.setMeasures(id, text)),
    setRainfall: (mm) => {
      setRainfallState(mm);
      window.clearTimeout(rainTimer.current);                  // debounce slider drags
      rainTimer.current = window.setTimeout(() => { api.setRain(mm).catch(e => setError(e.message)); }, 300);
    },
    // Optimistic: the node changes colour at once; the server answer then confirms (or undoes) it.
    blockNode: async (id) => {
      setNodes(prev => prev.map(n => n.id === id ? { ...n, blocked: true, status: 'FLOODED', risk: 'Critical', blockSource: 'manual' } : n));
      try { await api.blockNode(id); } finally { await refresh(); }
    },
    unblockNode: async (id) => {
      setNodes(prev => prev.map(n => n.id === id ? { ...n, blocked: false, blockSource: null } : n));
      try { await api.unblockNode(id); } finally { await refresh(); }
    },
    findRoute: api.route,
    reset: (clearBlocks = false) => act(async () => { await api.reset(clearBlocks); setRainfallState(0); }),
  };

  return <PravahaContext.Provider value={value}>{children}</PravahaContext.Provider>;
};

export const usePravaha = () => {
  const ctx = useContext(PravahaContext);
  if (ctx === undefined) throw new Error('usePravaha must be used within a PravahaProvider');
  return ctx;
};
