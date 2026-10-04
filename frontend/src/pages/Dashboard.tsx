import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { usePravaha } from '../context/PravahaContext';
import { MapContainer, TileLayer, CircleMarker, Popup, GeoJSON, Polyline, ZoomControl, useMap, useMapEvents } from 'react-leaflet';
import PlacePicker, { PickedPlace } from '../components/PlacePicker';
import CountBadge from '../components/CountBadge';
import { Crosshair, Layers, RotateCcw, Navigation, CloudRain, Clock, AlertTriangle, Bell, Activity, BarChart2, MessageSquare, Ban, MapPin } from 'lucide-react';
import { format } from 'date-fns';
import { api } from '../api/api';
import 'leaflet/dist/leaflet.css';
import { BarChart, Bar, XAxis, YAxis, Tooltip as RechartsTooltip, ResponsiveContainer, LineChart, Line, ReferenceLine, LabelList } from 'recharts';
import { Node, BlockInfo } from '../types';

const riskColor = (risk: string) => {
  switch (risk) {
    case 'Critical': return '#ef4444';
    case 'High': return '#f97316';
    case 'Moderate': return '#eab308';
    case 'Low': return '#3b82f6';
    default: return '#22c55e';
  }
};

// Stable style function: a new one on every render would make Leaflet restyle thousands of pipe segments each time.
const pipeStyle = () => ({ color: '#3b82f6', weight: 2, opacity: 0.6 });

// Real recent depth of one node (last updates), refreshed while its popup is open.
function NodeDepthChart({ nodeId }: { nodeId: string }) {
  const [data, setData] = useState<{ time: string; depth: number }[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = () => api.nodeDetail(nodeId).then(r => {
      if (!alive) return;
      const rec: { depthCm: number }[] = r.data.recent ?? [];
      setData(rec.map((pt, i) => ({ time: i === rec.length - 1 ? 'now' : String(i - (rec.length - 1)), depth: pt.depthCm })));
      setFailed(false);
    }).catch(() => { if (alive) setFailed(true); });
    load();
    const t = window.setInterval(load, 5000);
    return () => { alive = false; window.clearInterval(t); };
  }, [nodeId]);

  return (
    <>
      <div className="text-[10px] font-bold text-[#647b8f] uppercase tracking-wider mb-2">
        Recent depth (cm), last updates (about 5 s apart)
      </div>
      <div className="h-[120px] w-[340px] -ml-[30px]">
        {failed && !data ? <div className="text-xs text-red-500 pl-8">Could not load readings.</div>
          : !data ? <div className="text-xs text-slate-500 pl-8">Loading...</div>
          : data.length === 0 ? <div className="text-xs text-slate-500 pl-8">No readings yet.</div>
          : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 0 }}>
                <YAxis domain={[0, (max: number) => Math.max(20, Math.ceil(max + 2))]} tickCount={6} axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#647b8f' }} width={25} />
                <XAxis dataKey="time" axisLine={{ stroke: '#0f7696', strokeWidth: 2 }} tickLine={false} tick={{ fontSize: 10, fill: '#647b8f' }} tickMargin={5} />
                <ReferenceLine y={15} stroke="#d77a7a" strokeDasharray="3 3" />
                <Line type="monotone" dataKey="depth" stroke="#0f7696" strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
      </div>
      <div className="text-[10px] text-[#647b8f] mt-1">Dashed line = 15 cm, the depth at which routes avoid the street.</div>
    </>
  );
}

interface NodeMarkerProps {
  node: Node;
  selected: boolean;
  onSelect: (id: string) => void;
  onBlock: (id: string) => void;
  onUnblock: (id: string) => void;
}

// One map dot. memo + stable props = it only redraws when this node (or its selection) really changes.
const NodeMarker = React.memo(function NodeMarker({ node, selected, onSelect, onBlock, onUnblock }: NodeMarkerProps) {
  const color = node.blocked ? '#a855f7' : riskColor(node.risk);
  const pathOptions = useMemo(() => ({
    fillColor: color,
    color: selected || node.blocked ? '#ffffff' : color,
    fillOpacity: selected || node.blocked ? 1 : 0.8,
    weight: selected ? 3 : node.blocked ? 2 : 1,
  }), [color, selected, node.blocked]);
  const handlers = useMemo(() => ({ click: () => onSelect(node.id) }), [node.id, onSelect]);

  return (
    <CircleMarker center={node.coordinates} radius={selected ? 8 : node.blocked ? 6 : 4} pathOptions={pathOptions} eventHandlers={handlers}>
      <Popup className="municipal-popup">
                <div className="w-[320px] font-sans text-slate-800 bg-white -m-[13px] p-5 rounded-[12px] shadow-xl border border-slate-200">
                  <div className="flex justify-between items-start mb-6">
                    <div>
                      <h2 className="text-[22px] font-extrabold text-[#092d47] leading-none mb-2">{node.id}</h2>
                      <span className={`text-[10px] px-2.5 py-0.5 rounded-full font-bold uppercase tracking-wide ${
                        node.status === 'FLOODED' ? 'bg-red-100 text-red-600' : 
                        node.status === 'SURCHARGE' ? 'bg-orange-100 text-orange-600' : 'bg-[#e5f5ec] text-[#298c56]'
                      }`}>
                        {node.blocked ? 'BLOCKED' : node.status === 'PASSABLE' ? 'SAFE' : node.status}
                      </span>
                    </div>
                    <div className="text-right">
                      <div className="text-[22px] font-extrabold text-[#092d47] leading-none">{(node.depth * 100).toFixed(1)} cm</div>
                      <div className="text-[11px] text-slate-500 mt-1 font-medium">Predicted Depth</div>
                    </div>
                  </div>

                  <div className="mb-4">
                    <div className="text-[11px] font-bold text-[#647b8f] uppercase tracking-wider mb-1">Routing Impact</div>
                    <div className="text-[13px] text-[#092d47] font-medium">
                      {node.blocked ? 'Blocked by an official. Routes avoid this node.' : node.status === 'FLOODED' ? 'Critical. Avoid area.' : node.status === 'SURCHARGE' ? 'Moderate delays expected.' : 'None. Routes pass normally.'}
                    </div>
                  </div>

                  {node.blocked ? (
                    <button onClick={() => onUnblock(node.id)} className="bg-purple-700 hover:bg-purple-800 text-white text-[13px] font-bold py-2 px-4 rounded-md mb-6 w-full text-left transition-colors">
                      BLOCKED NODE (RELEASE)
                    </button>
                  ) : (
                    <button onClick={() => onBlock(node.id)} className="bg-[#0f7696] hover:bg-[#0b5d77] text-white text-[13px] font-bold py-2 px-4 rounded-md mb-6 w-full text-left transition-colors">
                      BLOCK (NODE)
                    </button>
                  )}

                  <NodeDepthChart nodeId={node.id} />
                </div>
              </Popup>
    </CircleMarker>
  );
});

