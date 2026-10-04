import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Lock, Shield, ArrowLeft } from 'lucide-react';
import BrandLogo from '../components/BrandLogo';
import { usePravaha } from '../context/PravahaContext';

export default function Login() {
  const [id, setId] = useState('');
  const [pwd, setPwd] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const { login } = usePravaha();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(id.trim(), pwd);
      navigate('/admin/dashboard');
    } catch (err: any) {
      setError(err?.status === 401 ? 'Wrong Municipality ID or password' : (err?.message ?? 'Cannot reach the server'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-900 flex flex-col items-center justify-center relative overflow-hidden">
      {/* Background image mockup with a dark overlay */}
      <div 
        className="absolute inset-0 z-0 bg-cover bg-center bg-no-repeat opacity-90" 
        style={{ backgroundImage: 'url("/login-bg.jpg")' }} 
      />
      
      <Link to="/" aria-label="Back to home" title="Back to home" className="absolute top-6 left-6 z-20 w-10 h-10 flex items-center justify-center text-slate-200 bg-slate-900/50 hover:bg-slate-900/80 backdrop-blur-md border border-slate-600 rounded-full transition-colors">
        <ArrowLeft size={18} />
      </Link>

      <div className="z-10 bg-slate-900/40 backdrop-blur-xl border border-slate-700 p-8 rounded-2xl shadow-2xl w-full max-w-md">
        <div className="flex flex-col items-center mb-8">
          <div className="flex items-center gap-2 text-slate-200 mb-2">
            <BrandLogo className="w-9 h-9" />
            <span className="font-bold text-lg tracking-wide">MeghSync</span>
          </div>
          <h2 className="text-2xl font-semibold text-white">Official Portal Access</h2>
        </div>

        <form onSubmit={handleLogin} className="space-y-4">
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <Lock className="h-5 w-5 text-slate-400" />
            </div>
            <input
              type="text"
              placeholder="Municipality ID"
              className="w-full bg-slate-900/50 border border-slate-600 text-slate-200 rounded-lg pl-10 pr-4 py-3 focus:outline-none focus:border-teal-500 transition"
              value={id}
              onChange={(e) => setId(e.target.value)}
              required
            />
          </div>
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <Shield className="h-5 w-5 text-slate-400" />
            </div>
            <input
              type="password"
              placeholder="Password"
              className="w-full bg-slate-900/50 border border-slate-600 text-slate-200 rounded-lg pl-10 pr-4 py-3 focus:outline-none focus:border-teal-500 transition"
              value={pwd}
              onChange={(e) => setPwd(e.target.value)}
              required
            />
          </div>
          
          {error && <div className="text-red-400 text-sm text-center">{error}</div>}
          <button type="submit" disabled={busy} className="w-full bg-slate-200 hover:bg-white disabled:opacity-60 text-slate-900 font-bold py-3 rounded-lg shadow-lg mt-6 transition transform active:scale-95">
            {busy ? 'Signing in...' : 'Login'}
          </button>
        </form>
        
        <p className="text-slate-400 text-xs text-center mt-6">
          Authorised municipal officials only. All actions are logged.
        </p>
      </div>
    </div>
  );
}
