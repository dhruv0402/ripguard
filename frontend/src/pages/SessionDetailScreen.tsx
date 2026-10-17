import React, { useState, useEffect, useRef } from 'react';
import { apiFetch, getVideoUrl, AnalysisSession } from '../api';
import { DisclaimerBanner } from '../components/Navbar';
import { ArrowLeft, AlertTriangle, ShieldCheck, AlertCircle, Play, RefreshCw, Radio, MapPin, CheckCircle2 } from 'lucide-react';

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
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const [liveTelemetry, setLiveTelemetry] = useState<{
    frame_idx: number;
    total_frames: number;
    progress_pct: number;
    confidence: number;
    t: number;
    region: { x: number; y: number; w: number; h: number } | null;
    timeline_so_far: { t: number; confidence: number; region?: { x: number; y: number; w: number; h: number } | null }[];
  } | null>(null);

  const fetchSession = async () => {
    try {
      const data = await apiFetch(`/api/sessions/${sessionId}`);
      setSession(data);
      setLoading(false);
    } catch (err: any) {
      setError(err.message || 'Failed to load video analysis');
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSession();
    const interval = setInterval(async () => {
      if (session?.status !== 'done' && session?.status !== 'failed') {
        fetchSession();
        try {
          const liveRes = await fetch(`/api/sessions/${sessionId}/live-telemetry`);
          if (liveRes.ok) {
            const liveData = await liveRes.json();
            if (liveData.telemetry) {
              setLiveTelemetry(liveData.telemetry);
            }
          }
        } catch {
          // ignore transient poll errors
        }
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [sessionId, session?.status]);

  const handleTimeUpdate = () => {
    if (videoRef.current) {
      setCurrentTime(videoRef.current.currentTime);
    }
  };

  const handleLoadedMetadata = () => {
    if (videoRef.current && videoRef.current.duration && isFinite(videoRef.current.duration)) {
      setDuration(videoRef.current.duration);
    }
  };

  const jumpToTime = (timestampSec: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = timestampSec;
      videoRef.current.play();
    }
  };

  if (loading && !session) {
    return (
      <div className="p-16 text-center text-slate-400 space-y-3">
        <RefreshCw className="w-8 h-8 animate-spin mx-auto text-sky-400" />
        <p className="text-sm">Loading video analysis...</p>
      </div>
    );
  }

  if (error || !session) {
    return (
      <div className="space-y-4 max-w-4xl mx-auto">
        <button onClick={onBack} className="inline-flex items-center text-sm text-slate-400 hover:text-white">
          <ArrowLeft className="w-4 h-4 mr-1.5" /> Back to Videos
        </button>
        <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800/60 text-rose-300 text-sm">
          {error || 'Video session not found'}
        </div>
      </div>
    );
  }

  const isProcessing = session.status === 'pending' || session.status === 'processing';
  const timeline = isProcessing && liveTelemetry?.timeline_so_far?.length
    ? liveTelemetry.timeline_so_far
    : (session.risk_timeline || []);
  const maxConfidence = timeline.length > 0
    ? Math.min(0.985, Math.max(...timeline.map((p) => p.confidence)))
    : (liveTelemetry?.confidence || 0);
  const detections = session.detections || [];
  const effectiveDuration = duration > 0
    ? duration
    : (timeline.length > 0 ? timeline[timeline.length - 1].t : 0);

  const effectiveRisk = session.overall_risk_level || (maxConfidence >= 0.7 ? 'high' : maxConfidence >= 0.4 ? 'medium' : 'low');

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Top Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-800">
        <div className="flex items-center space-x-3">
          <button
            onClick={onBack}
            className="px-3 py-2 rounded-lg bg-slate-900 border border-slate-800 text-slate-300 hover:text-white hover:border-slate-700 transition-all flex items-center space-x-1.5 text-sm font-medium"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Back</span>
          </button>
          <div>
            <h1 className="text-xl font-bold text-white tracking-tight">
              {session.filename}
            </h1>
            {session.location_label && (
              <p className="text-xs text-slate-400 flex items-center mt-0.5">
                <MapPin className="w-3.5 h-3.5 mr-1 text-sky-400" />
                {session.location_label}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Rejected / Failed Video State */}
      {session.status === 'failed' && (
        <div className="bg-slate-900 border border-rose-500/30 rounded-2xl p-8 text-center space-y-4">
          <div className="w-12 h-12 rounded-full bg-rose-500/10 text-rose-400 flex items-center justify-center mx-auto border border-rose-500/20">
            <AlertCircle className="w-6 h-6" />
          </div>
          <h2 className="text-lg font-bold text-white">Video Rejected: Not a Beach or Ocean Video</h2>
          <p className="text-sm text-rose-300 max-w-xl mx-auto bg-rose-950/30 p-4 rounded-xl border border-rose-500/20">
            {session.error_message || 'This file does not appear to be coastal surf footage. Please upload a beach or ocean video.'}
          </p>
        </div>
      )}

      {/* Live Processing Progress Banner */}
      {isProcessing && (
        <div className="bg-sky-950/40 border border-sky-500/40 rounded-xl p-4 space-y-2">
          <div className="flex items-center justify-between text-sm">
            <div className="flex items-center space-x-2 text-sky-300 font-semibold">
              <Radio className="w-4 h-4 text-rose-400 animate-pulse" />
              <span>Analyzing Video Live — Detecting Rip Currents Frame by Frame...</span>
            </div>
            <div className="text-sky-300 font-mono text-xs font-bold">
              {liveTelemetry
                ? `Frame ${liveTelemetry.frame_idx} of ${liveTelemetry.total_frames} (${liveTelemetry.progress_pct}%)`
                : 'Starting detector...'}
            </div>
          </div>
          <div className="w-full bg-slate-900 rounded-full h-2 overflow-hidden">
            <div
              className="bg-sky-400 h-2 transition-all duration-300"
              style={{ width: `${liveTelemetry?.progress_pct || 5}%` }}
            />
          </div>
        </div>
      )}

      {/* Main Content when Processing or Done */}
      {(session.status === 'done' || isProcessing) && (
        <div className="space-y-6">
          {/* Plain-English Safety Result Banner */}
          {effectiveRisk === 'high' ? (
            <div className="bg-rose-950/40 border border-rose-500/40 rounded-2xl p-5 flex items-start space-x-4">
              <div className="p-3 rounded-xl bg-rose-500/20 text-rose-400 shrink-0">
                <AlertTriangle className="w-6 h-6" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-rose-300">
                  DANGER: Strong Rip Current Detected ({(maxConfidence * 100).toFixed(1)}% Confidence)
                </h2>
                <p className="text-sm text-slate-300 mt-1">
                  A hazardous outward-flowing rip current channel was detected in this video (highlighted in <strong className="text-rose-300">red</strong> with a <strong className="text-amber-300">yellow outline</strong> on the video below). Swimming in this channel is dangerous.
                </p>
              </div>
            </div>
          ) : effectiveRisk === 'medium' ? (
            <div className="bg-amber-950/40 border border-amber-500/40 rounded-2xl p-5 flex items-start space-x-4">
              <div className="p-3 rounded-xl bg-amber-500/20 text-amber-400 shrink-0">
                <AlertTriangle className="w-6 h-6" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-amber-300">
                  CAUTION: Moderate Rip Current Activity ({(maxConfidence * 100).toFixed(1)}% Confidence)
                </h2>
                <p className="text-sm text-slate-300 mt-1">
                  A moderate offshore current channel was detected in the surf zone (outlined in <strong className="text-amber-300">yellow/red</strong> on the video below). Lifeguards should monitor swimmers near this area.
                </p>
              </div>
            </div>
          ) : (
            <div className="bg-emerald-950/30 border border-emerald-500/40 rounded-2xl p-5 flex items-start space-x-4">
              <div className="p-3 rounded-xl bg-emerald-500/20 text-emerald-400 shrink-0">
                <ShieldCheck className="w-6 h-6" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-emerald-300">
                  SAFE WATER CONDITIONS: No Rip Current Detected
                </h2>
                <p className="text-sm text-slate-300 mt-1">
                  Waves are breaking uniformly toward the shore with no hazardous rip current channels detected.
                </p>
              </div>
            </div>
          )}

          {/* Video Player + Simple Summary Sidebar */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Left 8 Columns: Unobstructed Video Player + Visual Legend + Timeline */}
            <div className="lg:col-span-8 space-y-4">
              <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl">
                {/* Clean Video Player — No blurry boxes blocking the video */}
                <div className="relative bg-black aspect-video flex items-center justify-center">
                  {isProcessing ? (
                    <img
                      src={`/api/sessions/${session.id}/live-feed`}
                      alt="Live rip current detection on uploaded video"
                      className="w-full h-full object-contain"
                    />
                  ) : (
                    <video
                      key={session.annotated_video_path || session.id}
                      ref={videoRef}
                      src={`${getVideoUrl(session.id)}?v=${encodeURIComponent(session.annotated_video_path || session.id)}`}
                      controls
                      autoPlay
                      loop
                      muted
                      playsInline
                      onTimeUpdate={handleTimeUpdate}
                      onLoadedMetadata={handleLoadedMetadata}
                      className="w-full h-full object-contain"
                    />
                  )}
                </div>

                {/* Simple Visual Guide explaining what is drawn on the video */}
                <div className="px-4 py-3 bg-slate-950 border-t border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-300">
                  <div className="font-semibold text-slate-400">What You See on the Video:</div>
                  <div className="flex flex-wrap items-center gap-4">
                    <span className="flex items-center">
                      <span className="w-3 h-3 rounded-sm bg-rose-600 border border-yellow-400 mr-1.5" />
                      <strong>Red Zone / Yellow Outline:</strong> Rip Current Channel
                    </span>
                    <span className="flex items-center">
                      <span className="w-3 h-0.5 bg-cyan-400 mr-1.5" />
                      <strong>Cyan Arrows:</strong> Normal Wave Direction
                    </span>
                    <span className="flex items-center">
                      <span className="w-3 h-0.5 bg-rose-500 mr-1.5" />
                      <strong>Red Arrows:</strong> Outward Rip Current Flow
                    </span>
                  </div>
                </div>

                {/* Clickable Detection Timeline */}
                <div className="p-4 border-t border-slate-800 space-y-2.5 bg-slate-900/60">
                  <div className="flex items-center justify-between text-xs">
                    <div>
                      <span className="font-semibold text-white">Second-by-Second Rip Current Risk</span>
                      <span className="text-slate-400 ml-2">(Click any bar to jump to that moment in the video)</span>
                    </div>
                    <div className="font-mono text-sky-400 font-semibold">
                      {currentTime.toFixed(1)}s / {effectiveDuration.toFixed(1)}s
                    </div>
                  </div>

                  <div className="relative h-12 bg-slate-950 border border-slate-800 rounded-lg overflow-hidden flex items-end px-1 py-1">
                    {effectiveDuration > 0 && (
                      <div
                        className="absolute top-0 bottom-0 w-0.5 bg-sky-400 z-10"
                        style={{ left: `${Math.min(100, (currentTime / effectiveDuration) * 100)}%` }}
                      />
                    )}

                    {timeline.map((point, idx) => {
                      const isHigh = point.confidence >= 0.7;
                      const isMed = point.confidence >= 0.4 && point.confidence < 0.7;
                      const heightPercent = Math.max(12, Math.min(98, point.confidence * 100));

                      return (
                        <div
                          key={idx}
                          onClick={() => jumpToTime(point.t)}
                          title={`Time: ${point.t}s | Rip Current Confidence: ${(point.confidence * 100).toFixed(1)}%`}
                          className="flex-1 mx-[1px] cursor-pointer group flex flex-col justify-end h-full"
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

                  <div className="flex items-center justify-between text-xs text-slate-400 pt-1">
                    <span className="flex items-center">
                      <span className="w-2.5 h-2.5 rounded-full bg-rose-500 mr-1.5" /> Strong Rip Current (High Risk)
                    </span>
                    <span className="flex items-center">
                      <span className="w-2.5 h-2.5 rounded-full bg-amber-500 mr-1.5" /> Moderate Current (Caution)
                    </span>
                    <span className="flex items-center">
                      <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 mr-1.5" /> Calm / Safe Surf
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Right 4 Columns: Plain-English Summary & Timestamps */}
            <div className="lg:col-span-4 space-y-4">
              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-4">
                <h3 className="text-sm font-bold text-white">
                  Analysis Summary
                </h3>

                <div className="space-y-3 text-sm">
                  <div className="flex justify-between items-center py-2 border-b border-slate-800">
                    <span className="text-slate-400">Safety Assessment</span>
                    <span
                      className={`font-bold ${
                        effectiveRisk === 'high'
                          ? 'text-rose-400'
                          : effectiveRisk === 'medium'
                          ? 'text-amber-400'
                          : 'text-emerald-400'
                      }`}
                    >
                      {effectiveRisk === 'high'
                        ? 'Danger (High Risk)'
                        : effectiveRisk === 'medium'
                        ? 'Caution (Moderate)'
                        : 'Safe (Low Risk)'}
                    </span>
                  </div>

                  <div className="flex justify-between items-center py-2 border-b border-slate-800">
                    <span className="text-slate-400">Detection Confidence</span>
                    <span className="text-white font-bold">{(maxConfidence * 100).toFixed(1)}%</span>
                  </div>

                  <div className="flex justify-between items-center py-2 border-b border-slate-800">
                    <span className="text-slate-400">Video Length</span>
                    <span className="text-slate-200">{effectiveDuration.toFixed(1)} seconds</span>
                  </div>

                  <div className="flex justify-between items-center py-2">
                    <span className="text-slate-400">Beach Verification</span>
                    <span className="text-emerald-400 font-medium flex items-center">
                      <CheckCircle2 className="w-4 h-4 mr-1" />
                      Verified Beach Video
                    </span>
                  </div>
                </div>
              </div>

              {/* Detected Time Windows */}
              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-3">
                <h3 className="text-sm font-bold text-white">
                  When Rip Currents Appear ({detections.length})
                </h3>

                {detections.length === 0 ? (
                  <p className="text-xs text-slate-400 py-2">
                    No dangerous rip currents were detected in this video.
                  </p>
                ) : (
                  <div className="space-y-2.5">
                    {detections.map((det, index) => (
                      <div
                        key={det.id || index}
                        className="p-3 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between"
                      >
                        <div>
                          <div className="font-semibold text-sm text-white">
                            {det.start_timestamp_sec.toFixed(1)}s – {det.end_timestamp_sec.toFixed(1)}s
                          </div>
                          <div className="text-xs text-rose-400 mt-0.5">
                            Rip Current Confidence: {(Math.min(0.985, det.confidence) * 100).toFixed(1)}%
                          </div>
                        </div>
                        <button
                          onClick={() => jumpToTime(det.start_timestamp_sec)}
                          className="px-3 py-1.5 rounded-lg bg-sky-500/15 text-sky-300 border border-sky-500/30 text-xs hover:bg-sky-500 hover:text-slate-950 transition-all font-semibold flex items-center space-x-1"
                        >
                          <Play className="w-3 h-3 fill-current" />
                          <span>Play</span>
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

      <DisclaimerBanner />
    </div>
  );
};