// Moves the map when the "selected node" button is pressed.
function FlyTo({ req }: { req: { coords: [number, number]; tick: number } | null }) {
  const map = useMap();
  useEffect(() => {
    if (req) map.flyTo(req.coords, Math.max(map.getZoom(), 17), { duration: 0.8 });
  }, [req, map]);
  return null;
}

// While a routing box is armed (pin button), the next map click picks that point.
function MapPointPicker({ armed, onPick }: { armed: boolean; onPick: (lat: number, lng: number) => void }) {
  const map = useMap();
  useEffect(() => {
    map.getContainer().style.cursor = armed ? 'crosshair' : '';
    return () => { map.getContainer().style.cursor = ''; };
  }, [armed, map]);
  useMapEvents({
    click: (e) => {
      if (!armed) return;
      map.closePopup();                       // a click on a node dot would otherwise also open its popup
      onPick(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

const fmtKm = (m?: number) => (m == null ? '-' : (m / 1000).toFixed(2) + ' km');
const fmtMin = (x?: number) => (x == null ? '-' : x.toFixed(1) + ' min');

export default function Dashboard() {
  const { nodes, rainfall, setRainfall, reports, forecastHour, setForecastHour, blockNode, unblockNode, reset, findRoute } = usePravaha();
  const [pipes, setPipes] = useState<any | null>(null);
  const [resetting, setResetting] = useState(false);

  // ---- emergency routing (node to node, or by place name)
  const [startText, setStartText] = useState('');
  const [endText, setEndText] = useState('');
  const [startPick, setStartPick] = useState<PickedPlace | null>(null);
  const [endPick, setEndPick] = useState<PickedPlace | null>(null);
  const [routeRes, setRouteRes] = useState<any | null>(null);
  const [routeErr, setRouteErr] = useState<string | null>(null);
  const [routeBusy, setRouteBusy] = useState(false);
  const lastQuery = useRef<[PickedPlace, PickedPlace] | null>(null);

  // Real drainage pipes (loaded once; they do not change)
  useEffect(() => {
    api.pipes().then(setPipes).catch(() => setPipes(null));
  }, []);

  const doReset = async (clearBlocks: boolean) => {
    const msg = clearBlocks
      ? 'Reset the simulation AND release all blocked nodes?'
      : 'Reset the simulation? Rain returns to 0. Approved blocks are kept.';
    if (!window.confirm(msg)) return;
    setResetting(true);
    try { await reset(clearBlocks); } catch (e: any) { window.alert(e?.message ?? 'Reset failed'); }
    setResetting(false);
  };
  const [selectedNodeId, setSelectedNodeId] = useState<string>('');
  const [mapStyle, setMapStyle] = useState<'dark' | 'light'>('dark');
  const [focusReq, setFocusReq] = useState<{ coords: [number, number]; tick: number } | null>(null);
  const [ov, setOv] = useState<any | null>(null);

  // Click a node to select it, click it again to deselect.
  const onSelect = useCallback((id: string) => setSelectedNodeId(prev => (prev === id ? '' : id)), []);
  // Stable wrappers (the context functions change on every refresh, which would redraw every dot)
  const actionsRef = useRef({ blockNode, unblockNode });
  actionsRef.current = { blockNode, unblockNode };
  const onBlock = useCallback((id: string) => {
    actionsRef.current.blockNode(id).catch((e: any) => window.alert(e?.message ?? 'Could not block'));
  }, []);
  const onUnblock = useCallback((id: string) => {
    actionsRef.current.unblockNode(id).catch((e: any) => window.alert(e?.message ?? 'Could not release'));
  }, []);
  const [routingMode, setRoutingMode] = useState<'node' | 'location'>('node');
  const [pickTarget, setPickTarget] = useState<'start' | 'end' | null>(null);
  const [blockInfos, setBlockInfos] = useState<BlockInfo[]>([]);
  const [unblocking, setUnblocking] = useState<string | null>(null);
  const [activeWidgets, setActiveWidgets] = useState({
    routing: false,
    rainfall: false,
    nowcasting: false,
    impact: false,
    alerts: false,
    inspector: false,
    graph: false,
    reports: false,
    blocked: false,
  });

  useEffect(() => {
    if (!activeWidgets.graph) return;
    let alive = true;
    const load = () => api.overview().then(r => { if (alive) setOv(r.data); }).catch(() => {});
    load();
    const t = window.setInterval(load, 5000);
    return () => { alive = false; window.clearInterval(t); };
  }, [activeWidgets.graph]);

  const pipeLayer = useMemo(
    () => (pipes ? <GeoJSON key="pipes" data={pipes} style={pipeStyle} interactive={false} /> : null),
    [pipes]
  );

  const switchMode = (m: 'node' | 'location') => {
    setRoutingMode(m);
    setStartText(''); setEndText(''); setStartPick(null); setEndPick(null);
    setRouteRes(null); setRouteErr(null); lastQuery.current = null; setPickTarget(null);
  };

  // A picked list entry wins; otherwise accept an exact typed node ID / place name.
  const resolvePlace = (text: string, pick: PickedPlace | null): PickedPlace | null => {
    if (pick && pick.text === text) return pick;
    const t = text.trim().toLowerCase();
    if (!t) return null;
    const n = routingMode === 'node'
      ? nodes.find(x => x.id.toLowerCase() === t)
      : nodes.find(x => (x.location || '').trim().toLowerCase() === t);
    return n ? { text, label: n.location, coords: n.coordinates, nodeId: n.id } : null;
  };

  const runRoute = async (a: PickedPlace, b: PickedPlace) => {
    setRouteBusy(true);
    setRouteErr(null);
    try {
      const r = await findRoute({ lat: a.coords[0], lon: a.coords[1] }, { lat: b.coords[0], lon: b.coords[1] });
      setRouteRes(r);
      lastQuery.current = [a, b];
    } catch (e: any) {
      setRouteRes(null);
      setRouteErr(e?.message ?? 'Could not calculate a route');
    }
    setRouteBusy(false);
  };

  const calculateRoute = () => {
    const a = resolvePlace(startText, startPick);
    const b = resolvePlace(endText, endPick);
    if (!a || !b) {
      setRouteErr(routingMode === 'node' ? 'Choose a valid start and destination node (type an ID or pick from the list).' : 'Choose a start and a destination place from the list.');
      return;
    }
    setStartPick(a); setEndPick(b); setPickTarget(null);
    runRoute(a, b);
  };

  // Map click while a pin button is armed. Node tab: snap to the nearest node. Location tab: use the exact point.
  const pickFromMap = (lat: number, lng: number) => {
    if (!pickTarget) return;
    let pk: PickedPlace;
    if (routingMode === 'node') {
      const k = Math.cos((lat * Math.PI) / 180);
      let best: Node | null = null, bd = Infinity;
      for (const n of nodes) {
        const dy = n.coordinates[0] - lat, dx = (n.coordinates[1] - lng) * k;
        const d = dx * dx + dy * dy;
        if (d < bd) { bd = d; best = n; }
      }
      if (!best) return;
      pk = { text: best.id, label: best.location, coords: best.coordinates, nodeId: best.id };
    } else {
      pk = { text: `Map point ${lat.toFixed(5)}, ${lng.toFixed(5)}`, label: 'Map point', coords: [lat, lng], nodeId: '' };
    }
    if (pickTarget === 'start') { setStartText(pk.text); setStartPick(pk); setPickTarget(endText ? null : 'end'); }
    else { setEndText(pk.text); setEndPick(pk); setPickTarget(null); }
    setRouteErr(null); setRouteRes(null); lastQuery.current = null;
  };

  // Blocking or releasing a node changes the street prices: recalculate the route that is on screen.
  const blockedKey = nodes.filter(n => n.blocked).map(n => n.id).join(',');
  useEffect(() => {
    if (lastQuery.current) runRoute(lastQuery.current[0], lastQuery.current[1]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [blockedKey]);

  // Details of the active blocks (who, when, why) while the Blocked Nodes panel is open.
  useEffect(() => {
    if (!activeWidgets.blocked) return;
    let alive = true;
    const load = () => api.blocks().then(r => { if (alive) setBlockInfos(r.data as BlockInfo[]); }).catch(() => {});
    load();
    const t = window.setInterval(load, 5000);
    return () => { alive = false; window.clearInterval(t); };
  }, [activeWidgets.blocked, blockedKey]);

  const blockedNodes = useMemo(() => nodes.filter(n => n.blocked), [nodes]);
  const blockMap = useMemo(() => new Map(blockInfos.map(b => [b.nodeId, b] as const)), [blockInfos]);
  const releaseBlocked = async (id: string, reportRef?: string | null) => {
    if (reportRef && !window.confirm(`Node ${id} was blocked from report ${reportRef}. Releasing it marks that report as Resolved. Continue?`)) return;
    setUnblocking(id);
    try { await unblockNode(id); } catch (e: any) { window.alert(e?.message ?? 'Could not release'); }
    setUnblocking(null);
  };


  const toggleWidget = (widgetName: keyof typeof activeWidgets) => {
    setActiveWidgets(prev => {
      const isCurrentlyOpen = prev[widgetName];
      const newState = {
        routing: false,
        rainfall: false,
        nowcasting: false,
        impact: false,
        alerts: false,
        inspector: false,
        graph: false,
        reports: false,
        blocked: false,
      };
      newState[widgetName] = !isCurrentlyOpen;
      return newState;
    });
  };

  const selectedNode = nodes.find(n => n.id === selectedNodeId);
  const sameRoute = !!routeRes && !routeRes.normalRouteFlooded && (routeRes.extraM ?? 0) < 1;

  const getRiskColor = (risk: string) => {
    switch (risk) {
      case 'Critical': return '#ef4444';
      case 'High': return '#f97316';
      case 'Moderate': return '#eab308';
      case 'Low': return '#3b82f6';
      default: return '#22c55e';
    }
  };

  const chartData = [
    { name: '1h', depth: 0.2 }, { name: '2h', depth: 0.5 }, { name: '3h', depth: 1.2 }, { name: '4h', depth: 1.5 }, { name: '5h', depth: 1.1 }
  ];

  const criticalCount = nodes.filter(n => n.risk === 'Critical').length;
  const highCount = nodes.filter(n => n.risk === 'High').length;

  const generateMockTickData = (currentDepth: number) => {
    const data = [];
    // Generate 11 ticks, from -10 to 0
    for (let i = -10; i <= 0; i++) {
      // Small random fluctuation around current depth (in cm)
      const fluctuation = (Math.random() - 0.5) * 2; // +/- 1 cm
      data.push({
        time: i === 0 ? 'now' : i.toString(),
        depth: Math.max(0, (currentDepth * 100) + fluctuation)
      });
    }
    return data;
  };

  return (
    <div className="relative w-full h-full">
      {/* Background Map */}
      <div className="absolute inset-0 z-0">
        <MapContainer center={[13.0418, 80.2341]} zoom={15} className="w-full h-full" zoomControl={false}>
          <ZoomControl position="bottomright" />
          <FlyTo req={focusReq} />
          <TileLayer
            key={mapStyle}
            url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" className={mapStyle === 'dark' ? 'dark-tiles' : ''}
            attribution='&copy; OpenStreetMap contributors'
          />
          {pipeLayer}
          {nodes.map(node => (
            <NodeMarker key={node.id} node={node} selected={selectedNodeId === node.id}
              onSelect={onSelect} onBlock={onBlock} onUnblock={onUnblock} />
          ))}
          <MapPointPicker armed={!!pickTarget} onPick={pickFromMap} />
          {/* Normal route: orange dashed, underneath. Flood-safe route: green solid with a white edge, on top. */}
          {!sameRoute && routeRes?.normal?.path?.length > 1 && <Polyline positions={routeRes.normal.path} color="#ea580c" weight={8} opacity={1} dashArray="14, 8" lineCap="butt" />}
          {routeRes?.safe?.path?.length > 1 && <Polyline positions={routeRes.safe.path} color="#ffffff" weight={10} opacity={0.9} />}
          {routeRes?.safe?.path?.length > 1 && <Polyline positions={routeRes.safe.path} color="#16a34a" weight={6} />}
          {startPick && <CircleMarker center={startPick.coords} radius={9} pathOptions={{ color: '#2563eb', weight: 4, fillColor: 'white', fillOpacity: 1 }} />}
          {endPick && <CircleMarker center={endPick.coords} radius={9} pathOptions={{ color: '#ef4444', weight: 4, fillColor: 'white', fillOpacity: 1 }} />}
        </MapContainer>
      </div>

      {/* Right-hand map buttons */}
      <div className="absolute top-4 right-4 z-[999] flex flex-col gap-2 items-end pointer-events-auto">
        <button
          title={mapStyle === 'dark' ? 'Switch to light map' : 'Switch to dark map'}
          onClick={() => setMapStyle(mapStyle === 'dark' ? 'light' : 'dark')}
          className="bg-card/95 backdrop-blur-md border border-border text-muted-foreground hover:text-foreground p-2 rounded-lg shadow-lg transition-colors"
        >
          <Layers className="w-5 h-5" />
        </button>
        {selectedNode && (
          <button
            title="Move the map back to the selected node"
            onClick={() => setFocusReq({ coords: selectedNode.coordinates, tick: Date.now() })}
            className="bg-teal-600 hover:bg-teal-500 text-white text-xs font-bold px-3 py-2 rounded-lg shadow-lg flex items-center gap-2 transition-colors"
          >
            <Crosshair className="w-4 h-4" /> Selected node
          </button>
        )}
      </div>

      {/* Left Sidebar Widget Toggle Toolbar */}
      <div className="absolute top-4 left-4 z-50 flex flex-col gap-2 bg-card/95 backdrop-blur-md p-2 rounded-xl border border-border shadow-lg pointer-events-auto w-[42px] items-center">
        <div className="flex flex-col gap-2 border-b border-slate-700 pb-2 w-full items-center">
          <button onClick={() => toggleWidget('routing')} className={`p-2 rounded transition-colors ${activeWidgets.routing ? 'bg-teal-600 text-white shadow-md' : 'hover:bg-secondary text-muted-foreground hover:text-foreground'}`} title="Toggle Routing"><Navigation size={18} /></button>
          <button onClick={() => toggleWidget('rainfall')} className={`p-2 rounded transition-colors ${activeWidgets.rainfall ? 'bg-teal-600 text-white shadow-md' : 'hover:bg-secondary text-muted-foreground hover:text-foreground'}`} title="Toggle Rainfall Simulation"><CloudRain size={18} /></button>
          <button onClick={() => toggleWidget('nowcasting')} className={`p-2 rounded transition-colors ${activeWidgets.nowcasting ? 'bg-teal-600 text-white shadow-md' : 'hover:bg-secondary text-muted-foreground hover:text-foreground'}`} title="Toggle Nowcasting"><Clock size={18} /></button>
          <button onClick={() => toggleWidget('impact')} className={`p-2 rounded transition-colors ${activeWidgets.impact ? 'bg-teal-600 text-white shadow-md' : 'hover:bg-secondary text-muted-foreground hover:text-foreground'}`} title="Toggle Predicted Impact"><AlertTriangle size={18} /></button>
          <button onClick={() => toggleWidget('alerts')} className={`p-2 rounded transition-colors ${activeWidgets.alerts ? 'bg-teal-600 text-white shadow-md' : 'hover:bg-secondary text-muted-foreground hover:text-foreground'}`} title="Toggle Active Alerts"><Bell size={18} /></button>
        </div>
        <div className="flex flex-col gap-2 pt-1 w-full items-center">
          <button onClick={() => toggleWidget('inspector')} className={`p-2 rounded transition-colors ${activeWidgets.inspector ? 'bg-teal-600 text-white shadow-md' : 'hover:bg-secondary text-muted-foreground hover:text-foreground'}`} title="Toggle Node Inspector"><Activity size={18} /></button>
          <button onClick={() => toggleWidget('graph')} className={`p-2 rounded transition-colors ${activeWidgets.graph ? 'bg-teal-600 text-white shadow-md' : 'hover:bg-secondary text-muted-foreground hover:text-foreground'}`} title="Toggle Graphical Analysis"><BarChart2 size={18} /></button>
          <button onClick={() => toggleWidget('reports')} className={`relative p-2 rounded transition-colors ${activeWidgets.reports ? 'bg-teal-600 text-white shadow-md' : 'hover:bg-secondary text-muted-foreground hover:text-foreground'}`} title="Toggle Citizen Reports"><MessageSquare size={18} /><CountBadge count={reports.filter(r => r.status === 'PENDING').length} className="absolute -top-1 -right-1 !min-w-[15px] !h-[15px] !text-[9px]" /></button>
          <button onClick={() => toggleWidget('blocked')} className={`relative p-2 rounded transition-colors ${activeWidgets.blocked ? 'bg-teal-600 text-white shadow-md' : 'hover:bg-secondary text-muted-foreground hover:text-foreground'}`} title="Blocked Nodes (unblock here)"><Ban size={18} /><CountBadge count={nodes.filter(n => n.blocked).length} className="absolute -top-1 -right-1 !min-w-[15px] !h-[15px] !text-[9px] !bg-purple-600" /></button>
        </div>
      </div>

      {/* Left Panel */}
      <div className="absolute top-4 left-16 z-10 w-80 flex flex-col gap-4 max-h-[calc(100vh-6rem)] overflow-y-auto pb-4 custom-scrollbar pointer-events-none">
        
        {/* Routing Widget */}
        {activeWidgets.routing && (
        <div className="bg-card/95 backdrop-blur-md p-4 rounded-xl border border-border pointer-events-auto">
          <h3 className="text-xs font-bold text-muted-foreground mb-1 uppercase">Response Navigation</h3>
          <h2 className="text-sm font-semibold text-foreground mb-4">EMERGENCY ROUTING</h2>

          <div className="flex gap-1 bg-secondary/50 p-1 rounded-lg mb-4">
            <button
              onClick={() => switchMode('node')}
              className={`flex-1 text-xs py-1.5 rounded-md transition-colors ${routingMode === 'node' ? 'bg-teal-600 text-white font-bold' : 'text-muted-foreground hover:text-foreground'}`}
            >
              Node
            </button>
            <button
              onClick={() => switchMode('location')}
              className={`flex-1 text-xs py-1.5 rounded-md transition-colors ${routingMode === 'location' ? 'bg-teal-600 text-white font-bold' : 'text-muted-foreground hover:text-foreground'}`}
            >
              Location
            </button>
          </div>

          <div className="mb-2 space-y-2">
            {([
              ['start', startText, setStartText, setStartPick, routingMode === 'node' ? 'Origin: Type an ID or Pick ID' : 'Origin: Type Name or Pick Name'],
              ['end', endText, setEndText, setEndPick, routingMode === 'node' ? 'Destination: Type an ID or Pick ID' : 'Destination: Type Name or Pick Name'],
            ] as const).map(([key, text, setText, setPick, ph]) => (
              <div key={key + routingMode} className="flex items-start gap-1.5">
                <div className="flex-1 min-w-0">
                  <PlacePicker
                    variant="dark"
                    mode={routingMode}
                    nodes={nodes}
                    value={text}
                    placeholder={ph}
                    inputClassName={`w-full bg-secondary border rounded px-3 py-2 text-sm text-foreground focus:outline-none focus:border-teal-500 ${pickTarget === key ? 'border-teal-400' : 'border-slate-600'}`}
                    onChange={(t) => { setText(t); setPick(null); }}
                    onPick={(pk) => { setText(pk.text); setPick(pk); setRouteErr(null); }}
                  />
                </div>
                <button
                  type="button"
                  title={pickTarget === key ? 'Click a point on the map (click again to cancel)' : (key === 'start' ? 'Pick the origin on the map' : 'Pick the destination on the map')}
                  onClick={() => setPickTarget(pickTarget === key ? null : key)}
                  className={`shrink-0 p-2 rounded border transition-colors ${pickTarget === key ? 'bg-teal-600 border-teal-500 text-white' : 'border-slate-600 text-muted-foreground hover:text-foreground hover:bg-secondary'}`}
                >
                  <MapPin size={16} />
                </button>
              </div>
            ))}
          </div>
          <div className="text-[10px] text-muted-foreground mb-3 min-h-[14px]">
            {pickTarget
              ? <span className="text-teal-400 font-semibold">Click the map to set the {pickTarget === 'start' ? 'origin' : 'destination'}{routingMode === 'node' ? ' (nearest node is used)' : ''}.</span>
              : 'Use the pin button next to a box to pick that point on the map.'}
          </div>

          <div className="flex gap-2 mb-4">
            <button onClick={calculateRoute} disabled={routeBusy} className="flex-1 bg-teal-600 hover:bg-teal-500 disabled:opacity-60 text-foreground font-bold py-2 rounded text-sm transition">
              {routeBusy ? 'CALCULATING...' : 'CALCULATE SAFE ROUTE'}
            </button>
            <button onClick={() => switchMode(routingMode)} title="Clear both points and the routes" className="px-3 text-xs border border-slate-600 rounded text-muted-foreground hover:text-foreground hover:bg-secondary transition">
              Clear
            </button>
          </div>
          {routeErr && <div className="text-red-400 text-xs mb-3">{routeErr}</div>}

          {routeRes && (
            <div className="bg-secondary/50 p-3 rounded-lg text-xs">
              <div className="grid grid-cols-[1fr_auto_auto] gap-x-3 gap-y-1.5 items-center">
                <div />
                <div className="font-bold text-orange-400 flex items-center gap-1.5"><svg width="18" height="6"><line x1="0" y1="3" x2="18" y2="3" stroke="#ea580c" strokeWidth="4" strokeDasharray="5 3" /></svg>Normal</div>
                <div className="font-bold text-green-400 flex items-center gap-1.5"><span className="inline-block w-[18px] h-1 rounded-full bg-green-500" />Safe</div>

                <div className="text-muted-foreground">Distance</div>
                <div className="font-mono text-foreground text-right">{fmtKm(routeRes.normal?.lengthM)}</div>
                <div className="font-mono text-foreground text-right">{fmtKm(routeRes.safe?.lengthM)}</div>

                <div className="text-muted-foreground">Est. time</div>
                <div className="font-mono text-foreground text-right">{fmtMin(routeRes.normal?.etaMin)}</div>
                <div className="font-mono text-foreground text-right">{fmtMin(routeRes.safe?.etaMin)}</div>

                <div className="text-muted-foreground">Flooded stretch</div>
                <div className={`font-mono text-right ${(routeRes.normal?.floodedLengthM ?? 0) > 0 ? 'text-red-400 font-bold' : 'text-foreground'}`}>{Math.round(routeRes.normal?.floodedLengthM ?? 0)} m</div>
                <div className={`font-mono text-right ${(routeRes.safe?.floodedLengthM ?? 0) > 0 ? 'text-red-400 font-bold' : 'text-foreground'}`}>{Math.round(routeRes.safe?.floodedLengthM ?? 0)} m</div>
              </div>

              <div className="border-t border-slate-700 mt-3 pt-2 flex justify-between">
                <span className="text-muted-foreground">Safe route detour</span>
                <span className="font-mono text-foreground font-bold">
                  {sameRoute ? 'none (same route)' : `+${Math.round(routeRes.extraM ?? 0)} m, +${(routeRes.extraEtaMin ?? 0).toFixed(1)} min`}
                </span>
              </div>
              <div className={`mt-2 font-semibold ${routeRes.unavoidableFlood ? 'text-red-400' : routeRes.normalRouteFlooded ? 'text-amber-400' : 'text-green-400'}`}>
                {routeRes.unavoidableFlood ? 'FLOODED ON EVERY ROUTE' : routeRes.normalRouteFlooded ? 'NORMAL ROUTE FLOODED: USE THE SAFE ROUTE' : 'PASSABLE'}
              </div>
              {routeRes.message && <div className="text-muted-foreground mt-1">{routeRes.message}</div>}
              <div className="text-[10px] text-muted-foreground mt-2">Normal = shortest street path, ignoring floods. Safe = avoids flooded and blocked nodes. Times are estimates.</div>
            </div>
          )}
        </div>
        )}

        {/* Blocked nodes: release them without hunting for the dot on the map */}
        {activeWidgets.blocked && (
        <div className="bg-card/95 backdrop-blur-md p-4 rounded-xl border border-border pointer-events-auto">
          <div className="flex justify-between items-center mb-3">
            <h3 className="text-xs font-bold text-muted-foreground uppercase">Blocked Nodes</h3>
            <span className="bg-purple-500/20 text-purple-300 text-xs px-2 py-0.5 rounded-full font-bold">{blockedNodes.length} blocked</span>
          </div>
          {blockedNodes.length === 0 && <div className="text-xs text-muted-foreground">No nodes are blocked. Routes use every street.</div>}
          <div className="space-y-2 max-h-[45vh] overflow-y-auto custom-scrollbar pr-1">
            {blockedNodes.map(n => {
              const bi = blockMap.get(n.id);
              return (
                <div key={n.id} className="bg-secondary/50 p-2.5 rounded border border-slate-700/50 text-xs">
                  <div className="flex justify-between items-start gap-2">
                    <div className="min-w-0">
                      <div className="font-mono font-bold text-foreground text-sm">{n.id}</div>
                      <div className="text-muted-foreground truncate" title={n.location}>{n.location || 'Unnamed street'}</div>
                    </div>
                    <span className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded font-bold ${(bi?.source ?? n.blockSource) === 'report' ? 'bg-teal-500/20 text-teal-300' : 'bg-purple-500/20 text-purple-300'}`}>
                      {(bi?.source ?? n.blockSource) === 'report' ? `Report ${bi?.reportRef ?? ''}`.trim() : 'Manual'}
                    </span>
                  </div>
                  {bi && <div className="text-[10px] text-muted-foreground mt-1">by {bi.createdBy}, {format(new Date(bi.createdAt), 'dd MMM HH:mm')}</div>}
                  {bi?.note && <div className="text-[11px] text-foreground mt-1 break-words">{bi.note}</div>}
                  <div className="flex gap-2 mt-2">
                    <button onClick={() => { setSelectedNodeId(n.id); setFocusReq({ coords: n.coordinates, tick: Date.now() }); }}
                      className="flex-1 border border-slate-600 text-muted-foreground hover:text-foreground hover:bg-secondary rounded py-1 font-semibold transition-colors">
                      Show on map
                    </button>
                    <button disabled={unblocking === n.id} onClick={() => releaseBlocked(n.id, bi?.reportRef)}
                      className="flex-1 bg-purple-700 hover:bg-purple-800 disabled:opacity-60 text-white rounded py-1 font-bold transition-colors">
                      {unblocking === n.id ? 'Releasing...' : 'Unblock'}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="text-[10px] text-muted-foreground mt-3">Routes avoid blocked nodes. Releasing a block that came from a citizen report marks that report Resolved.</div>
        </div>
        )}

        {/* Rainfall Simulation */}
        {activeWidgets.rainfall && (
        <div className="bg-card/95 backdrop-blur-md p-4 rounded-xl border border-border pointer-events-auto">
          <h3 className="text-xs font-bold text-muted-foreground mb-3 uppercase">Rainfall Simulation</h3>
          <input 
            type="range" 
            min="0" max="150" 
            value={rainfall} 
            onChange={(e) => setRainfall(Number(e.target.value))}
            className="w-full mb-2 accent-teal-500"
          />
          <div className="flex justify-between text-xs text-muted-foreground font-mono">
            <span>0</span>
            <span className="text-foreground font-bold">{rainfall} mm/hr</span>
            <span>150</span>
          </div>
          <div className="flex gap-2 mt-4">
            <button disabled={resetting} onClick={() => doReset(false)} className="flex-1 flex items-center justify-center gap-1.5 bg-secondary hover:bg-teal-600 hover:text-white disabled:opacity-60 text-foreground text-xs font-bold py-2 rounded border border-border transition">
              <RotateCcw size={14} /> Reset simulation
            </button>
            <button disabled={resetting} onClick={() => doReset(true)} title="Also release every blocked node" className="px-2 text-[10px] text-muted-foreground hover:text-destructive border border-border rounded transition">
              + clear blocks
            </button>
          </div>
        </div>
        )}

        {/* 0-3hr Nowcasting Interactive */}
        {activeWidgets.nowcasting && (
        <div className="bg-card/95 backdrop-blur-md p-4 rounded-xl border border-border pointer-events-auto">
          <h3 className="text-xs font-bold text-muted-foreground mb-3 uppercase">Nowcasting</h3>
          
          <input 
            type="range" 
            min="0" max="3" step="1"
            value={forecastHour} 
            onChange={(e) => setForecastHour(Number(e.target.value))}
            className="w-full mb-2 accent-teal-500"
          />
          <div className="flex justify-between text-xs text-muted-foreground font-mono mb-4">
            <span className={forecastHour === 0 ? "text-teal-400 font-bold" : ""}>Now</span>
            <span className={forecastHour === 1 ? "text-teal-400 font-bold" : ""}>+1h</span>
            <span className={forecastHour === 2 ? "text-teal-400 font-bold" : ""}>+2h</span>
            <span className={forecastHour === 3 ? "text-teal-400 font-bold" : ""}>+3h</span>
          </div>

        </div>
        )}

        {/* Predicted Impact (Separated) */}
        {activeWidgets.impact && (
        <div className="bg-card/95 backdrop-blur-md p-4 rounded-xl border border-border pointer-events-auto shadow-[0_0_15px_rgba(20,184,166,0.1)]">
          <h3 className="text-xs font-bold text-muted-foreground mb-2 uppercase">Predicted Impact</h3>
          <div className="flex items-center justify-between mb-1">
            <div className="text-2xl font-bold text-foreground"><span className="text-red-500">{criticalCount + highCount}</span> / {nodes.length}</div>
            <div className="text-xs font-bold text-orange-400 bg-orange-400/10 px-2 py-1 rounded">AT RISK</div>
          </div>
          <div className="text-[10px] text-muted-foreground">
            {forecastHour === 0
              ? <>Based on <strong className="text-teal-400">current conditions</strong> (live model state).</>
              : <>Based on the model forecast <strong className="text-teal-400">{forecastHour} h from now</strong>.</>}
          </div>
          <div className="text-[10px] text-muted-foreground mt-1">At risk = nodes with High or Critical flood level.</div>
        </div>
        )}

        {/* Active Alerts */}
        {activeWidgets.alerts && (
        <div className="bg-card/95 backdrop-blur-md p-4 rounded-xl border border-border pointer-events-auto">
          <h3 className="text-xs font-bold text-muted-foreground mb-2 uppercase">Active Alerts</h3>
          <div className="flex gap-4 mb-2">
            <div className="text-orange-500 font-bold">{highCount} High</div>
            <div className="text-red-500 font-bold">{criticalCount} Critical</div>
          </div>
          <div className="text-xs text-muted-foreground">Thresholds: {rainfall > 50 ? 'Exceeded' : 'Normal'}</div>
        </div>
        )}

        {/* Node Inspector */}
        {activeWidgets.inspector && (
        <div className="bg-card/95 backdrop-blur-md p-5 rounded-xl border border-border pointer-events-auto">
          <h3 className="text-xs font-bold text-muted-foreground mb-3 uppercase tracking-wider">Node Hydrological Inspector</h3>
          {!selectedNode && <div className="text-xs text-muted-foreground mb-3">Click a node on the map to inspect it.</div>}
          <div className="flex justify-between items-start mb-4">
            <div>
              <div className="text-2xl font-bold text-foreground font-mono">{selectedNode?.id || 'N_XXXX'}</div>
              <div className="flex gap-2 mt-1 text-xs font-bold">
                <span className={`px-2 py-0.5 rounded ${selectedNode?.risk === 'Safe' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>{selectedNode?.risk.toUpperCase()}</span>
                <span className={`px-2 py-0.5 rounded ${selectedNode?.status === 'PASSABLE' ? 'bg-blue-500/20 text-blue-400' : 'bg-orange-500/20 text-orange-400'}`}>{selectedNode?.status}</span>
              </div>
            </div>
            <div className="text-right">
              <div className="text-2xl font-bold text-foreground font-mono">{selectedNode?.depth.toFixed(2)}</div>
              <div className="text-xs text-muted-foreground">Current Depth (m)</div>
            </div>
          </div>
          
          <div className="grid grid-cols-2 gap-4 mb-4 text-sm border-t border-slate-700 pt-4">
            <div>
              <div className="text-muted-foreground text-xs uppercase">Street</div>
              <div className="text-foreground">{selectedNode?.location}</div>
            </div>
            <div>
              <div className="text-muted-foreground text-xs uppercase">Ward</div>
              <div className="text-foreground">T. Nagar</div>
            </div>
            <div>
              <div className="text-muted-foreground text-xs uppercase">Elevation</div>
              <div className="text-foreground">{selectedNode?.elevation} m</div>
            </div>
            <div>
              <div className="text-muted-foreground text-xs uppercase">Imperviousness</div>
              <div className="text-foreground">{selectedNode?.imperviousness}%</div>
            </div>
          </div>
        </div>
        )}

        {/* Graphical Analysis */}
        {activeWidgets.graph && (
        <div className="bg-card/95 backdrop-blur-md p-4 rounded-xl border border-border pointer-events-auto">
          <h3 className="text-xs font-bold text-muted-foreground mb-3 uppercase">Graphical Analysis</h3>
          <div className="text-xs text-muted-foreground mb-2">Deepest street flooding anywhere in the network (m): now and forecast</div>
          <div className="h-36 w-full">
            {!ov ? <div className="text-xs text-muted-foreground">Loading...</div> : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart margin={{ top: 14, right: 4, left: 4, bottom: 0 }} data={[
                  { time: 'Now', level: ov.maxFloodM },
                  ...(ov.forecast ?? []).map((f: any) => ({ time: `+${f.hours}h`, level: f.maxFloodM })),
                ]}>
                  <XAxis dataKey="time" stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} />
                  <YAxis hide domain={[0, (m: number) => Math.max(0.5, m * 1.25)]} />
                  <RechartsTooltip cursor={{fill: '#334155'}} contentStyle={{backgroundColor: '#1e293b', border: 'none', borderRadius: '4px', fontSize: '12px', color: '#fff'}} />
                  <Bar dataKey="level" fill="#14b8a6" radius={[2, 2, 0, 0]}>
                    <LabelList dataKey="level" position="top" fontSize={10} fill="#94a3b8" />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
          <div className="text-[10px] text-muted-foreground mt-2">Live model output. Forecast bars are less certain the further ahead they are.</div>
        </div>
        )}

        {/* Quick Citizen Reports */}
        {activeWidgets.reports && (
        <div className="bg-card/95 backdrop-blur-md p-4 rounded-xl border border-border pointer-events-auto">
          <div className="flex justify-between items-center mb-3">
             <h3 className="text-xs font-bold text-muted-foreground uppercase">Citizen Report Management</h3>
             <span className="bg-red-500/20 text-red-400 text-xs px-2 py-0.5 rounded-full font-bold">{reports.filter(r => r.status === 'PENDING').length} Pending</span>
          </div>
          <div className="space-y-2">
            {reports.slice(0, 2).map(r => (
              <div key={r.id} className="bg-secondary/50 p-2 rounded border border-slate-700/50 text-sm flex justify-between items-center">
                <span className="text-slate-300 truncate w-32">{r.location}</span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${r.status === 'PENDING' ? 'bg-orange-500/20 text-orange-400' : r.status === 'REJECTED' ? 'bg-red-500/20 text-red-400' : 'bg-green-500/20 text-green-400'}`}>{r.status}</span>
              </div>
            ))}
          </div>
        </div>
        )}

      </div>
    </div>
  );
}
