import React, { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Outlet, Link, useLocation, Navigate } from 'react-router-dom';
import { PravahaProvider, usePravaha } from './context/PravahaContext';
import { Activity, Menu, Map as MapIcon, ShieldAlert, Navigation, Clock } from 'lucide-react';
import { format } from 'date-fns';

import Home from './pages/Home';
import CitizenRouting from './pages/CitizenRouting';
import CitizenReport from './pages/CitizenReport';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Nodes from './pages/Nodes';
import Reports from './pages/Reports';
import Logs from './pages/Logs';
import PrivacyPolicy from './pages/PrivacyPolicy';
import TermsOfService from './pages/TermsOfService';
import CountBadge from './components/CountBadge';
import BrandLogo from './components/BrandLogo';

const LayoutPublic = () => {
  const [currentTime, setCurrentTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="min-h-screen flex flex-col font-sans">
      <header className="bg-white/80 backdrop-blur-md border-b border-slate-200 px-6 py-4 flex justify-between items-center fixed w-full z-50">
        <Link to="/" className="flex items-center gap-3 hover:opacity-80 transition-opacity">
          <BrandLogo className="w-10 h-10" />
          <div className="flex flex-col">
            <span className="font-bold text-lg text-slate-800 leading-none">MeghSync</span>
            <div className="flex items-center gap-1.5 text-slate-500 font-medium mt-1 bg-slate-100/50 px-2 py-0.5 rounded-md border border-slate-200 shadow-sm w-fit">
              <Clock className="w-3 h-3 text-teal-600" />
              <span className="text-[10px] tracking-wide">{format(currentTime, 'EEEE, MMM do, yyyy | hh:mm:ss a')}</span>
            </div>
          </div>
        </Link>
        <nav className="flex items-center gap-6">
          <Link to="/" className="text-slate-600 hover:text-teal-600 text-sm font-medium">Home</Link>
          <Link to="/routing" className="text-slate-600 hover:text-teal-600 text-sm font-medium">Safe Routes</Link>
          <Link to="/report" className="text-slate-600 hover:text-teal-600 text-sm font-medium">Report Flood</Link>
          <Link to="/login" className="bg-teal-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-teal-700 transition">Municipality Login</Link>
        </nav>
      </header>
      <main className="flex-1 pt-20">
        <Outlet />
      </main>
    </div>
  );
};

const LayoutAdmin = () => {
  const [menuOpen, setMenuOpen] = React.useState(false);
  
  useEffect(() => {
    document.body.classList.add('dark');
    return () => document.body.classList.remove('dark');
  }, []);

  const location = useLocation();
  const { isAuthenticated, logout, reports } = usePravaha();
  const pendingReports = reports.filter(r => r.status === 'PENDING').length;

  if (!isAuthenticated) return <Navigate to="/login" replace />;

  return (
    <div className="min-h-screen flex flex-col font-sans bg-background text-foreground h-screen overflow-hidden">
      <header className="bg-card border-b border-border px-4 py-3 flex justify-between items-center z-50 shrink-0">
        <Link to="/admin/dashboard" className="flex items-center gap-2 hover:opacity-80 transition-opacity" title="Go to Overview">
          <BrandLogo className="w-8 h-8" />
          <div>
             <div className="font-bold text-sm tracking-wide text-foreground">MeghSync</div>
             <div className="text-[10px] text-muted-foreground uppercase tracking-widest">Command Center</div>
          </div>
        </Link>
        <nav className="hidden md:flex items-center gap-6">
          <Link to="/admin/dashboard" className={`text-sm ${location.pathname === '/admin/dashboard' ? 'text-teal-400' : 'text-muted-foreground hover:text-foreground'}`}>Overview</Link>
          <Link to="/admin/nodes" className={`text-sm ${location.pathname === '/admin/nodes' ? 'text-teal-400' : 'text-muted-foreground hover:text-foreground'}`}>Node List</Link>
          <Link to="/admin/reports" className={`text-sm inline-flex items-center gap-1.5 ${location.pathname === '/admin/reports' ? 'text-teal-400' : 'text-muted-foreground hover:text-foreground'}`}>Reports <CountBadge count={pendingReports} /></Link>
          <Link to="/admin/logs" className={`text-sm ${location.pathname === '/admin/logs' ? 'text-teal-400' : 'text-muted-foreground hover:text-foreground'}`}>Logs</Link>
        </nav>
        <div className="flex items-center gap-4 relative">
          <div className="flex items-center gap-2">
             <div className="w-2 h-2 rounded-full bg-green-500"></div>
             <span className="text-xs text-green-500 font-medium hidden sm:inline">SYSTEM OPERATIONAL</span>
          </div>
          <button 
            className="relative text-muted-foreground hover:text-foreground p-1 transition-colors"
            onClick={() => setMenuOpen(!menuOpen)}
          >
            <Menu className="w-6 h-6"/>
            <CountBadge count={pendingReports} className="absolute -top-1 -right-1" />
          </button>
          
          {menuOpen && (
            <div className="absolute top-12 right-0 bg-popover border border-border rounded-lg shadow-2xl p-2 flex flex-col gap-1 z-50 w-48">
              <Link onClick={() => setMenuOpen(false)} to="/admin/dashboard" className="px-4 py-2 hover:bg-secondary rounded text-sm text-popover-foreground">Overview</Link>
              <Link onClick={() => setMenuOpen(false)} to="/admin/nodes" className="px-4 py-2 hover:bg-secondary rounded text-sm text-popover-foreground">Node List</Link>
              <Link onClick={() => setMenuOpen(false)} to="/admin/reports" className="px-4 py-2 hover:bg-secondary rounded text-sm text-popover-foreground flex items-center justify-between">Reports <CountBadge count={pendingReports} /></Link>
              <Link onClick={() => setMenuOpen(false)} to="/admin/logs" className="px-4 py-2 hover:bg-secondary rounded text-sm text-popover-foreground">Logs</Link>
              <hr className="border-border my-1" />
              <Link onClick={() => { setMenuOpen(false); logout(); }} to="/" className="px-4 py-2 hover:bg-destructive/20 hover:text-destructive rounded text-sm text-muted-foreground">Logout</Link>
            </div>
          )}
        </div>
      </header>
      <main className="flex-1 relative overflow-hidden flex bg-background">
        <Outlet />
      </main>
    </div>
  );
};

export default function App() {
  return (
    <PravahaProvider>
      <BrowserRouter>
        <Routes>
          {/* Public Routes */}
          <Route element={<LayoutPublic />}>
            <Route path="/" element={<Home />} />
            <Route path="/routing" element={<CitizenRouting />} />
            <Route path="/report" element={<CitizenReport />} />
            <Route path="/privacy" element={<PrivacyPolicy />} />
            <Route path="/terms" element={<TermsOfService />} />
          </Route>
          
          <Route path="/login" element={<Login />} />

          {/* Admin Routes */}
          <Route element={<LayoutAdmin />}>
            <Route path="/admin/dashboard" element={<Dashboard />} />
            <Route path="/admin/nodes" element={<Nodes />} />
            <Route path="/admin/reports" element={<Reports />} />
            <Route path="/admin/logs" element={<Logs />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </PravahaProvider>
  );
}
