import React, { useState, useEffect, useRef } from 'react';
import { apiFetch, getVideoUrl, AnalysisSession } from '../api';
import { DisclaimerBanner } from '../components/Navbar';
import { ArrowLeft, Clock, AlertTriangle, ShieldCheck, CheckCircle2, AlertCircle, Play, Pause, RefreshCw, Crosshair, Waves, Activity, Radio, MapPin, Gauge } from 'lucide-react';

interface SessionDetailScreenProps {
  sessionId: string;
  onBack: () => void;
}

export const SessionDetailScreen: React.FC<SessionDetailScreenProps> = ({ sessionId, onBack }) => {
  const [session, setSession] = useState<AnalysisSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const fetchSession = async () => {
    try {
      const data = await apiFetch(`/api/sessions/${sessionId}`);
      setSession(data);
      if (data.status === 'done' || data.status === 'failed') {
        setLoading(false);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to fetch session detail');
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSession();
    const interval = setInterval(() => {
      if (session?.status !== 'done' && session?.status !== 'failed') {
        fetchSession();
      }
    }, 2500);
    return () => clearInterval(interval);
  }, [sessionId, session?.status]);

  const handleTimeUpdate = () => {
    if (videoRef.current) {
      setCurrentTime(videoRef.current.currentTime);
    }
  };

  const handleLoadedMetadata = () => {
    if (videoRef.current) {
      setDuration(videoRef.current.duration);
    }
  };

  const jumpToTime = (timestampSec: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = timestampSec;
      videoRef.current.play();
      setIsPlaying(true);
    }
  };

  if (loading && !session) {
    return (
      <div className="p-16 text-center text-slate-400 font-mono space-y-3">
        <RefreshCw className="w-8 h-8 animate-spin mx-auto text-cyan-400" />
        <p className="text-xs uppercase tracking-wider">Acquiring surveillance session telemetry {sessionId}...</p>
      </div>
    );
  }

  if (error || !session) {
    return (
      <div className="space-y-4 max-w-4xl mx-auto">
        <button onClick={onBack} className="inline-flex items-center text-xs font-mono text-slate-400 hover:text-white">
          <ArrowLeft className="w-4 h-4 mr-1.5" /> Return to Surveillance Deck
        </button>
        <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800/60 text-rose-300 font-mono text-xs">
          {error || 'Session not found in telemetry registry'}
        </div>
      </div>
    );
  }

  const timeline = session.risk_timeline || [];
  const maxConfidence = timeline.length > 0 ? Math.max(...timeline.map((p) => p.confidence)) : 0;
  const detections = session.detections || [];

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-cyan-950/60">
        <div className="flex items-center space-x-3">
          <button
            onClick={onBack}
            className="p-2 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 hover:text-white hover:border-cyan-500/40 transition-all"
            title="Back to Dashboard"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <div className="flex items-center space-x-2">
              <span className="font-mono text-xs text-cyan-400 uppercase font-semibold">INCIDENT ANALYSIS</span>
              <span className="text-slate-600">/</span>
              <span className="font-mono text-xs text-slate-400 truncate max-w-xs">{session.filename}</span>
            </div>
            <h1 className="text-xl font-bold font-mono text-white tracking-tight mt-0.5">
              Rip Current Tracking & Telemetry Session
            </h1>
          </div>
        </div>

        <div className="flex items-center space-x-3 text-xs font-mono">
          <span className="px-2.5 py-1 rounded bg-slate-900 border border-slate-800 text-slate-400">
            LOC: <strong className="text-slate-200">{session.location_label || 'COASTAL SITE #1'}</strong>
          </span>
          <span className="px-2.5 py-1 rounded bg-slate-900 border border-slate-800 text-slate-400">
            UUID: <strong className="text-slate-200">{session.id.substring(0, 8)}...</strong>
          </span>
        </div>
      </div>

      {/* Mandatory Disclaimer */}
      <DisclaimerBanner />

      {/* Processing or Failed State */}
      {session.status !== 'done' && (
        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-8 text-center space-y-4 shadow-2xl">
          {session.status === 'failed' ? (
            <div className="space-y-3 max-w-lg mx-auto">
              <div className="w-12 h-12 rounded-full bg-rose-500/10 text-rose-400 flex items-center justify-center mx-auto border border-rose-500/20">
                <AlertCircle className="w-6 h-6" />
              </div>
              <h3 className="text-base font-bold font-mono text-white uppercase">Inference Aborted / Validation Rejected</h3>
              <p className="text-xs font-mono text-rose-300 leading-relaxed bg-rose-950/30 p-3 rounded-lg border border-rose-500/20">
                {session.error_message || 'Inference pipeline error or Out-of-Distribution rejection.'}
              </p>
            </div>
          ) : (
            <div className="space-y-3 max-w-md mx-auto">
              <div className="w-12 h-12 rounded-full bg-cyan-500/10 text-cyan-400 flex items-center justify-center mx-auto border border-cyan-500/30 animate-pulse">
                <Clock className="w-6 h-6" />
              </div>
              <h3 className="text-base font-bold font-mono text-white uppercase">
                {session.status === 'processing' ? 'Running Spatio-Temporal Segmentation...' : 'Awaiting Ingestion Worker...'}
              </h3>
              <p className="text-xs font-mono text-slate-400 leading-relaxed">
                Applying Farnebäck optical flow vectors, coastal domain verification, and Temporal Confidence Aggregation (TCA).
              </p>
              <div className="text-xs text-cyan-400 font-mono tracking-widest uppercase">
                STATUS: {session.status.toUpperCase()}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Main Analysis View when Done */}
      {session.status === 'done' && (
        <div className="space-y-6">
          {/* Quick Metrics Bar */}
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
            <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl">
              <div className="text-[10px] font-mono uppercase text-slate-400">Target Risk Classification</div>
              <div className="mt-1 flex items-center space-x-2">
                <span
                  className={`text-xl font-bold font-mono uppercase ${
                    session.overall_risk_level === 'high'
                      ? 'text-rose-400'
                      : session.overall_risk_level === 'medium'
                      ? 'text-amber-400'
                      : 'text-emerald-400'
                  }`}
                >
                  {session.overall_risk_level || 'LOW'}
                </span>
                <span className="text-xs font-mono text-slate-500">
                  ({(maxConfidence * 100).toFixed(1)}% PEAK)
                </span>
              </div>
            </div>

            <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl">
              <div className="text-[10px] font-mono uppercase text-slate-400">Flagged Risk Intervals</div>
              <div className="mt-1 text-xl font-bold font-mono text-white">
                {detections.length} <span className="text-xs font-normal text-slate-400 font-mono">intervals</span>
              </div>
            </div>

            <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl">
              <div className="text-[10px] font-mono uppercase text-slate-400">Motion Tracking Algorithm</div>
              <div className="mt-1 text-sm font-bold font-mono text-cyan-400 flex items-center">
                <Waves className="w-4 h-4 mr-1.5" />
                Dense Farnebäck (5-Ch)
              </div>
            </div>

            <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl">
              <div className="text-[10px] font-mono uppercase text-slate-400">Filter Aggregation</div>
              <div className="mt-1 text-sm font-bold font-mono text-emerald-400 flex items-center">
                <Gauge className="w-4 h-4 mr-1.5" />
                TCA Smoothed (α=0.65)
              </div>
            </div>
          </div>

          {/* Tactical Split Deck: Left 65% Video Player / Right 35% Live Telemetry */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Left Column: Player & Timeline */}
            <div className="lg:col-span-8 space-y-4">
              <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-2xl relative">
                <div className="relative bg-black aspect-video flex items-center justify-center overflow-hidden">
                  <video
                    ref={videoRef}
                    src={getVideoUrl(session.id)}
                    controls
                    onTimeUpdate={handleTimeUpdate}
                    onLoadedMetadata={handleLoadedMetadata}
                    onPlay={() => setIsPlaying(true)}
                    onPause={() => setIsPlaying(false)}
                    className="w-full h-full object-contain"
                  />

                  {/* Dynamic Tactical HUD Overlay */}
                  {(() => {
                    const activeDetection = detections.find(
                      (d) => currentTime >= d.start_timestamp_sec && currentTime <= d.end_timestamp_sec
                    );
                    const nearestPoint = timeline.reduce((prev, curr) => {
                      return Math.abs(curr.t - currentTime) < Math.abs(prev.t - currentTime) ? curr : prev;
                    }, timeline[0] || { t: 0, confidence: 0 });

                    const activeConfidence = activeDetection
                      ? activeDetection.confidence
                      : nearestPoint
                      ? nearestPoint.confidence
                      : 0;

                    const isHigh = activeConfidence >= 0.7;
                    const isMed = activeConfidence >= 0.4 && activeConfidence < 0.7;
                    const region = activeDetection?.bounding_region;

                    return (
                      <div className="absolute inset-0 pointer-events-none p-4 flex flex-col justify-between">
                        {/* Top HUD Row */}
                        <div className="flex items-center justify-between">
                          <div className="flex items-center space-x-2 bg-slate-950/90 backdrop-blur px-3 py-1.5 rounded-lg border border-slate-800 text-xs font-mono">
                            <span className="flex h-2 w-2 relative">
                              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
                              <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500"></span>
                            </span>
                            <span className="text-slate-300 font-bold uppercase tracking-wider">TACTICAL HUD</span>
                            <span className="text-slate-600">|</span>
                            <span className="text-cyan-400">{currentTime.toFixed(1)}s</span>
                          </div>

                          <div className="flex items-center space-x-2 bg-slate-950/90 backdrop-blur px-3 py-1.5 rounded-lg border border-slate-800 text-xs font-mono">
                            <span className="text-slate-400">SURF STATE:</span>
                            <span
                              className={`font-bold px-2 py-0.5 rounded ${
                                isHigh
                                  ? 'bg-rose-500/20 text-rose-400 border border-rose-500/40 animate-pulse'
                                  : isMed
                                  ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40'
                                  : 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                              }`}
                            >
                              {isHigh ? 'CRITICAL RIP CURRENT' : isMed ? 'ELEVATED SURF' : 'NORMAL WATER'}
                            </span>
                            <span className="text-white font-bold">{(activeConfidence * 100).toFixed(1)}%</span>
                          </div>
                        </div>

                        {/* Bounding Box Reticle */}
                        {region && (
                          <div
                            className="absolute border-2 border-dashed border-rose-500 rounded bg-rose-500/15 backdrop-blur-[1px] transition-all duration-200 shadow-[0_0_20px_rgba(244,63,94,0.5)]"
                            style={{
                              left: `${Math.max(5, Math.min(90, region.x * 100))}%`,
                              top: `${Math.max(5, Math.min(90, region.y * 100))}%`,
                              width: `${Math.max(15, Math.min(80, region.w * 100))}%`,
                              height: `${Math.max(15, Math.min(80, region.h * 100))}%`,
                            }}
                          >
                            <div className="absolute -top-6 left-0 bg-rose-600 text-white font-mono text-[10px] font-bold px-2 py-0.5 rounded shadow flex items-center space-x-1">
                              <Crosshair className="w-3 h-3" />
                              <span>TARGET CORRIDOR [{(activeConfidence * 100).toFixed(1)}%]</span>
                            </div>
                          </div>
                        )}

                        {/* Bottom Reticle */}
                        <div className="flex items-center justify-between text-[11px] font-mono text-slate-400 bg-slate-950/80 backdrop-blur px-3 py-1.5 rounded-lg border border-slate-800">
                          <div className="flex items-center space-x-2">
                            <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                            <span>FARNEBÄCK SURFACE FLOW TRACKER ACTIVE</span>
                          </div>
                          <div>
                            CORRIDOR CONFIDENCE: <strong className="text-cyan-400">{(activeConfidence * 100).toFixed(1)}%</strong>
                          </div>
                        </div>
                      </div>
                    );
                  })()}
                </div>

                {/* Interactive Seekbar Timeline */}
                <div className="p-4 border-t border-slate-800 space-y-3 bg-slate-950/60">
                  <div className="flex items-center justify-between font-mono text-xs">
                    <div>
                      <span className="font-bold text-slate-200">Temporal Risk Distribution</span>
                      <span className="text-slate-500 ml-2">(Click bars to scrub video)</span>
                    </div>
                    <div className="text-cyan-400">
                      {currentTime.toFixed(1)}s / {duration.toFixed(1)}s
                    </div>
                  </div>

                  <div className="relative h-14 bg-slate-950 border border-slate-800 rounded-lg overflow-hidden flex items-end px-1 py-1">
                    {duration > 0 && (
                      <div
                        className="absolute top-0 bottom-0 w-0.5 bg-cyan-400 z-10 shadow-[0_0_10px_rgba(6,182,212,1)]"
                        style={{ left: `${(currentTime / duration) * 100}%` }}
                      />
                    )}

                    {timeline.map((point, idx) => {
                      const isHigh = point.confidence >= 0.7;
                      const isMed = point.confidence >= 0.4 && point.confidence < 0.7;
                      const heightPercent = Math.max(10, point.confidence * 100);

                      return (
                        <div
                          key={idx}
                          onClick={() => jumpToTime(point.t)}
                          title={`t=${point.t}s | Confidence: ${(point.confidence * 100).toFixed(1)}%`}
                          className="flex-1 mx-0.5 cursor-pointer group flex flex-col justify-end h-full"
                        >
                          <div
                            style={{ height: `${heightPercent}%` }}
                            className={`w-full rounded-t transition-all ${
                              isHigh
                                ? 'bg-rose-500 group-hover:bg-rose-400'
                                : isMed
                                ? 'bg-amber-500 group-hover:bg-amber-400'
                                : 'bg-emerald-500/60 group-hover:bg-emerald-400'
                            }`}
                          />
                        </div>
                      );
                    })}
                  </div>

                  <div className="flex items-center justify-between text-[11px] font-mono text-slate-500 pt-1">
                    <span className="flex items-center">
                      <span className="w-2 h-2 rounded-full bg-rose-500 mr-1.5" /> High (≥70%)
                    </span>
                    <span className="flex items-center">
                      <span className="w-2 h-2 rounded-full bg-amber-500 mr-1.5" /> Medium (40-69%)
                    </span>
                    <span className="flex items-center">
                      <span className="w-2 h-2 rounded-full bg-emerald-500 mr-1.5" /> Low (&lt;40%)
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Right Column: Diagnostic Deck & Flagged Windows */}
            <div className="lg:col-span-4 space-y-4">
              {/* Surveillance Diagnostic Card */}
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
                <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-300 flex items-center justify-between">
                  <span>Diagnostic Telemetry</span>
                  <Activity className="w-4 h-4 text-cyan-400" />
                </h3>

                <div className="space-y-3 font-mono text-xs">
                  <div>
                    <div className="flex justify-between text-slate-400 mb-1">
                      <span>Max Peak Confidence:</span>
                      <span className="text-white font-bold">{(maxConfidence * 100).toFixed(1)}%</span>
                    </div>
                    <div className="w-full bg-slate-950 rounded-full h-1.5">
                      <div
                        className={`h-1.5 rounded-full ${
                          maxConfidence >= 0.7 ? 'bg-rose-500' : maxConfidence >= 0.4 ? 'bg-amber-400' : 'bg-emerald-400'
                        }`}
                        style={{ width: `${Math.min(100, maxConfidence * 100)}%` }}
                      />
                    </div>
                  </div>

                  <div className="pt-2 border-t border-slate-800 flex justify-between">
                    <span className="text-slate-400">Coastal Domain Check:</span>
                    <span className="text-emerald-400 font-bold">VERIFIED FLUID SURF</span>
                  </div>

                  <div className="pt-2 border-t border-slate-800 flex justify-between">
                    <span className="text-slate-400">Total Analyzed Duration:</span>
                    <span className="text-slate-200">{duration.toFixed(1)} seconds</span>
                  </div>

                  <div className="pt-2 border-t border-slate-800 flex justify-between">
                    <span className="text-slate-400">Execution Runtime:</span>
                    <span className="text-slate-200">ONNX CoreML / MPS Edge</span>
                  </div>
                </div>
              </div>

              {/* Flagged Windows */}
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
                <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-300 flex items-center justify-between">
                  <span>Flagged Current Intervals ({detections.length})</span>
                  <Crosshair className="w-4 h-4 text-rose-400" />
                </h3>

                {detections.length === 0 ? (
                  <p className="text-xs font-mono text-slate-500 italic py-2">
                    No sustained rip current windows detected above threshold.
                  </p>
                ) : (
                  <div className="space-y-2.5 max-h-72 overflow-y-auto pr-1">
                    {detections.map((det, index) => (
                      <div
                        key={det.id || index}
                        className="p-3 rounded-lg bg-slate-950 border border-slate-800 hover:border-cyan-500/40 transition-all font-mono text-xs flex items-center justify-between"
                      >
                        <div>
                          <div className="font-bold text-slate-200">
                            INTERVAL #{index + 1}: {det.start_timestamp_sec.toFixed(1)}s - {det.end_timestamp_sec.toFixed(1)}s
                          </div>
                          <div className="text-[11px] text-rose-400 mt-0.5">
                            Confidence: {(det.confidence * 100).toFixed(1)}%
                          </div>
                        </div>
                        <button
                          onClick={() => jumpToTime(det.start_timestamp_sec)}
                          className="px-2.5 py-1 rounded bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 text-[11px] hover:bg-cyan-500/25 transition-all font-bold"
                        >
                          SEEK
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
