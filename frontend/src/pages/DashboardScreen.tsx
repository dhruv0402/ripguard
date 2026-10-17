import React, { useState, useEffect } from 'react';
import { apiFetch, AnalysisSession } from '../api';
import { Video, Calendar, MapPin, AlertTriangle, ShieldCheck, Clock, Plus, Search, Play, XCircle } from 'lucide-react';

interface DashboardScreenProps {
  onSelectSession: (id: string) => void;
  onNewAnalysis: () => void;
}

export const DashboardScreen: React.FC<DashboardScreenProps> = ({ onSelectSession, onNewAnalysis }) => {
  const [sessions, setSessions] = useState<AnalysisSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [riskFilter, setRiskFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');

  const fetchSessions = async () => {
    try {
      setLoading(true);
      const data = await apiFetch('/api/sessions');
      if (Array.isArray(data)) {
        setSessions(data);
      } else {
        setSessions([]);
      }
    } catch (err) {
      console.error('Failed to load sessions', err);
      setSessions([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSessions();
  }, []);

  const safeSessions = Array.isArray(sessions) ? sessions : [];

  const filteredSessions = safeSessions.filter((s) => {
    if (riskFilter !== 'all' && s.overall_risk_level !== riskFilter) {
      return false;
    }
    if (searchQuery.trim() !== '') {
      const q = searchQuery.toLowerCase();
      const matchFile = (s.filename || '').toLowerCase().includes(q);
      const matchLoc = (s.location_label || '').toLowerCase().includes(q);
      return matchFile || matchLoc;
    }
    return true;
  });

  const getRiskBadge = (session: AnalysisSession) => {
    if (session.status === 'failed') {
      return (
        <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-800 text-slate-300 border border-slate-700">
          <XCircle className="w-3.5 h-3.5 mr-1.5 text-rose-400" />
          Rejected: Not a Beach Video
        </span>
      );
    }
    if (session.overall_risk_level === 'high') {
      return (
        <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-500/15 text-rose-300 border border-rose-500/30">
          <AlertTriangle className="w-3.5 h-3.5 mr-1.5 text-rose-400" />
          Danger: Strong Rip Current
        </span>
      );
    }
    if (session.overall_risk_level === 'medium') {
      return (
        <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30">
          <AlertTriangle className="w-3.5 h-3.5 mr-1.5 text-amber-400" />
          Caution: Moderate Rip Current
        </span>
      );
    }
    if (session.overall_risk_level === 'low') {
      return (
        <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
          <ShieldCheck className="w-3.5 h-3.5 mr-1.5 text-emerald-400" />
          Safe: Calm Water (No Rip Current)
        </span>
      );
    }
    return (
      <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium text-sky-300 bg-sky-500/10 border border-sky-500/20">
        <Clock className="w-3.5 h-3.5 mr-1.5 animate-spin" />
        Analyzing Video...
      </span>
    );
  };

  const ripDetectedCount = safeSessions.filter(
    (s) => s.status === 'done' && (s.overall_risk_level === 'high' || s.overall_risk_level === 'medium')
  ).length;
  const safeBeachCount = safeSessions.filter(
    (s) => s.status === 'done' && s.overall_risk_level === 'low'
  ).length;

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">
            Analyzed Beach Videos
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Click any video below to watch the rip current detection overlay, or upload a new beach video.
          </p>
        </div>

        <button
          onClick={onNewAnalysis}
          className="inline-flex items-center justify-center space-x-2 px-5 py-2.5 rounded-xl bg-sky-500 text-slate-950 hover:bg-sky-400 font-semibold text-sm transition-all shadow-lg shadow-sky-500/20 shrink-0"
        >
          <Plus className="w-4 h-4 stroke-[2.5]" />
          <span>Upload New Beach Video</span>
        </button>
      </div>

      {/* Simple Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between">
          <div>
            <div className="text-xs font-medium text-slate-400">Total Videos Uploaded</div>
            <div className="text-2xl font-bold text-white mt-1">{safeSessions.length}</div>
          </div>
          <div className="p-3 rounded-xl bg-slate-800 text-sky-400">
            <Video className="w-5 h-5" />
          </div>
        </div>

        <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between">
          <div>
            <div className="text-xs font-medium text-slate-400">Rip Currents Detected</div>
            <div className="text-2xl font-bold text-rose-400 mt-1">{ripDetectedCount}</div>
          </div>
          <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400">
            <AlertTriangle className="w-5 h-5" />
          </div>
        </div>

        <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between">
          <div>
            <div className="text-xs font-medium text-slate-400">Safe / Calm Beach Videos</div>
            <div className="text-2xl font-bold text-emerald-400 mt-1">{safeBeachCount}</div>
          </div>
          <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
            <ShieldCheck className="w-5 h-5" />
          </div>
        </div>
      </div>

      {/* Search & Filter */}
      <div className="flex flex-col sm:flex-row gap-3 bg-slate-900 border border-slate-800 p-3 rounded-xl">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3.5 top-3 text-slate-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by video name or beach location..."
            className="w-full pl-10 pr-4 py-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-200 placeholder-slate-500 text-sm focus:outline-none focus:border-sky-500"
          />
        </div>
        <div className="flex items-center space-x-2">
          <span className="text-xs font-medium text-slate-400">Show:</span>
          <select
            value={riskFilter}
            onChange={(e) => setRiskFilter(e.target.value)}
            className="px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-200 text-sm focus:outline-none focus:border-sky-500"
          >
            <option value="all">All Videos</option>
            <option value="high">Strong Rip Current (High Risk)</option>
            <option value="medium">Moderate Rip Current</option>
            <option value="low">Safe / Calm Water</option>
          </select>
        </div>
      </div>

      {/* Video List */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
        {loading ? (
          <div className="p-12 text-center text-slate-400 text-sm">
            Loading analyzed beach videos...
          </div>
        ) : filteredSessions.length === 0 ? (
          <div className="p-12 text-center space-y-3">
            <Video className="w-10 h-10 text-slate-600 mx-auto" />
            <h3 className="text-base font-semibold text-slate-200">No Videos Found</h3>
            <p className="text-sm text-slate-400 max-w-md mx-auto">
              Upload a beach video to detect rip currents automatically.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-slate-800">
            {filteredSessions.map((session) => (
              <div
                key={session.id}
                onClick={() => onSelectSession(session.id)}
                className="p-5 hover:bg-slate-800/50 transition-all cursor-pointer flex flex-col sm:flex-row sm:items-center justify-between gap-4"
              >
                <div className="flex items-start space-x-4 min-w-0">
                  <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 text-sky-400 shrink-0 mt-0.5">
                    <Video className="w-5 h-5" />
                  </div>
                  <div className="min-w-0 space-y-1.5">
                    <div className="flex flex-wrap items-center gap-2.5">
                      <span className="font-semibold text-base text-white truncate">
                        {session.filename}
                      </span>
                      {getRiskBadge(session)}
                    </div>
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400">
                      {session.location_label && (
                        <span className="flex items-center text-slate-300">
                          <MapPin className="w-3.5 h-3.5 mr-1 text-sky-400" />
                          {session.location_label}
                        </span>
                      )}
                      <span className="flex items-center">
                        <Calendar className="w-3.5 h-3.5 mr-1 text-slate-500" />
                        {new Date(session.created_at).toLocaleDateString()} at {new Date(session.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                    {session.error_message && (
                      <p className="text-xs text-rose-400 bg-rose-950/30 border border-rose-500/20 rounded-lg px-3 py-1.5 mt-1">
                        {session.error_message}
                      </p>
                    )}
                  </div>
                </div>

                <div className="flex items-center shrink-0">
                  <span className="inline-flex items-center space-x-1.5 px-4 py-2 rounded-lg bg-slate-800 hover:bg-sky-500 hover:text-slate-950 text-slate-200 text-xs font-semibold transition-all">
                    <Play className="w-3.5 h-3.5 fill-current" />
                    <span>{session.status === 'failed' ? 'View Details' : 'Watch Detection'}</span>
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
