import React, { useState, useEffect, useRef } from 'react';
import {
  apiFetch,
  getVideoUrl,
  getLiveFeedUrl,
  AnalysisSession,
  submitSessionFeedback,
  getActiveLearningManifest,
  FeedbackType,
} from '../api';
import { DisclaimerBanner } from '../components/Navbar';

import {
  ArrowLeft,
  AlertTriangle,
  ShieldCheck,
  AlertCircle,
  Play,
  RefreshCw,
  Radio,
  MapPin,
  CheckCircle2,
  ThumbsUp,
  ThumbsDown,
  Download,
  Activity,
  Check,
} from 'lucide-react';

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

  const [feedbackOpenId, setFeedbackOpenId] = useState<string | null>(null);
  const [feedbackType, setFeedbackType] = useState<FeedbackType>('false_positive_wake');
  const [operatorNotes, setOperatorNotes] = useState<string>('');
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);
  const [feedbackSuccess, setFeedbackSuccess] = useState<string | null>(null);

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

  const handleFeedbackSubmit = async (detectionId: string | null) => {
    try {
      setFeedbackSubmitting(true);
      await submitSessionFeedback(sessionId, {
        detection_id: detectionId,
        feedback_type: feedbackType,
        confidence_rating: 5,
        operator_notes: operatorNotes.trim() || undefined,
      });
      setFeedbackSuccess('Feedback logged for model fine-tuning & active learning.');
      setFeedbackOpenId(null);
      setOperatorNotes('');
      fetchSession();
      setTimeout(() => setFeedbackSuccess(null), 4000);
    } catch (err: any) {
      alert(err.message || 'Failed to submit feedback');
    } finally {
      setFeedbackSubmitting(false);
    }
  };

  const handleQuickConfirm = async (detectionId: string) => {
    try {
      setFeedbackSubmitting(true);
      await submitSessionFeedback(sessionId, {
        detection_id: detectionId,
        feedback_type: 'confirmed_true_positive',
        confidence_rating: 5,
      });
      setFeedbackSuccess('Verified as True Positive rip current.');
      fetchSession();
      setTimeout(() => setFeedbackSuccess(null), 4000);
    } catch (err: any) {
      alert(err.message || 'Failed to submit feedback');
    } finally {
      setFeedbackSubmitting(false);
    }
  };

  const handleDownloadManifest = async () => {
    try {
      const manifest = await getActiveLearningManifest(sessionId);
      const blob = new Blob([JSON.stringify(manifest, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `ripguard_active_learning_${sessionId.slice(0, 8)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      alert(err.message || 'Failed to download manifest');
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

  const effectiveRisk = session.overall_risk_level || (maxConfidence >= 0.68 ? 'high' : maxConfidence >= 0.35 ? 'medium' : 'low');

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
                      src={getLiveFeedUrl(session.id)}
                      alt="Live rip current detection on uploaded video"
                      className="w-full h-full object-contain"
                    />
                  ) : (

                    <video
                      key={session.annotated_video_path || session.id}
                      ref={videoRef}
                      src={getVideoUrl(session.id)}
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

              {/* Detected Time Windows & Operator RLHF Feedback */}
              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-bold text-white flex items-center gap-2">
                    <Activity className="w-4 h-4 text-rose-400" />
                    <span>Rip Channels & Corridors ({detections.length})</span>
                  </h3>
                  {session.status === 'done' && (
                    <button
                      onClick={handleDownloadManifest}
                      title="Export hard-negative mining manifest for model fine-tuning"
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-xs border border-slate-700 transition-colors"
                    >
                      <Download className="w-3.5 h-3.5" />
                      <span>Export Active Learning Manifest</span>
                    </button>
                  )}
                </div>

                {feedbackSuccess && (
                  <div className="p-2.5 rounded-lg bg-emerald-950/60 border border-emerald-800/80 text-emerald-300 text-xs flex items-center gap-2">
                    <Check className="w-4 h-4 text-emerald-400 shrink-0" />
                    <span>{feedbackSuccess}</span>
                  </div>
                )}

                {detections.length === 0 ? (
                  <p className="text-xs text-slate-400 py-2">
                    No dangerous rip currents were detected in this video.
                  </p>
                ) : (
                  <div className="space-y-3">
                    {detections.map((det, index) => {
                      const detFeedback = session.feedback?.filter((f) => f.detection_id === det.id);
                      const isFeedbackOpen = feedbackOpenId === det.id;

                      return (
                        <div
                          key={det.id || index}
                          className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-2.5"
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div>
                              <div className="font-semibold text-sm text-white">
                                {det.start_timestamp_sec.toFixed(1)}s – {det.end_timestamp_sec.toFixed(1)}s
                              </div>
                              <div className="text-xs text-rose-400 mt-0.5">
                                Rip Current Confidence: {(Math.min(0.985, det.confidence) * 100).toFixed(1)}%
                              </div>
                              {det.bounding_region?.corridor_id && (
                                <div className="flex flex-wrap items-center gap-2 mt-1.5 text-[11px] font-mono">
                                  <span className="px-1.5 py-0.5 rounded bg-cyan-950/80 border border-cyan-800 text-cyan-300 font-bold">
                                    Track: {det.bounding_region.corridor_id}
                                  </span>
                                  {det.bounding_region.drift_velocity && (
                                    <span className="text-slate-400">
                                      Drift: <span className="text-white font-semibold">{det.bounding_region.drift_velocity}</span>
                                    </span>
                                  )}
                                  {det.bounding_region.offshore_distance_m != null && (
                                    <span className="text-slate-400">
                                      Position: <span className="text-white font-semibold">{det.bounding_region.offshore_distance_m}m offshore</span>
                                    </span>
                                  )}
                                  {det.bounding_region.gps_coordinates && (
                                    <span className="text-slate-400" title={`GPS: ${det.bounding_region.gps_coordinates.lat}, ${det.bounding_region.gps_coordinates.lon}`}>
                                      GPS: <span className="text-sky-300 font-mono text-[10px]">{det.bounding_region.gps_coordinates.lat.toFixed(4)}, {det.bounding_region.gps_coordinates.lon.toFixed(4)}</span>
                                    </span>
                                  )}
                                </div>
                              )}

                            </div>
                            <button
                              onClick={() => jumpToTime(det.start_timestamp_sec)}
                              className="px-2.5 py-1.5 rounded-lg bg-sky-500/15 text-sky-300 border border-sky-500/30 text-xs hover:bg-sky-500 hover:text-slate-950 transition-all font-semibold flex items-center space-x-1 shrink-0"
                            >
                              <Play className="w-3 h-3 fill-current" />
                              <span>Play</span>
                            </button>
                          </div>

                          {/* Existing feedback tags */}
                          {detFeedback && detFeedback.length > 0 && (
                            <div className="flex flex-wrap gap-1.5 pt-1 border-t border-slate-900">
                              {detFeedback.map((fb) => (
                                <span
                                  key={fb.id}
                                  className={`px-2 py-0.5 rounded text-[10px] font-semibold flex items-center gap-1 ${
                                    fb.feedback_type === 'confirmed_true_positive'
                                      ? 'bg-emerald-950 border border-emerald-800 text-emerald-300'
                                      : 'bg-amber-950 border border-amber-800 text-amber-300'
                                  }`}
                                >
                                  {fb.feedback_type === 'confirmed_true_positive' ? '✓ Confirmed Rip' : `⚠ False Alarm (${fb.feedback_type.replace('false_positive_', '')})`}
                                </span>
                              ))}
                            </div>
                          )}

                          {/* Lifeguard verification buttons */}
                          <div className="pt-2 border-t border-slate-900 flex items-center justify-between text-xs">
                            <span className="text-[11px] text-slate-500">Lifeguard Validation:</span>
                            <div className="flex items-center gap-1.5">
                              <button
                                onClick={() => handleQuickConfirm(det.id)}
                                disabled={feedbackSubmitting}
                                title="Confirm this detection is a real rip current"
                                className="px-2 py-1 rounded bg-slate-900 hover:bg-emerald-950 hover:text-emerald-300 text-slate-400 border border-slate-800 hover:border-emerald-700 transition-colors flex items-center gap-1 text-[11px]"
                              >
                                <ThumbsUp className="w-3 h-3" />
                                <span>Confirm Rip</span>
                              </button>
                              <button
                                onClick={() => setFeedbackOpenId(isFeedbackOpen ? null : det.id)}
                                disabled={feedbackSubmitting}
                                title="Flag false alarm (boat wake, sandbar, wave break)"
                                className={`px-2 py-1 rounded border transition-colors flex items-center gap-1 text-[11px] ${
                                  isFeedbackOpen
                                    ? 'bg-amber-950 text-amber-300 border-amber-700'
                                    : 'bg-slate-900 hover:bg-amber-950 hover:text-amber-300 text-slate-400 border-slate-800 hover:border-amber-700'
                                }`}
                              >
                                <ThumbsDown className="w-3 h-3" />
                                <span>Flag False Alarm</span>
                              </button>
                            </div>
                          </div>

                          {/* Interactive feedback panel */}
                          {isFeedbackOpen && (
                            <div className="mt-2.5 p-3 rounded-lg bg-slate-900/90 border border-slate-800 space-y-2.5">
                              <div className="text-[11px] font-semibold text-slate-300">
                                False Alarm Cause (Hard Negative Mining):
                              </div>
                              <select
                                value={feedbackType}
                                onChange={(e) => setFeedbackType(e.target.value as FeedbackType)}
                                className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-amber-500"
                              >
                                <option value="false_positive_wake">Boat / Jet Ski Wake Churn</option>
                                <option value="false_positive_sandbar">Sandbar / Shallow Reef Shadow</option>
                                <option value="false_positive_wave_break">Uniform Wave Break Turbulence</option>
                                <option value="false_positive_other">Other False Positive</option>
                              </select>
                              <input
                                type="text"
                                placeholder="Operator notes (e.g., wake from fishing trawler at 12s)"
                                value={operatorNotes}
                                onChange={(e) => setOperatorNotes(e.target.value)}
                                className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-amber-500"
                              />
                              <div className="flex justify-end gap-2 pt-1">
                                <button
                                  onClick={() => setFeedbackOpenId(null)}
                                  className="px-2 py-1 rounded text-slate-400 hover:text-white text-xs"
                                >
                                  Cancel
                                </button>
                                <button
                                  onClick={() => handleFeedbackSubmit(det.id)}
                                  disabled={feedbackSubmitting}
                                  className="px-3 py-1 rounded bg-amber-500 hover:bg-amber-400 text-slate-950 font-semibold text-xs transition-colors"
                                >
                                  {feedbackSubmitting ? 'Saving...' : 'Submit Feedback'}
                                </button>
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
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
