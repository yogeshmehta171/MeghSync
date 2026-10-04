import React, { useState } from 'react';
import { MapContainer, TileLayer, Polyline, CircleMarker, ZoomControl, useMapEvents } from 'react-leaflet';
import { Layers, Navigation, Activity, Map } from 'lucide-react';
import { usePravaha } from '../context/PravahaContext';
import PlacePicker from '../components/PlacePicker';
import 'leaflet/dist/leaflet.css';

type LatLng = [number, number];

function MapClickPicker({ onPick }: { onPick: (p: LatLng) => void }) {
  useMapEvents({ click: (e) => onPick([e.latlng.lat, e.latlng.lng]) });
  return null;
}

const fmtPoint = (p: LatLng | null) => (p ? `${p[0].toFixed(5)}, ${p[1].toFixed(5)}` : '');

export default function CitizenRouting() {
  const { nodes, meta, error, findRoute } = usePravaha();
  // Data is outdated when the server says so (meta.stale) or when we have lost the server entirely.
  const outdated = !!meta?.stale || (!meta && !!error);
  const lastUpdated = meta?.computedAt ? new Date(meta.computedAt).toLocaleTimeString() : 'unknown';
  const [startText, setStartText] = useState('');
  const [endText, setEndText] = useState('');
  const [startPt, setStart] = useState<LatLng | null>(null);
  const [endPt, setEnd] = useState<LatLng | null>(null);
  const [route, setRoute] = useState<any | null>(null);
  const [routeError, setRouteError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [mapStyle, setMapStyle] = useState<'light' | 'dark'>('light');
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [focusedInput, setFocusedInput] = useState<'start' | 'end'>('start');
  const [activeWidgets, setActiveWidgets] = useState({
    routing: false,
    stats: false,
    legend: false
  });

  const toggleWidget = (widgetName: keyof typeof activeWidgets) => {
    setActiveWidgets(prev => {
      const isCurrentlyOpen = prev[widgetName];
      const newState = { routing: false, stats: false, legend: false };
      newState[widgetName] = !isCurrentlyOpen;
      return newState;
    });
  };

  const getRiskColor = (risk: string) => {
    switch (risk) {
      case 'Critical': return '#ef4444';
      case 'High': return '#f97316';
      case 'Moderate': return '#eab308';
      case 'Low': return '#3b82f6';
      default: return '#22c55e';
    }
  };

  // Clicking the map sets the start first, then the destination (or whichever box is focused).
  const handlePick = (p: LatLng) => {
    if (focusedInput === 'start') { setStart(p); setStartText(fmtPoint(p)); setFocusedInput('end'); }
    else { setEnd(p); setEndText(fmtPoint(p)); }
    setRoute(null);
    setRouteError(null);
  };

  // A point chosen from the list or the map wins; otherwise accept an exact typed place name.
  const resolve = (text: string, point: LatLng | null): LatLng | null => {
    if (point) return point;
    const t = text.trim().toLowerCase();
    const n = t ? nodes.find(x => (x.location || '').trim().toLowerCase() === t) : undefined;
    return n ? n.coordinates : null;
  };

  const locateMe = () => {
    if (!navigator.geolocation) { setRouteError('Location is not available in this browser.'); return; }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const p: LatLng = [pos.coords.latitude, pos.coords.longitude];
        setStart(p); setStartText('My location'); setFocusedInput('end'); setRoute(null); setRouteError(null);
      },
      () => setRouteError('Could not get your location. Allow location access, or pick a place / click the map.')
    );
  };

  const handleFind = async () => {
    const start = resolve(startText, startPt);
    const end = resolve(endText, endPt);
    if (!start || !end) { setRouteError('Choose a start and a destination: type a place name and pick it from the list, or click the map.'); return; }
    setLoading(true);
    setRouteError(null);
    try {
      const r = await findRoute({ lat: start[0], lon: start[1] }, { lat: end[0], lon: end[1] });
      setRoute(r);
      setActiveWidgets({ routing: true, stats: true, legend: false });
    } catch (e: any) {
      setRoute(null);
      setRouteError(e?.message ?? 'Could not calculate a route');
    } finally {
      setLoading(false);
    }
  };

  const normalRoute: LatLng[] = route?.normal?.path ?? [];
  const safeRoute: LatLng[] = route?.safe?.path ?? [];
  const km = (m?: number) => (m == null ? '-' : (m / 1000).toFixed(1) + ' km');

  return (
    <div className="relative w-full h-[calc(100vh-4rem)] bg-slate-100 flex">
      {/* Left Sidebar Widget Toggle Toolbar */}
      <div className="absolute top-4 left-4 z-50 flex flex-col gap-2 bg-white/95 backdrop-blur-md p-2 rounded-xl border border-slate-200 shadow-lg pointer-events-auto w-[42px] items-center">
        <button onClick={() => toggleWidget('routing')} className={`p-2 rounded transition-colors ${activeWidgets.routing ? 'bg-[#1e7c9a] text-white shadow-md' : 'hover:bg-slate-100 text-slate-600 hover:text-slate-900'}`} title="Toggle Routing"><Navigation size={18} /></button>
        <button onClick={() => toggleWidget('stats')} className={`p-2 rounded transition-colors ${activeWidgets.stats ? 'bg-[#1e7c9a] text-white shadow-md' : 'hover:bg-slate-100 text-slate-600 hover:text-slate-900'}`} title="Toggle Trip Stats"><Activity size={18} /></button>
        <button onClick={() => toggleWidget('legend')} className={`p-2 rounded transition-colors ${activeWidgets.legend ? 'bg-[#1e7c9a] text-white shadow-md' : 'hover:bg-slate-100 text-slate-600 hover:text-foreground'}`} title="Toggle Navigation Guide"><Map size={18} /></button>
      </div>

      {/* Sidebar Overlay */}
      <div className="absolute top-4 left-16 z-20 w-80 flex flex-col gap-4 pointer-events-none">
        
        {activeWidgets.routing && (
        <div className="bg-white p-5 rounded-xl shadow-lg border border-slate-200 pointer-events-auto">
          <h2 className="text-sm font-bold text-slate-800 tracking-wider uppercase mb-4">Safe Routes</h2>
          <div className="space-y-3 mb-4 relative">
            <div className="relative">
              <div className={`absolute left-3 top-3 z-10 w-3 h-3 rounded-full transition-colors ${focusedInput === 'start' ? 'bg-teal-500' : 'border-2 border-slate-400'}`}></div>
              <PlacePicker
                variant="light"
                mode="location"
                nodes={nodes}
                value={startText}
                placeholder="Start: type a place, pick, or click the map"
                inputClassName="w-full border border-slate-300 rounded-lg pl-9 pr-3 py-2 text-sm text-slate-800 bg-white focus:outline-none focus:border-teal-500 transition-colors"
                onFocus={() => setFocusedInput('start')}
                onChange={(t) => { setStartText(t); setStart(null); setRoute(null); }}
                onPick={(pk) => { setStartText(pk.text); setStart(pk.coords); setRoute(null); setRouteError(null); }}
              />
            </div>
            <div className="relative">
              <div className={`absolute left-3 top-3 z-10 w-3 h-3 rounded-full transition-colors ${focusedInput === 'end' ? 'bg-teal-500' : 'border-2 border-slate-400'}`}></div>
              <PlacePicker
                variant="light"
                mode="location"
                nodes={nodes}
                value={endText}
                placeholder="Destination: type a place, pick, or click the map"
                inputClassName="w-full border border-slate-300 rounded-lg pl-9 pr-3 py-2 text-sm text-slate-800 bg-white focus:outline-none focus:border-teal-500 transition-colors"
                onFocus={() => setFocusedInput('end')}
                onChange={(t) => { setEndText(t); setEnd(null); setRoute(null); }}
                onPick={(pk) => { setEndText(pk.text); setEnd(pk.coords); setRoute(null); setRouteError(null); }}
              />
            </div>
            <button type="button" onClick={locateMe} className="text-xs text-teal-700 hover:underline">Use my current location as start</button>
          </div>
          <button className="w-full bg-[#1e7c9a] hover:bg-[#166078] text-white font-medium py-2.5 rounded-lg text-sm transition" onClick={handleFind} disabled={loading}>
            {loading ? 'Calculating...' : 'Find Safe Route'}
          </button>
          {routeError && <div className="text-red-600 text-xs mt-2">{routeError}</div>}
          {route?.message && <div className="text-slate-600 text-xs mt-2">{route.message}</div>}
        </div>
        )}

        {activeWidgets.stats && (
        <div className="bg-white p-5 rounded-xl shadow-lg border border-slate-200 pointer-events-auto">
          <h3 className="font-bold text-slate-800 text-sm tracking-wider uppercase mb-3">Route View</h3>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-slate-600 flex items-center gap-2"><span className="inline-block w-3 h-3 rounded-full bg-orange-600"></span>Normal route distance:</span>
              <span className="font-medium">{km(route?.normal?.lengthM)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-600 flex items-center gap-2"><span className="inline-block w-3 h-3 rounded-full bg-green-600"></span>Flood-safe route distance:</span>
              <span className="font-medium">{km(route?.safe?.lengthM)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-600">Additional distance:</span>
              <span className="font-medium">{km(route?.extraM)}</span>
            </div>
          </div>
        </div>
        )}

        {activeWidgets.legend && (
        <div className="bg-white p-5 rounded-xl shadow-lg border border-slate-200 pointer-events-auto">
          <h3 className="font-bold text-slate-800 text-sm tracking-wider uppercase mb-3">Navigation Guide</h3>
          <div className="space-y-2 text-sm">
            <div className="flex items-center gap-3">
              <svg width="28" height="8"><line x1="0" y1="4" x2="28" y2="4" stroke="#ea580c" strokeWidth="6" strokeDasharray="8 4" /></svg>
              <span className="text-slate-700">Normal route (shortest, ignores floods)</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-7 h-1.5 bg-green-600 rounded-full"></div>
              <span className="text-slate-700">Flood-safe route (avoids flooded streets)</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-4 h-4 border-4 border-blue-600 rounded-full bg-white ml-1.5"></div>
              <span className="text-slate-700">Start point</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-4 h-4 border-4 border-red-500 rounded-full bg-white ml-1.5"></div>
              <span className="text-slate-700">Destination</span>
            </div>
            <div className="text-xs text-slate-500 pt-1">Additional distance is the extra length of the safe route, shown in Route View.</div>
          </div>
        </div>
        )}

      </div>

      {/* Map Tools */}
      <div className="absolute top-4 right-4 z-[999] flex flex-col gap-2 pointer-events-auto">
        <button 
          title="Toggle Map Style"
          className="bg-white p-2 rounded shadow border border-slate-200 text-slate-600 hover:text-slate-900 transition-colors active:bg-slate-100 cursor-pointer"
          onClick={() => setMapStyle(mapStyle === 'light' ? 'dark' : 'light')}
        >
          <Layers className="w-5 h-5"/>
        </button>
      </div>

      {/* Outdated Warning */}
      {outdated && (
        <div className="absolute top-0 left-0 w-full z-[100] bg-orange-100/90 border-b border-orange-200 text-orange-800 py-2 text-center text-sm font-medium backdrop-blur-sm shadow-md">
          Flood data is outdated. Last updated: {lastUpdated}. Do not rely on these routes.
        </div>
      )}

      {/* Full Map */}
      <div className="w-full h-full z-0 relative">
        <MapContainer center={[13.044, 80.235]} zoom={15} className="w-full h-full" zoomControl={false}>
          <ZoomControl position="bottomright" />
          <TileLayer
            key={mapStyle}
            url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
            className={mapStyle === 'light' ? '' : 'dark-tiles'}
          />
          <MapClickPicker onPick={handlePick} />
          {/* Normal route: orange dashed, underneath. Flood-safe route: green solid with a white edge, on top. */}
          {normalRoute.length > 1 && <Polyline positions={normalRoute} color="#ea580c" weight={8} opacity={1} dashArray="14, 8" lineCap="butt" />}
          {safeRoute.length > 1 && <Polyline positions={safeRoute} color="#ffffff" weight={10} opacity={0.9} />}
          {safeRoute.length > 1 && <Polyline positions={safeRoute} color="#16a34a" weight={6} />}
          {startPt && <CircleMarker center={startPt} radius={8} pathOptions={{ color: '#2563eb', weight: 4, fillColor: 'white', fillOpacity: 1 }} />}
          {endPt && <CircleMarker center={endPt} radius={8} pathOptions={{ color: '#ef4444', weight: 4, fillColor: 'white', fillOpacity: 1 }} />}
        </MapContainer>
        
        {/* Full screen grey overlay if outdated to simulate fail-safe */}
        {outdated && (
           <div className="absolute inset-0 bg-slate-900/10 z-[5] pointer-events-none transition-opacity duration-300"></div>
        )}
      </div>
    </div>
  );
}
