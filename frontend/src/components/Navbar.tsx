import React from 'react';
import { Eye, BarChart3, Plus, LogOut, Waves, Info } from 'lucide-react';

interface NavbarProps {
  currentTab: string;
  setCurrentTab: (tab: string) => void;
  isLoggedIn: boolean;
  onLogout: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ currentTab, setCurrentTab, isLoggedIn, onLogout }) => {
  return (
    <header className="border-b border-slate-800 bg-slate-950/95 backdrop-blur-md sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand */}
        <div
          className="flex items-center space-x-3 cursor-pointer group"
          onClick={() => setCurrentTab(isLoggedIn ? 'dashboard' : 'login')}
        >
          <div className="bg-sky-500/15 p-2.5 rounded-xl text-sky-400 border border-sky-500/30 group-hover:border-sky-400 transition-colors">
            <Waves className="w-5 h-5 text-sky-400" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="font-bold text-xl tracking-tight text-white">
                Rip<span className="text-sky-400">Guard</span>
              </span>
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-sky-500/10 text-sky-300 border border-sky-500/20 font-medium">
                Beach Safety AI
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Automated Rip Current Detection &amp; Lifeguard Decision Support
            </p>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav className="flex items-center space-x-2">
          {isLoggedIn ? (
            <>
              <button
                onClick={() => setCurrentTab('dashboard')}
                className={`px-3.5 py-2 rounded-lg text-sm font-medium transition-all flex items-center space-x-1.5 ${
                  currentTab === 'dashboard' || currentTab === 'detail'
                    ? 'bg-slate-800 text-white border border-slate-700'
                    : 'text-slate-400 hover:text-white hover:bg-slate-900'
                }`}
              >
                <Eye className="w-4 h-4" />
                <span>Beach Videos</span>
              </button>

              <button
                onClick={() => setCurrentTab('upload')}
                className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all flex items-center space-x-1.5 ${
                  currentTab === 'upload'
                    ? 'bg-sky-400 text-slate-950 shadow-lg shadow-sky-500/25'
                    : 'bg-sky-500 text-slate-950 hover:bg-sky-400 shadow-md shadow-sky-500/15'
                }`}
              >
                <Plus className="w-4 h-4 stroke-[2.5]" />
                <span>Upload Video</span>
              </button>

              <button
                onClick={() => setCurrentTab('benchmark')}
                className={`px-3.5 py-2 rounded-lg text-sm font-medium transition-all flex items-center space-x-1.5 ${
                  currentTab === 'benchmark'
                    ? 'bg-slate-800 text-white border border-slate-700'
                    : 'text-slate-400 hover:text-white hover:bg-slate-900'
                }`}
              >
                <BarChart3 className="w-4 h-4" />
                <span>Model Accuracy</span>
              </button>

              <button
                onClick={onLogout}
                className="p-2 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-rose-950/30 transition-all flex items-center"
                title="Sign Out"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => setCurrentTab('benchmark')}
                className={`px-3.5 py-2 rounded-lg text-sm font-medium flex items-center space-x-1.5 transition-all ${
                  currentTab === 'benchmark'
                    ? 'bg-slate-800 text-white border border-slate-700'
                    : 'text-slate-400 hover:text-white hover:bg-slate-900'
                }`}
              >
                <BarChart3 className="w-4 h-4" />
                <span>Model Accuracy</span>
              </button>
              <button
                onClick={() => setCurrentTab('login')}
                className="px-4 py-2 rounded-lg text-sm font-semibold bg-sky-500 text-slate-950 hover:bg-sky-400 transition-all"
              >
                Sign In
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
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl px-4 py-3 flex items-center space-x-3 text-slate-300 text-xs">
      <Info className="w-4 h-4 text-sky-400 shrink-0" />
      <span>
        <strong>Safety Note:</strong> RipGuard highlights rip current channels directly on beach footage to assist lifeguards and coastal observers. Always verify water conditions on site.
      </span>
    </div>
  );
};
