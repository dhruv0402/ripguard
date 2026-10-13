import React, { useState, useEffect } from 'react';
import { apiFetch, AnalysisSession } from '../api';
import { Video, Calendar, MapPin, AlertCircle, CheckCircle, Clock, ChevronRight, PlusCircle, Search } from 'lucide-react';

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
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20">
          High Risk
        </span>
      );
    }
    if (level === 'medium') {
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">
          Medium Risk
        </span>
      );
    }
    if (level === 'low') {
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
          Low Risk
        </span>
      );
    }
    return (
      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-800 text-slate-400">
        Pending Eval
      </span>
    );
  };

  const getStatusBadge = (status: string) => {
    if (status === 'done') {
      return (
        <span className="flex items-center text-xs text-emerald-400">
          <CheckCircle className="w-3.5 h-3.5 mr-1" /> Ready
        </span>
      );
    }
    if (status === 'processing' || status === 'pending') {
      return (
        <span className="flex items-center text-xs text-sky-400 animate-pulse">
          <Clock className="w-3.5 h-3.5 mr-1" /> {status === 'processing' ? 'Analyzing...' : 'Queued'}
        </span>
      );
    }
    return (
      <span className="flex items-center text-xs text-rose-400">
        <AlertCircle className="w-3.5 h-3.5 mr-1" /> Failed
      </span>
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Surveillance Sessions</h1>
          <p className="text-sm text-slate-400 mt-1">
            Historical beach video recordings, rip current detections, and risk classifications
          </p>
        </div>
        <button
          onClick={onNewAnalysis}
          className="inline-flex items-center px-4 py-2 rounded-xl bg-sky-500 hover:bg-sky-400 text-white font-medium text-sm transition-colors shadow-lg shadow-sky-500/20"
        >
          <PlusCircle className="w-4 h-4 mr-2" />
          New Video Analysis
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row gap-3 bg-slate-900 border border-slate-800 p-3 rounded-xl">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3 top-3 text-slate-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by filename or beach camera location..."
            className="w-full pl-9 pr-4 py-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-100 placeholder-slate-500 text-sm focus:outline-none focus:border-sky-500"
          />
        </div>
        <div className="flex items-center space-x-2">
          <span className="text-xs text-slate-400 font-medium">Risk:</span>
          <select
            value={riskFilter}
            onChange={(e) => setRiskFilter(e.target.value)}
            className="px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-200 text-sm focus:outline-none focus:border-sky-500"
          >
            <option value="all">All Risk Levels</option>
            <option value="high">High Risk</option>
            <option value="medium">Medium Risk</option>
            <option value="low">Low Risk</option>
          </select>
        </div>
      </div>

      {/* Sessions Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
        {loading ? (
          <div className="p-12 text-center text-slate-400 text-sm">Loading sessions...</div>
        ) : filteredSessions.length === 0 ? (
          <div className="p-12 text-center">
            <Video className="w-12 h-12 text-slate-600 mx-auto mb-3" />
            <h3 className="text-base font-semibold text-slate-300">No surveillance sessions found</h3>
            <p className="text-sm text-slate-500 mt-1 max-w-sm mx-auto">
              Upload a coastal video footage clip to execute the U-Net rip current segmentation model.
            </p>
            <button
              onClick={onNewAnalysis}
              className="mt-4 px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-sky-400 text-sm font-medium transition-colors"
            >
              Upload Footage
            </button>
          </div>
        ) : (
          <div className="divide-y divide-slate-800/80">
            {filteredSessions.map((session) => (
              <div
                key={session.id}
                onClick={() => onSelectSession(session.id)}
                className="p-4 hover:bg-slate-800/40 transition-colors cursor-pointer flex items-center justify-between group"
              >
                <div className="flex items-center space-x-4">
                  <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 text-sky-400 group-hover:border-sky-500/40 transition-colors">
                    <Video className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="flex items-center space-x-2">
                      <span className="font-semibold text-sm text-slate-100 group-hover:text-sky-300 transition-colors">
                        {session.filename}
                      </span>
                      {getRiskBadge(session.overall_risk_level)}
                    </div>
                    <div className="flex items-center space-x-4 text-xs text-slate-400 mt-1">
                      {session.location_label && (
                        <span className="flex items-center">
                          <MapPin className="w-3.5 h-3.5 mr-1 text-slate-500" />
                          {session.location_label}
                        </span>
                      )}
                      <span className="flex items-center">
                        <Calendar className="w-3.5 h-3.5 mr-1 text-slate-500" />
                        {new Date(session.created_at).toLocaleDateString()} {new Date(session.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center space-x-4">
                  {getStatusBadge(session.status)}
                  <ChevronRight className="w-5 h-5 text-slate-600 group-hover:text-slate-300 transition-colors" />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
