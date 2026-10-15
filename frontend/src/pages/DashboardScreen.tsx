import React, { useState, useEffect } from 'react';
import { apiFetch, AnalysisSession } from '../api';
import { Video, Calendar, MapPin, AlertTriangle, ShieldCheck, Clock, ChevronRight, Plus, Search, ShieldAlert, Waves, CheckCircle2, XCircle } from 'lucide-react';

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

  const getRiskBadge = (level: string | null) => {
    if (level === 'high') {
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded font-mono text-[11px] font-bold bg-rose-500/15 text-rose-400 border border-rose-500/30 uppercase tracking-wider">
          <AlertTriangle className="w-3 h-3 mr-1" />
          HIGH RISK
        </span>
      );
    }
    if (level === 'medium') {
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded font-mono text-[11px] font-bold bg-amber-500/15 text-amber-400 border border-amber-500/30 uppercase tracking-wider">
          <AlertTriangle className="w-3 h-3 mr-1" />
          MEDIUM
        </span>
      );
    }
    if (level === 'low') {
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded font-mono text-[11px] font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 uppercase tracking-wider">
          <ShieldCheck className="w-3 h-3 mr-1" />
          LOW SURF
        </span>
      );
    }
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded font-mono text-[11px] text-slate-500 bg-slate-900 border border-slate-800 uppercase">
        PENDING
      </span>
    );
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'done':
        return (
          <span className="inline-flex items-center text-xs font-mono text-emerald-400">
            <CheckCircle2 className="w-3.5 h-3.5 mr-1" />
            PROCESSED
          </span>
        );
      case 'processing':
        return (
          <span className="inline-flex items-center text-xs font-mono text-cyan-400 animate-pulse">
            <Clock className="w-3.5 h-3.5 mr-1" />
            ANALYZING...
          </span>
        );
      case 'failed':
        return (
          <span className="inline-flex items-center text-xs font-mono text-rose-400">
            <XCircle className="w-3.5 h-3.5 mr-1" />
            REJECTED / FAILED
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center text-xs font-mono text-slate-500">
            <Clock className="w-3.5 h-3.5 mr-1" />
            QUEUED
          </span>
        );
    }
  };

  const highRiskCount = safeSessions.filter((s) => s.overall_risk_level === 'high').length;
  const processedCount = safeSessions.filter((s) => s.status === 'done').length;

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Tactical Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-cyan-950/60">
        <div>
          <div className="flex items-center space-x-2">
            <span className="h-2 w-2 rounded-full bg-cyan-400 animate-ping"></span>
            <span className="text-xs font-mono text-cyan-400 uppercase tracking-widest font-semibold">
              TACTICAL SURVEILLANCE FEED
            </span>
          </div>
          <h1 className="text-2xl font-extrabold text-white font-mono tracking-tight mt-1">
            Coastal Incident & Surveillance Deck
          </h1>
          <p className="text-xs text-slate-400 font-mono mt-0.5">
            Active CVPR 2025 RipVIS spatio-temporal inference & coastal domain verification console.
          </p>
        </div>

        <button
          onClick={onNewAnalysis}
          className="inline-flex items-center justify-center space-x-2 px-4 py-2.5 rounded-lg bg-cyan-500 text-slate-950 hover:bg-cyan-400 font-mono font-bold text-xs transition-all shadow-[0_0_20px_rgba(6,182,212,0.3)] shrink-0"
        >
          <Plus className="w-4 h-4 stroke-[3]" />
          <span>INGEST NEW SURVEILLANCE CLIP</span>
        </button>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 shadow-sm flex items-center justify-between">
          <div>
            <div className="text-[11px] font-mono uppercase text-slate-400">Total Analyzed Feeds</div>
            <div className="text-2xl font-bold font-mono text-white mt-1">{safeSessions.length}</div>
          </div>
          <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 text-cyan-400">
            <Video className="w-5 h-5" />
          </div>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 shadow-sm flex items-center justify-between">
          <div>
            <div className="text-[11px] font-mono uppercase text-slate-400">High Risk Active Corridors</div>
            <div className="text-2xl font-bold font-mono text-rose-400 mt-1">{highRiskCount}</div>
          </div>
          <div className="p-2.5 rounded-lg bg-rose-950/30 border border-rose-500/30 text-rose-400">
            <ShieldAlert className="w-5 h-5" />
          </div>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 shadow-sm flex items-center justify-between">
          <div>
            <div className="text-[11px] font-mono uppercase text-slate-400">TCA Verified Pipelines</div>
            <div className="text-2xl font-bold font-mono text-emerald-400 mt-1">{processedCount}</div>
          </div>
          <div className="p-2.5 rounded-lg bg-emerald-950/30 border border-emerald-500/30 text-emerald-400">
            <Waves className="w-5 h-5" />
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row gap-3 bg-slate-900/90 border border-slate-800 p-3 rounded-xl backdrop-blur-sm">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3.5 top-3 text-slate-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search footage filename or camera location tag..."
            className="w-full pl-10 pr-4 py-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-200 placeholder-slate-600 text-xs font-mono focus:outline-none focus:border-cyan-500 transition-colors"
          />
        </div>
        <div className="flex items-center space-x-2">
          <span className="text-xs font-mono text-slate-400">FILTER:</span>
          <select
            value={riskFilter}
            onChange={(e) => setRiskFilter(e.target.value)}
            className="px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-200 text-xs font-mono focus:outline-none focus:border-cyan-500"
          >
            <option value="all">ALL CONDITIONS</option>
            <option value="high">HIGH RISK ONLY</option>
            <option value="medium">MEDIUM RISK</option>
            <option value="low">LOW SURF</option>
          </select>
        </div>
      </div>

      {/* Sessions Deck */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl overflow-hidden shadow-2xl">
        {loading ? (
          <div className="p-12 text-center text-slate-500 font-mono text-xs">
            Querying surveillance registry...
          </div>
        ) : filteredSessions.length === 0 ? (
          <div className="p-12 text-center space-y-3">
            <Waves className="w-10 h-10 text-slate-700 mx-auto" />
            <h3 className="text-sm font-mono font-bold text-slate-300 uppercase">No Surveillance Sessions Found</h3>
            <p className="text-xs text-slate-500 font-mono max-w-sm mx-auto">
              No recorded coastal sessions match your search criteria. Ingest a new beach surveillance video to initiate analysis.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-slate-800/80">
            {filteredSessions.map((session) => (
              <div
                key={session.id}
                onClick={() => onSelectSession(session.id)}
                className="p-4 hover:bg-cyan-950/20 transition-all cursor-pointer flex items-center justify-between group border-l-2 border-transparent hover:border-cyan-400"
              >
                <div className="flex items-center space-x-4 min-w-0">
                  <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 text-cyan-400 group-hover:border-cyan-500/50 group-hover:shadow-[0_0_12px_rgba(6,182,212,0.2)] transition-all">
                    <Video className="w-4 h-4" />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center space-x-2.5">
                      <span className="font-mono font-bold text-sm text-slate-200 group-hover:text-cyan-300 transition-colors truncate">
                        {session.filename}
                      </span>
                      {getRiskBadge(session.overall_risk_level)}
                    </div>
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500 font-mono mt-1">
                      {session.location_label && (
                        <span className="flex items-center text-slate-400">
                          <MapPin className="w-3 h-3 mr-1 text-cyan-400" />
                          {session.location_label}
                        </span>
                      )}
                      <span className="flex items-center">
                        <Calendar className="w-3 h-3 mr-1 text-slate-600" />
                        {new Date(session.created_at).toLocaleDateString()} {new Date(session.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                      {session.error_message && (
                        <span className="text-rose-400 text-[11px] truncate max-w-md">
                          Reason: {session.error_message}
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                <div className="flex items-center space-x-4 shrink-0">
                  {getStatusBadge(session.status)}
                  <ChevronRight className="w-4 h-4 text-slate-600 group-hover:text-cyan-400 group-hover:translate-x-0.5 transition-all" />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
