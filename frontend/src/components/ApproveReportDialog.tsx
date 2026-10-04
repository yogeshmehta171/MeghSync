import React, { useMemo, useState } from 'react';
import { Node } from '../types';
import PlacePicker from './PlacePicker';

interface Props {
  report: any;                                   // the report being approved
  nodes: Node[];
  onCancel: () => void;
  onConfirm: (nodeId: string) => Promise<void>;  // throws on failure; the message is shown in the dialog
}

const inputCls = 'w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-teal-500';
const lc = (s: string) => (s || '').trim().toLowerCase();

// Distance in metres between two lat/lng points (good enough for "nearest node").
const distM = (a: [number, number], b: [number, number]) => {
  const R = 6371000, rad = Math.PI / 180;
  const dLat = (b[0] - a[0]) * rad, dLng = (b[1] - a[1]) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[0] * rad) * Math.cos(b[0] * rad) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
};

// Step 1: choose the location (street / place). Step 2: choose the node on it. Type or pick from the list.
export default function ApproveReportDialog({ report, nodes, onCancel, onConfirm }: Props) {
  const matched = report.matchedNodeId ? nodes.find(n => n.id === report.matchedNodeId) : undefined;
  const [locText, setLocText] = useState(matched?.location ?? '');
  const [nodeText, setNodeText] = useState(matched?.id ?? '');
  const [nodeId, setNodeId] = useState<string | null>(matched?.id ?? null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // If the citizen dropped a pin, offer the closest node as a one-click suggestion (never applied automatically).
  const nearest = useMemo(() => {
    if (report.lat == null || report.lon == null || nodes.length === 0) return null;
    let best: Node | null = null, bestD = Infinity;
    for (const n of nodes) {
      const d = distM([report.lat, report.lon], n.coordinates);
      if (d < bestD) { bestD = d; best = n; }
    }
    return best ? { node: best, d: Math.round(bestD) } : null;
  }, [report.lat, report.lon, nodes]);

  // Once a known location is chosen, the node list only shows nodes on that location.
  const nodesForList = useMemo(() => {
    const key = lc(locText);
    if (key && nodes.some(n => lc(n.location) === key)) return nodes.filter(n => lc(n.location) === key);
    return nodes;
  }, [nodes, locText]);

  const resolvedNode = useMemo(
    () => (nodeId ? nodes.find(n => n.id === nodeId) : nodes.find(n => lc(n.id) === lc(nodeText))),
    [nodes, nodeId, nodeText]
  );

  const chooseNode = (n: Node) => { setNodeText(n.id); setNodeId(n.id); setLocText(n.location || ''); setErr(null); };

  const submit = async () => {
    if (!resolvedNode) { setErr('Choose a node from the list, or type an exact node ID.'); return; }
    setBusy(true); setErr(null);
    try { await onConfirm(resolvedNode.id); }
    catch (e: any) { setErr(e?.message ?? 'Could not approve this report'); setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-[2000] flex items-center justify-center bg-black/60 p-4" onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onCancel(); }}>
      <div className="w-full max-w-md bg-card border border-border rounded-xl shadow-2xl p-5">
        <h2 className="text-sm font-bold text-foreground uppercase tracking-wide mb-1">Approve report {report.id}</h2>
        <p className="text-xs text-muted-foreground mb-4">Approving blocks the node you choose below, so citizen routes avoid it.</p>

        <div className="text-xs bg-secondary/50 border border-border rounded-lg p-3 mb-4 space-y-1">
          <div><span className="text-muted-foreground">Reported location: </span><span className="text-foreground">{report.location}</span></div>
          <div className="italic text-muted-foreground break-words">"{report.description}"</div>
        </div>

        <label className="block text-xs font-medium text-muted-foreground mb-1">1. Location (street / place)</label>
        <PlacePicker
          variant="dark" mode="location" nodes={nodes} value={locText}
          placeholder="Type a street or pick from the list"
          inputClassName={inputCls}
          onChange={(t) => { setLocText(t); }}
          onPick={(pk) => {
            setLocText(pk.text);
            if (resolvedNode && lc(resolvedNode.location) !== lc(pk.text)) { setNodeText(''); setNodeId(null); }   // old node is on another street
            setErr(null);
          }}
        />

        <label className="block text-xs font-medium text-muted-foreground mt-4 mb-1">2. Node to block</label>
        <PlacePicker
          variant="dark" mode="node" nodes={nodesForList} value={nodeText}
          placeholder="Type a node ID or pick from the list"
          inputClassName={inputCls}
          onChange={(t) => { setNodeText(t); setNodeId(null); }}
          onPick={(pk) => { const n = nodes.find(x => x.id === pk.nodeId); if (n) chooseNode(n); }}
        />
        {resolvedNode
          ? <div className="text-[11px] text-teal-400 mt-1">Will block {resolvedNode.id}{resolvedNode.location ? ` (${resolvedNode.location})` : ''}</div>
          : nodeText.trim() && <div className="text-[11px] text-orange-400 mt-1">No node with that ID yet. Pick one from the list.</div>}

        {nearest && !resolvedNode && (
          <button type="button" onClick={() => chooseNode(nearest.node)} className="mt-2 text-[11px] text-teal-400 hover:underline text-left">
            Citizen's pin is {nearest.d} m from {nearest.node.id}{nearest.node.location ? ` (${nearest.node.location})` : ''}. Use this node
          </button>
        )}

        {err && <div className="text-xs text-red-400 mt-3">{err}</div>}

        <div className="flex justify-end gap-2 mt-5">
          <button type="button" disabled={busy} onClick={onCancel} className="px-3 py-1.5 rounded bg-secondary hover:bg-secondary/70 text-foreground text-xs font-medium border border-border">Cancel</button>
          <button type="button" disabled={busy || !resolvedNode} onClick={submit} className="px-3 py-1.5 rounded bg-teal-600 hover:bg-teal-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-medium shadow-lg shadow-teal-500/20">
            {busy ? 'Approving...' : 'Approve and block node'}
          </button>
        </div>
      </div>
    </div>
  );
}
