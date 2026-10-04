import React, { useEffect, useRef, useState } from 'react';
import { usePravaha } from '../context/PravahaContext';
import { MapContainer, TileLayer, CircleMarker, ZoomControl, useMap, useMapEvents } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';

type LatLng = [number, number];

// One click drops the pin. A double click only zooms (the pin waits briefly so a double click does not move it).
function PinPicker({ onPick }: { onPick: (p: LatLng) => void }) {
  const timer = useRef<number | undefined>(undefined);
  useMapEvents({
    click: (e) => {
      const p: LatLng = [e.latlng.lat, e.latlng.lng];
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => onPick(p), 250);
    },
    dblclick: () => window.clearTimeout(timer.current),
  });
  return null;
}

function Recenter({ pos }: { pos: LatLng | null }) {
  const map = useMap();
  useEffect(() => { if (pos) map.setView(pos, Math.max(map.getZoom(), 16)); }, [pos, map]);
  return null;
}

export default function CitizenReport() {
  const { addReport, reports } = usePravaha();
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [location, setLocation] = useState('');
  const [description, setDescription] = useState('');
  const [submitted, setSubmitted] = useState<{ id: string; status: string; timestamp: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [pin, setPin] = useState<LatLng | null>(null);
  const [recenter, setRecenter] = useState<LatLng | null>(null);

  const dropPin = (p: LatLng) => {
    setPin(p);
    setLocation(prev => prev.trim() ? prev : `Pinned on map (${p[0].toFixed(5)}, ${p[1].toFixed(5)})`);
  };

  const useGps = () => {
    if (!navigator.geolocation) { setError('GPS is not available in this browser.'); return; }
    navigator.geolocation.getCurrentPosition(
      (pos) => { const p: LatLng = [pos.coords.latitude, pos.coords.longitude]; dropPin(p); setRecenter(p); setError(null); },
      () => setError('Could not get your GPS location. Allow location access or click the map instead.')
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = await addReport({ name, phone, location, description, lat: pin?.[0], lon: pin?.[1] });
      setSubmitted(res);
      setName(''); setPhone(''); setLocation(''); setDescription(''); setPin(null);
    } catch (err: any) {
      setError(err?.status === 429 ? 'Too many reports from this device. Please try again later.' : (err?.message ?? 'Could not send the report'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative min-h-[calc(100vh-4rem)] flex items-center justify-center bg-slate-100 overflow-hidden">
      {/* Background image mockup with a light overlay */}
      <div 
        className="absolute inset-0 z-0 bg-cover bg-center bg-no-repeat opacity-80" 
        style={{ backgroundImage: 'url("/report-bg.jpg")' }} 
      />
      
      <div className="z-10 bg-white/60 backdrop-blur-xl border border-white/40 p-8 rounded-3xl shadow-2xl w-full max-w-2xl my-8">
        <h2 className="text-3xl font-bold text-slate-800 text-center mb-8">Public Flood Report</h2>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="grid md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1">Name</label>
              <input type="text" value={name} onChange={e => setName(e.target.value)} required className="w-full bg-white border border-slate-300 rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-teal-500 shadow-sm" placeholder="Rahul" />
            </div>
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1">Phone Number</label>
              <input type="tel" value={phone} onChange={e => setPhone(e.target.value)} required className="w-full bg-white border border-slate-300 rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-teal-500 shadow-sm" placeholder="99XXXXXXXX" />
            </div>
          </div>

          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-1">Location</label>
            <input type="text" value={location} onChange={e => setLocation(e.target.value)} required className="w-full bg-white border border-slate-300 rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-teal-500 shadow-sm" placeholder="T. Nagar, near Node N104" />
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="block text-sm font-semibold text-slate-700">Pin the exact spot (optional)</label>
              <button type="button" onClick={useGps} className="text-xs font-bold text-teal-700 hover:underline">Use my GPS</button>
            </div>
            <div className="w-full h-60 bg-slate-200 rounded-lg border border-slate-300 overflow-hidden relative shadow-sm">
              <MapContainer center={[13.041, 80.231]} zoom={14} className="w-full h-full" zoomControl={false}>
                <ZoomControl position="bottomright" />
                <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" />
                <PinPicker onPick={dropPin} />
                <Recenter pos={recenter} />
                {pin && <CircleMarker center={pin} radius={9} pathOptions={{ color: '#ffffff', weight: 3, fillColor: '#ef4444', fillOpacity: 1 }} />}
              </MapContainer>
            </div>
            <div className="text-xs text-slate-600 mt-1">Drag to move the map. Double-click or use +/- to zoom. Click once to drop the pin.</div>
          </div>

          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-1">Flooding Description</label>
            <textarea value={description} onChange={e => setDescription(e.target.value)} required rows={2} className="w-full bg-white border border-slate-300 rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-teal-500 shadow-sm" placeholder="Water level approximately 1 foot"></textarea>
          </div>

          {error && <div className="text-red-600 text-sm font-medium text-center">{error}</div>}
          <button type="submit" disabled={busy} className="w-full bg-slate-800 hover:bg-slate-700 disabled:opacity-60 text-white font-bold py-3.5 rounded-xl shadow-lg transition text-lg mt-4">
            {busy ? 'Sending...' : 'Submit'}
          </button>
        </form>

        {submitted && (
          <div className="mt-6 bg-white/80 border border-slate-200 p-4 rounded-xl text-sm font-mono text-slate-700 shadow-sm">
            <div>Stored report ID: {submitted.id}</div>
            <div>Timestamp: {submitted.timestamp}</div>
            <div>Stored report status: {submitted.status}</div>
          </div>
        )}
      </div>
    </div>
  );
}
