import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { ShieldAlert, Navigation, Layers } from 'lucide-react';
import BrandLogo from '../components/BrandLogo';
import LegalModal from '../components/LegalModal';
import { PRIVACY, TERMS } from '../lib/legal';
import { MapContainer, TileLayer, CircleMarker, Popup, ZoomControl } from 'react-leaflet';
import { usePravaha } from '../context/PravahaContext';
import 'leaflet/dist/leaflet.css';

export default function Home() {
  const [legal, setLegal] = useState<'privacy' | 'terms' | null>(null);
  const [forecastHour, setForecastHour] = useState(0);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [mapStyle, setMapStyle] = useState<'dark' | 'light'>('dark');
  const { nodes } = usePravaha();
  const liveNodes = nodes.map(n => ({
    id: n.id, lat: n.coordinates[0], lng: n.coordinates[1], name: n.location, level: `${n.depth.toFixed(2)}m`,
    blocked: !!n.blocked,
    status: n.risk === 'Critical' || n.risk === 'High' ? 'danger' : n.risk === 'Moderate' ? 'warning' : 'safe',
  }));
  return (
    <div className="min-h-[calc(100vh-4rem)] w-full bg-slate-50 flex flex-col px-4 py-6 md:px-8 md:py-8 gap-8 max-w-7xl mx-auto">
      
      {/* Hero Block with Storm Background */}
      <div 
        className="relative w-full flex-1 min-h-[400px] flex flex-col md:flex-row items-center gap-8 rounded-[2rem] overflow-hidden shadow-2xl p-8 md:p-12 lg:p-16 bg-cover bg-center border border-slate-200/50"
        style={{ backgroundImage: 'url("/hero-bg.jpg")' }}
      >
        {/* Dark overlay for readability */}
        <div className="absolute inset-0 bg-slate-900/50 z-0"></div>
        
        <div className="flex-1 relative z-10 flex flex-col justify-center h-full py-4">
          <h1 className="text-2xl md:text-4xl font-extrabold text-white mb-4 leading-tight drop-shadow-lg">
            Urban Flood <br/><span className="text-teal-400">Intelligence</span> System
          </h1>
          <p className="text-sm md:text-base text-slate-200 mb-6 max-w-lg drop-shadow-md leading-relaxed">
            Real-time flood prediction, safe routing, and citizen reporting for a safer, more resilient T. Nagar.
          </p>
          <div className="flex flex-wrap items-center gap-3">
             <Link to="/routing" className="bg-teal-500 hover:bg-teal-400 text-white px-4 py-2 rounded-lg text-sm font-bold shadow-lg shadow-teal-500/30 transition transform hover:-translate-y-1">Find Safe Route</Link>
             <Link to="/report" className="bg-white/10 hover:bg-white/20 backdrop-blur-md text-white border border-white/30 px-4 py-2 rounded-lg text-sm font-bold shadow-sm transition transform hover:-translate-y-1">Report Flooding</Link>
          </div>
        </div>
        
        <div className="flex-1 relative w-full h-full z-10 hidden md:flex items-center justify-center">
          {/* Live Mini Map Mockup */}
          <div className="w-full max-w-[450px] h-[250px] bg-slate-800 rounded-2xl overflow-hidden shadow-2xl relative border-4 border-white/20">
              <MapContainer 
                center={[13.0418, 80.2341]} 
                zoom={14} 
                className="w-full h-full z-0"
                zoomControl={false}
                attributionControl={false}
              >
                <ZoomControl position="bottomright" />
                <TileLayer key={mapStyle} url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" className={mapStyle === 'dark' ? 'dark-tiles' : ''} />
                {liveNodes.map(node => (
                  <CircleMarker 
                    key={node.id}
                    center={[node.lat, node.lng]}
                    radius={selectedNodeId === node.id ? 6 : 3}
                    eventHandlers={{
                      click: () => setSelectedNodeId(node.id === selectedNodeId ? null : node.id)
                    }}
                    pathOptions={{ 
                      fillColor: node.blocked ? '#a855f7' : node.status === 'danger' ? '#ef4444' : node.status === 'warning' ? '#f59e0b' : '#10b981',
                      color: selectedNodeId === node.id ? '#ffffff' : 'white',
                      weight: selectedNodeId === node.id ? 3 : 1,
                      fillOpacity: selectedNodeId === node.id ? 1 : 0.8
                    }}
                    className="cursor-pointer transition-all duration-300"
                  >
                    <Popup>
                      <div className="text-xs font-bold text-slate-800">{node.name}</div>
                      <div className="text-xs text-slate-600">Water Level: {node.level}</div>
                      <div className="text-[10px] font-bold mt-1 px-2 py-0.5 rounded bg-slate-100 text-slate-700 w-fit">
                        {node.status.toUpperCase()}
                      </div>
                    </Popup>
                  </CircleMarker>
                ))}
              </MapContainer>
             <button
               type="button"
               title={mapStyle === 'dark' ? 'Switch to light map' : 'Switch to dark map'}
               onClick={() => setMapStyle(mapStyle === 'dark' ? 'light' : 'dark')}
               className="absolute top-3 right-3 z-10 bg-white/90 hover:bg-white text-slate-700 p-1.5 rounded shadow border border-white/40"
             >
               <Layers className="w-4 h-4" />
             </button>
             <div className="absolute top-3 left-3 z-10 bg-black/60 backdrop-blur-md text-white px-3 py-1 rounded text-xs font-bold shadow border border-white/10 flex items-center gap-2">
               <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></span>
               Live T. Nagar Grid
             </div>
          </div>
        </div>
      </div>

      {/* Cards Block */}
      <div className="w-full shrink-0 flex flex-col items-center mb-6 mt-8">
        <h2 className="text-2xl font-bold text-slate-800 tracking-tight">System Capabilities</h2>
        <div className="w-12 h-1 bg-teal-500 rounded-full mt-3 mb-2"></div>
        <p className="text-slate-500 text-sm">Core features powering the MeghSync</p>
      </div>
      <div className="grid md:grid-cols-3 gap-6 shrink-0 w-full">
        <div className="bg-white rounded-2xl shadow-md border border-slate-200 hover:shadow-xl transition-all duration-300 overflow-hidden group flex flex-col">
          <div className="w-full h-32 overflow-hidden shrink-0 relative">
            <div className="absolute inset-0 bg-slate-900/10 group-hover:bg-transparent transition z-10"></div>
            <img src="/prediction.jpg" alt="Live Prediction Dashboard" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700" />
          </div>
          <div className="p-4 flex flex-col flex-1">
            <div className="flex items-center gap-3 mb-2">
              <img src="/prediction-icon.png" alt="" className="w-9 h-9 rounded-full shrink-0 shadow-sm" />
              <h3 className="text-base font-bold text-slate-800">Live Prediction</h3>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">Advanced ML models predicting water levels up to 3 hours ahead across 662 drainage nodes.</p>
          </div>
        </div>
        
        <div className="bg-white rounded-2xl shadow-md border border-slate-200 hover:shadow-xl transition-all duration-300 overflow-hidden group flex flex-col">
          <div className="w-full h-32 overflow-hidden shrink-0 relative">
            <div className="absolute inset-0 bg-slate-900/10 group-hover:bg-transparent transition z-10"></div>
            <img src="/routing.jpg" alt="Safe Routing Map" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700" />
          </div>
          <div className="p-4 flex flex-col flex-1">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-8 h-8 bg-teal-50 text-teal-600 rounded-lg flex items-center justify-center shrink-0 shadow-sm">
                <Navigation className="w-4 h-4" />
              </div>
              <h3 className="text-base font-bold text-slate-800">Safe Routing</h3>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">Dynamic A* pathfinding avoiding flooded streets, keeping citizens and emergency vehicles safe.</p>
          </div>
        </div>

        <div className="bg-white rounded-2xl shadow-md border border-slate-200 hover:shadow-xl transition-all duration-300 overflow-hidden group flex flex-col">
          <div className="w-full h-32 overflow-hidden shrink-0 relative">
            <div className="absolute inset-0 bg-slate-900/10 group-hover:bg-transparent transition z-10"></div>
            <img src="/alerts.jpg" alt="Instant Alerts Interface" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700" />
          </div>
          <div className="p-4 flex flex-col flex-1">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-8 h-8 bg-orange-50 text-orange-600 rounded-lg flex items-center justify-center shrink-0 shadow-sm">
                <ShieldAlert className="w-4 h-4" />
              </div>
              <h3 className="text-base font-bold text-slate-800">Instant Reports</h3>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">Real-time alerts triggered by critical water levels and verified citizen reports.</p>
          </div>
        </div>
      </div>



      {/* Footer Block */}
      <footer className="w-full bg-slate-900 rounded-[2rem] mt-4 overflow-hidden border border-slate-800 shadow-xl shrink-0">
        <div className="px-8 py-10 flex flex-col md:flex-row justify-between gap-10">
          <div className="flex-1 max-w-xs">
            <div className="flex items-center gap-2 mb-4">
              <BrandLogo className="w-8 h-8" />
              <span className="font-bold text-lg text-white tracking-wide">MeghSync</span>
            </div>
            <p className="text-sm text-slate-400 leading-relaxed mb-6">
              Empowering the T. Nagar community with predictive intelligence and real-time safe routing to minimize the impact of urban flooding.
            </p>
          </div>

          <div className="flex gap-12 md:gap-20">
            <div>
              <h4 className="text-white font-bold text-sm mb-4 tracking-wider">QUICK LINKS</h4>
              <ul className="space-y-3 text-sm text-slate-400">
                <li><Link to="/routing" className="hover:text-teal-400 transition-colors">Safe Route</Link></li>
                <li><Link to="/report" className="hover:text-teal-400 transition-colors">Report Flooding</Link></li>
                <li><Link to="/login" className="hover:text-teal-400 transition-colors">Municipality Login</Link></li>
              </ul>
            </div>
            
            <div>
              <h4 className="text-white font-bold text-sm mb-4 tracking-wider">EMERGENCY CONTACTS</h4>
              <ul className="space-y-3 text-sm text-slate-400">
                <li><span className="text-teal-400 font-semibold mr-2">1070</span> State Control Room</li>
                <li><span className="text-teal-400 font-semibold mr-2">1913</span> GCC Helpline</li>
                <li><span className="text-teal-400 font-semibold mr-2">101</span> Fire & Rescue</li>
              </ul>
            </div>
          </div>
        </div>
        
        <div className="border-t border-slate-800 bg-black/20 px-8 py-4 flex flex-col md:flex-row justify-between items-center gap-4 text-xs text-slate-500">
          <div>&copy; {new Date().getFullYear()} MeghSync Initiative. All rights reserved.</div>
          <div className="flex gap-4">
            <button type="button" onClick={() => setLegal('privacy')} className="hover:text-white transition-colors">Privacy Policy</button>
            <button type="button" onClick={() => setLegal('terms')} className="hover:text-white transition-colors">Terms of Service</button>
          </div>
        </div>
      </footer>
      {legal && <LegalModal doc={legal === 'privacy' ? PRIVACY : TERMS} onClose={() => setLegal(null)} />}
    </div>
  );
}
