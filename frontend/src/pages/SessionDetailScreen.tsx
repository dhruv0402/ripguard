import React, { useState, useEffect, useRef } from 'react';
import { apiFetch, getVideoUrl, AnalysisSession } from '../api';
import { DisclaimerBanner } from '../components/Navbar';
import { ArrowLeft, Clock, AlertTriangle, ShieldCheck, CheckCircle2, AlertCircle, Play, Pause, RefreshCw } from 'lucide-react';

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

  const togglePlay = () => {
    if (videoRef.current) {
      if (videoRef.current.paused) {
        videoRef.current.play();
        setIsPlaying(true);
      } else {
        videoRef.current.pause();
        setIsPlaying(false);
      }
    }
  };

  if (loading && !session) {
    return (
      <div className="p-12 text-center text-slate-400">
        <RefreshCw className="w-8 h-8 animate-spin mx-auto mb-3 text-sky-400" />
        <p>Loading surveillance session {sessionId}...</p>
      </div>
    );
  }

  if (error || !session) {
    return (
      <div className="space-y-4">
        <button onClick={onBack} className="inline-flex items-center text-sm text-slate-400 hover:text-white">
          <ArrowLeft className="w-4 h-4 mr-1" /> Back to Dashboard
        </button>
        <div className="p-4 rounded-xl bg-rose-950/50 border border-rose-800 text-rose-300 text-sm">
          {error || 'Session not found'}
        </div>
      </div>
    );
  }

  const timeline = session.risk_timeline || [];
  const maxConfidence = timeline.length > 0 ? Math.max(...timeline.map((p) => p.confidence)) : 0;
  const detections = session.detections || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <button
          onClick={onBack}
          className="inline-flex items-center text-sm font-medium text-slate-400 hover:text-white transition-colors"
        >
          <ArrowLeft className="w-4 h-4 mr-1.5" /> Back to Surveillance Dashboard
        </button>
        <span className="text-xs text-slate-500 font-mono">ID: {session.id}</span>
      </div>

      {/* Mandatory Disclaimer Banner per PRD */}
      <DisclaimerBanner />

      {/* Processing or Failed State */}
      {session.status !== 'done' && (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8 text-center space-y-4 shadow-xl">
          {session.status === 'failed' ? (
            <div className="space-y-3">
              <div className="w-12 h-12 rounded-full bg-rose-500/10 text-rose-400 flex items-center justify-center mx-auto border border-rose-500/20">
                <AlertCircle className="w-6 h-6" />
              </div>
              <h3 className="text-lg font-bold text-white">Video Analysis Failed</h3>
              <p className="text-sm text-rose-300 max-w-md mx-auto">{session.error_message || 'Inference pipeline error'}</p>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="w-12 h-12 rounded-full bg-sky-500/10 text-sky-400 flex items-center justify-center mx-auto border border-sky-500/20 animate-pulse">
                <Clock className="w-6 h-6" />
              </div>
              <h3 className="text-lg font-bold text-white">
                {session.status === 'processing' ? 'Processing Video With RipVIS Model...' : 'Queued for Analysis...'}
              </h3>
              <p className="text-sm text-slate-400 max-w-md mx-auto">
                Running U-Net segmentation on sampled frames, calculating confidence distributions, and merging temporal detection windows.
              </p>
              <div className="text-xs text-sky-400 animate-pulse font-mono">Status: {session.status.toUpperCase()}</div>
            </div>
          )}
        </div>
      )}

      {/* Main Analysis View when Done */}
      {session.status === 'done' && (
        <div className="space-y-6">
          {/* Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl">
              <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Overall Risk Level</div>
              <div className="mt-2 flex items-center space-x-2">
                <span
                  className={`text-2xl font-bold uppercase ${
                    session.overall_risk_level === 'high'
                      ? 'text-rose-400'
                      : session.overall_risk_level === 'medium'
                      ? 'text-amber-400'
                      : 'text-emerald-400'
                  }`}
                >
                  {session.overall_risk_level || 'Low'}
                </span>
                <span className="text-xs text-slate-400 font-mono">
                  (Peak conf: {(maxConfidence * 100).toFixed(1)}%)
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-1">
                Derived from sustained model confidence over sampled timeline
              </p>
            </div>

            <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl">
              <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Detected Rip Windows</div>
              <div className="mt-2 text-2xl font-bold text-white">
                {detections.length}{' '}
                <span className="text-sm font-normal text-slate-400">
                  {detections.length === 1 ? 'window flagged' : 'windows flagged'}
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-1">
                High-confidence spatio-temporal clusters merged via inference post-processor
              </p>
            </div>

            <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl">
              <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Surveillance Source</div>
              <div className="mt-2 text-base font-semibold text-slate-200 truncate">{session.filename}</div>
              <p className="text-xs text-slate-400 mt-1">
                {session.location_label || 'Location not specified'}
              </p>
            </div>
          </div>

          {/* Video Player Section */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl">
            <div className="relative bg-black aspect-video flex items-center justify-center">
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
            </div>

            {/* Interactive Timeline Strip */}
            <div className="p-6 border-t border-slate-800 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-semibold text-sm text-slate-200">Risk Timeline Strip</h3>
                  <p className="text-xs text-slate-400">
                    Click anywhere along the timeline to seek video to that timestamp. Bars show model confidence per sampled frame.
                  </p>
                </div>
                <div className="text-xs font-mono text-slate-400">
                  Time: {currentTime.toFixed(1)}s / {duration.toFixed(1)}s
                </div>
              </div>

              {/* Graphical Timeline Bar */}
              <div className="space-y-1">
                <div className="relative h-16 bg-slate-950 border border-slate-800 rounded-xl overflow-hidden flex items-end px-2 py-1">
                  {/* Current playback needle */}
                  {duration > 0 && (
                    <div
                      className="absolute top-0 bottom-0 w-0.5 bg-sky-400 z-10 shadow-[0_0_8px_rgba(56,189,248,0.8)]"
                      style={{ left: `${(currentTime / duration) * 100}%` }}
                    />
                  )}

                  {timeline.map((point, idx) => {
                    const isHigh = point.confidence >= 0.7;
                    const isMed = point.confidence >= 0.4 && point.confidence < 0.7;
                    const heightPercent = Math.max(8, point.confidence * 100);

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
                              : 'bg-emerald-500/70 group-hover:bg-emerald-400'
                          }`}
                        />
                      </div>
                    );
                  })}
                </div>

                <div className="flex justify-between text-[10px] text-slate-500 font-mono px-1">
                  <span>0.0s</span>
                  <span>Duration: {duration.toFixed(1)}s</span>
                </div>
              </div>

              {/* Confidence Legend */}
              <div className="flex items-center space-x-6 text-xs text-slate-400 pt-1">
                <span className="flex items-center">
                  <span className="w-2.5 h-2.5 rounded-full bg-rose-500 mr-2" />
                  High Confidence (≥70%)
                </span>
                <span className="flex items-center">
                  <span className="w-2.5 h-2.5 rounded-full bg-amber-500 mr-2" />
                  Medium Confidence (40–69%)
                </span>
                <span className="flex items-center">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 mr-2" />
                  Low Confidence (&lt;40%)
                </span>
              </div>
            </div>
          </div>

          {/* Detections List */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
            <h3 className="font-semibold text-base text-slate-100">
              Flagged Detection Windows ({detections.length})
            </h3>
            {detections.length === 0 ? (
              <div className="text-sm text-slate-400 italic">
                No sustained high-confidence rip current windows detected above threshold.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {detections.map((det, index) => (
                  <div
                    key={det.id || index}
                    className="p-4 rounded-xl bg-slate-950 border border-slate-800 hover:border-slate-700 transition-colors flex items-center justify-between"
                  >
                    <div>
                      <div className="text-xs font-semibold uppercase text-slate-400">
                        Window #{index + 1}
                      </div>
                      <div className="text-sm font-mono text-slate-200 mt-1">
                        {det.start_timestamp_sec.toFixed(1)}s — {det.end_timestamp_sec.toFixed(1)}s
                      </div>
                      <div className="text-xs text-rose-400 font-semibold mt-1">
                        Model Confidence: {(det.confidence * 100).toFixed(1)}%
                      </div>
                      {det.bounding_region && (
                        <div className="text-[11px] text-slate-500 font-mono mt-0.5">
                          Region: [x={det.bounding_region.x.toFixed(2)}, y={det.bounding_region.y.toFixed(2)}, w={det.bounding_region.w.toFixed(2)}, h={det.bounding_region.h.toFixed(2)}]
                        </div>
                      )}
                    </div>
                    <button
                      onClick={() => jumpToTime(det.start_timestamp_sec)}
                      className="px-3 py-1.5 rounded-lg bg-sky-500/20 text-sky-400 border border-sky-500/30 text-xs font-medium hover:bg-sky-500/30 transition-colors"
                    >
                      Jump to Time
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
