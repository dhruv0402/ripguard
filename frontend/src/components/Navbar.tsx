import React from 'react';
import { AlertTriangle, ShieldCheck, Activity, BarChart2, PlusCircle, LogOut } from 'lucide-react';

interface NavbarProps {
  currentTab: string;
  setCurrentTab: (tab: string) => void;
  isLoggedIn: boolean;
  onLogout: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ currentTab, setCurrentTab, isLoggedIn, onLogout }) => {
  return (
    <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center space-x-3 cursor-pointer" onClick={() => setCurrentTab(isLoggedIn ? 'dashboard' : 'login')}>
          <div className="bg-sky-500/20 p-2 rounded-lg text-sky-400 border border-sky-500/30">
            <Activity className="w-5 h-5" />
          </div>
          <div>
            <span className="font-bold text-lg tracking-tight bg-gradient-to-r from-sky-400 to-teal-300 bg-clip-text text-transparent">
              RipGuard
            </span>
            <span className="ml-2 text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700">
              CVPR '25 RipVIS Prototype
            </span>
          </div>
        </div>

        <nav className="flex items-center space-x-2">
          {isLoggedIn ? (
            <>
              <button
                onClick={() => setCurrentTab('dashboard')}
                className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  currentTab === 'dashboard'
                    ? 'bg-sky-500/20 text-sky-400 border border-sky-500/30'
                    : 'text-slate-300 hover:text-white hover:bg-slate-800'
                }`}
              >
                Dashboard
              </button>
              <button
                onClick={() => setCurrentTab('upload')}
                className={`px-3 py-1.5 rounded-md text-sm font-medium flex items-center space-x-1 transition-colors ${
                  currentTab === 'upload'
                    ? 'bg-sky-500 text-white'
                    : 'bg-slate-800 text-slate-200 hover:bg-slate-700'
                }`}
              >
                <PlusCircle className="w-4 h-4 mr-1" />
                New Analysis
              </button>
              <button
                onClick={() => setCurrentTab('benchmark')}
                className={`px-3 py-1.5 rounded-md text-sm font-medium flex items-center space-x-1 transition-colors ${
                  currentTab === 'benchmark'
                    ? 'bg-sky-500/20 text-sky-400 border border-sky-500/30'
                    : 'text-slate-300 hover:text-white hover:bg-slate-800'
                }`}
              >
                <BarChart2 className="w-4 h-4 mr-1" />
                Benchmark
              </button>
              <button
                onClick={onLogout}
                className="px-3 py-1.5 rounded-md text-sm text-slate-400 hover:text-rose-400 hover:bg-slate-800/80 transition-colors flex items-center"
                title="Log out"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => setCurrentTab('benchmark')}
                className={`px-3 py-1.5 rounded-md text-sm font-medium flex items-center space-x-1 transition-colors ${
                  currentTab === 'benchmark'
                    ? 'bg-sky-500/20 text-sky-400 border border-sky-500/30'
                    : 'text-slate-300 hover:text-white hover:bg-slate-800'
                }`}
              >
                <BarChart2 className="w-4 h-4 mr-1" />
                Benchmark (Public)
              </button>
              <button
                onClick={() => setCurrentTab('login')}
                className="px-4 py-1.5 rounded-md text-sm font-medium bg-sky-500 text-white hover:bg-sky-600 transition-colors"
              >
                Operator Login
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
    <div className="bg-amber-950/40 border border-amber-600/40 rounded-xl p-4 flex items-start space-x-3 text-amber-200 shadow-sm">
      <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
      <div className="text-sm">
        <span className="font-semibold text-amber-300">Safety Notice: </span>
        This is a research prototype and decision-support aid evaluated against the CVPR 2025 RipVIS benchmark, not a certified safety-of-life system. Rip current segmentation from video is an unsolved computer vision problem. Never use this as an autonomous safety trigger — always rely on trained lifeguard inspection.
      </div>
    </div>
  );
};
