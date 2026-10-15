import React from 'react';
import { Shield, Eye, Radio, BarChart3, Plus, LogOut, Waves, AlertTriangle } from 'lucide-react';

interface NavbarProps {
  currentTab: string;
  setCurrentTab: (tab: string) => void;
  isLoggedIn: boolean;
  onLogout: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ currentTab, setCurrentTab, isLoggedIn, onLogout }) => {
  return (
    <header className="border-b border-cyan-950/80 bg-slate-950/90 backdrop-blur-md sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand */}
        <div
          className="flex items-center space-x-3 cursor-pointer group"
          onClick={() => setCurrentTab(isLoggedIn ? 'dashboard' : 'login')}
        >
          <div className="bg-cyan-500/10 p-2.5 rounded-lg text-cyan-400 border border-cyan-500/30 group-hover:border-cyan-400/60 transition-colors shadow-[0_0_15px_rgba(6,182,212,0.15)]">
            <Waves className="w-5 h-5 text-cyan-400 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="font-extrabold text-xl tracking-tight text-white font-mono uppercase">
                RIP<span className="text-cyan-400">GUARD</span>
              </span>
              <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-cyan-950/80 text-cyan-300 border border-cyan-800/60 font-semibold tracking-wider">
                TACTICAL OPS
              </span>
            </div>
            <p className="text-[11px] text-slate-400 font-mono tracking-tight">
              CVPR 2025 RipVIS Neural Surveillance Console
            </p>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav className="flex items-center space-x-1 sm:space-x-2">
          {isLoggedIn ? (
            <>
              <button
                onClick={() => setCurrentTab('dashboard')}
                className={`px-3 py-1.5 rounded-lg text-xs font-mono font-medium transition-all flex items-center space-x-1.5 ${
                  currentTab === 'dashboard'
                    ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/40 shadow-[0_0_10px_rgba(6,182,212,0.2)]'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900 border border-transparent'
                }`}
              >
                <Eye className="w-3.5 h-3.5" />
                <span>SURVEILLANCE</span>
              </button>

              <button
                onClick={() => setCurrentTab('upload')}
                className={`px-3 py-1.5 rounded-lg text-xs font-mono font-medium transition-all flex items-center space-x-1.5 ${
                  currentTab === 'upload'
                    ? 'bg-cyan-500 text-slate-950 font-bold border border-cyan-400 shadow-[0_0_15px_rgba(6,182,212,0.4)]'
                    : 'bg-slate-900 text-slate-300 hover:bg-slate-800 hover:text-white border border-slate-800'
                }`}
              >
                <Plus className="w-3.5 h-3.5" />
                <span>INGEST VIDEO</span>
              </button>

              <button
                onClick={() => setCurrentTab('stream')}
                className={`px-3 py-1.5 rounded-lg text-xs font-mono font-medium transition-all flex items-center space-x-1.5 ${
                  currentTab === 'stream'
                    ? 'bg-rose-500/15 text-rose-300 border border-rose-500/40 shadow-[0_0_12px_rgba(244,63,94,0.2)]'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900 border border-transparent'
                }`}
              >
                <Radio className="w-3.5 h-3.5 text-rose-400 animate-pulse" />
                <span>LIVE STREAM</span>
              </button>

              <button
                onClick={() => setCurrentTab('benchmark')}
                className={`px-3 py-1.5 rounded-lg text-xs font-mono font-medium transition-all flex items-center space-x-1.5 ${
                  currentTab === 'benchmark'
                    ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/40'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900 border border-transparent'
                }`}
              >
                <BarChart3 className="w-3.5 h-3.5" />
                <span>AUDIT & BENCHMARK</span>
              </button>

              <button
                onClick={onLogout}
                className="px-2.5 py-1.5 rounded-lg text-xs font-mono text-slate-500 hover:text-rose-400 hover:bg-rose-950/20 border border-transparent hover:border-rose-900/40 transition-all flex items-center"
                title="Disconnect Operator"
              >
                <LogOut className="w-3.5 h-3.5" />
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => setCurrentTab('benchmark')}
                className={`px-3 py-1.5 rounded-lg text-xs font-mono font-medium flex items-center space-x-1.5 transition-all ${
                  currentTab === 'benchmark'
                    ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/40'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
                }`}
              >
                <BarChart3 className="w-3.5 h-3.5" />
                <span>PUBLIC BENCHMARK</span>
              </button>
              <button
                onClick={() => setCurrentTab('login')}
                className="px-3.5 py-1.5 rounded-lg text-xs font-mono font-semibold bg-cyan-500 text-slate-950 hover:bg-cyan-400 transition-all shadow-[0_0_15px_rgba(6,182,212,0.3)]"
              >
                OPERATOR LOGIN
              </button>
            </>
          )}
        </nav>
      </div>
    </header>
  );
};

export const DisclaimerBanner: React.FC = () => {
  return (
    <div className="bg-amber-950/30 border border-amber-600/30 rounded-xl p-3.5 flex items-start space-x-3 text-amber-300/90 font-mono text-xs shadow-sm">
      <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
      <div className="leading-relaxed">
        <span className="font-bold text-amber-400 uppercase tracking-wider">Operational Directive: </span>
        RipGuard is a tactical computer vision decision-support prototype evaluated against the CVPR 2025 RipVIS dataset. Rip current boundary dynamics are inherently fluid and non-rigid. Always confirm detections with qualified human lifeguard observation before dispatching waterborne rescue.
      </div>
    </div>
  );
};
