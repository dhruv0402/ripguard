import React, { useState, useEffect } from 'react';
import { Camera, Radio, Activity, RefreshCw } from 'lucide-react';
import { DisclaimerBanner } from '../components/Navbar';
import { apiFetch, getStreamFeedUrl } from '../api';

interface Telemetry {
  status: string;
  confidence: number | null;
  risk_level: string;
  fps: number;
  timestamp: number;
  error?: string;
}

interface AlertItem {
  id: string;
  type: string;
  priority: string;
  confidence: number;
  sustained_duration_sec: number;
  timestamp: string;
  message: string;
}

export const LiveStreamScreen: React.FC = () => {
  const [streamSource, setStreamSource] = useState<string>('test_assets/beach_ripvis_072.mp4');
  const [appliedSource, setAppliedSource] = useState(streamSource);
  const [activeUrl, setActiveUrl] = useState<string>(() => getStreamFeedUrl('test_assets/beach_ripvis_072.mp4'));
  const [telemetry, setTelemetry] = useState<Telemetry>({
    status: 'connecting',
    confidence: null,
    risk_level: 'UNKNOWN',
    fps: 0,
    timestamp: Date.now() / 1000,
  });
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [webhookUrl, setWebhookUrl] = useState<string>('');
  const [webhookSuccess, setWebhookSuccess] = useState<boolean>(false);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    let controller: AbortController;
    const poll = async () => {
      controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 10000);
      try {
        const data = await apiFetch(`/api/stream/status?source=${encodeURIComponent(appliedSource)}`, {
          signal: controller.signal,
        });
        if (!cancelled) setTelemetry(data);
      } catch {
        if (!cancelled) setTelemetry({ status: 'offline', confidence: null, risk_level: 'UNKNOWN', fps: 0, timestamp: 0 });
      } finally {
        clearTimeout(timeout);
      }
      if (cancelled) return;
      const alertsTimeout = setTimeout(() => controller.abort(), 10000);
      try {
        const alertData = await apiFetch('/api/stream/alerts', { signal: controller.signal });
        if (!cancelled) setAlerts(alertData.alerts || []);
      } catch {
        if (!cancelled) setAlerts([]);
      } finally {
        clearTimeout(alertsTimeout);
      }
      if (!cancelled) timer = setTimeout(poll, 1200);
    };
    void poll();
    return () => { cancelled = true; clearTimeout(timer); controller?.abort(); };
  }, [appliedSource]);

  const hasMeasurement = telemetry.status === 'streaming'
    && !telemetry.error
    && typeof telemetry.confidence === 'number'
    && Number.isFinite(telemetry.confidence)
    && telemetry.confidence >= 0 && telemetry.confidence <= 1
    && ['LOW', 'MEDIUM', 'HIGH'].includes(telemetry.risk_level);
  const confidence = hasMeasurement ? telemetry.confidence : null;
  const confidenceText = confidence === null ? 'Unavailable' : `${(confidence * 100).toFixed(1)}%`;
  const riskLevel = hasMeasurement ? telemetry.risk_level : 'UNKNOWN';
  const feedStatus = hasMeasurement ? 'ANALYSIS ACTIVE'
    : telemetry.error === 'model_unavailable' ? 'MODEL UNAVAILABLE'
    : telemetry.status === 'connecting' || telemetry.status === 'initializing' ? 'CONNECTING'
    : 'ANALYSIS UNAVAILABLE';

  const handleRegisterWebhook = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!webhookUrl) return;
    try {
      await apiFetch(`/api/stream/alerts/webhook?url=${encodeURIComponent(webhookUrl)}`, {
        method: 'POST',
      });
      setWebhookSuccess(true);
      setTimeout(() => setWebhookSuccess(false), 3000);
    } catch {
      // error handling
    }
  };

  const handleApplySource = (e: React.FormEvent) => {
    e.preventDefault();
    setTelemetry({ status: 'connecting', confidence: null, risk_level: 'UNKNOWN', fps: 0, timestamp: 0 });
    setAlerts([]);
    setAppliedSource(streamSource);
    setActiveUrl(getStreamFeedUrl(streamSource));
  };


  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <span className="flex h-3 w-3 relative">

              <span className="relative inline-flex rounded-full h-3 w-3 bg-slate-500"></span>
            </span>
            <h1 className="text-2xl font-bold text-white tracking-tight flex items-center">
              Live Coastal Stream Ingestion
            </h1>
          </div>
          <p className="text-slate-400 text-sm mt-1">
            RTSP/webcam feed analysis. Detection requires an available model and stream.
          </p>
        </div>

        {/* Source selector */}
        <form onSubmit={handleApplySource} className="flex items-center space-x-2">
          <input
            type="text"
            value={streamSource}
            onChange={(e) => setStreamSource(e.target.value)}
            placeholder="RTSP URL or video path (e.g. 0 for webcam)"
            className="bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded-lg px-3 py-2 w-64 focus:outline-none focus:border-sky-500"
          />
          <button
            type="submit"
            className="bg-sky-500 hover:bg-sky-600 text-white text-xs font-medium px-3 py-2 rounded-lg flex items-center space-x-1"
          >
            <RefreshCw className="w-3.5 h-3.5 mr-1" />
            Switch Feed
          </button>
        </form>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Stream Video Container */}
        <div className="lg:col-span-3 bg-slate-900 border border-slate-800 rounded-xl overflow-hidden relative shadow-2xl">
          <div className="aspect-video bg-black flex items-center justify-center relative">
            <img
              key={activeUrl}
              src={activeUrl}
              alt="Live coastal rip current analysis stream"
              className="w-full h-full object-contain"
              onError={(e) => {
                // If stream is still loading or disconnected
                e.currentTarget.style.display = 'none';
              }}
            />

            {/* Overlaid Live Badges */}
            <div className="absolute top-4 left-4 flex items-center space-x-2 bg-slate-950/80 backdrop-blur px-3 py-1.5 rounded-lg border border-slate-800 text-xs">
              <Radio className="w-3.5 h-3.5 text-slate-400" />
              <span className="text-slate-200 font-semibold uppercase tracking-wider">{feedStatus}</span>
              <span className="text-slate-500">|</span>
              <span className="text-slate-300 font-mono">{hasMeasurement && Number.isFinite(telemetry.fps) ? `${telemetry.fps} FPS` : 'Unavailable'}</span>
            </div>

            <div className="absolute top-4 right-4 flex items-center space-x-2 bg-slate-950/80 backdrop-blur px-3 py-1.5 rounded-lg border border-slate-800 text-xs">
              <span className="text-slate-400">Risk Level:</span>
              <span
                className={`font-bold px-2 py-0.5 rounded ${
                  riskLevel === 'HIGH'
                    ? 'bg-rose-500/20 text-rose-400 border border-rose-500/40'
                    : riskLevel === 'MEDIUM'
                    ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40'
                    : riskLevel === 'LOW'
                    ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                    : 'bg-slate-500/20 text-slate-300 border border-slate-500/40'
                }`}
              >
                {riskLevel}
              </span>
            </div>
          </div>

          <div className="p-4 bg-slate-900/90 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
            <div className="flex items-center space-x-2">
              <Activity className="w-4 h-4 text-sky-400" />
              <span>Engine: <strong className="text-slate-200">Runtime not reported</strong></span>
            </div>
            <div className="font-mono">
              Confidence: <strong className="text-sky-400">{confidenceText}</strong>
            </div>
          </div>
        </div>

        {/* Telemetry Sidebar */}
        <div className="space-y-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
            <h2 className="text-sm font-semibold text-white tracking-wide uppercase">Real-Time Metrics</h2>
            
            <div className="space-y-3">
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-slate-400">Current Confidence</span>
                  <span className="text-sky-400 font-mono">{confidenceText}</span>
                </div>
                <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
                  <div
                    className={`h-2 transition-all duration-300 ${
                      confidence === null ? 'bg-slate-600' : confidence >= 0.70
                        ? 'bg-rose-500'
                        : confidence >= 0.40
                        ? 'bg-amber-400'
                        : 'bg-emerald-400'
                    }`}
                    style={{ width: `${(confidence ?? 0) * 100}%` }}
                  />
                </div>
              </div>

              <div className="pt-2 border-t border-slate-800/80 flex justify-between items-center text-xs">
                <span className="text-slate-400">Processed Ingestion Rate:</span>
                <span className="text-slate-200 font-mono">{hasMeasurement && Number.isFinite(telemetry.fps) ? `${telemetry.fps} FPS` : 'Unavailable'}</span>
              </div>

              <div className="pt-2 border-t border-slate-800/80 flex justify-between items-center text-xs">
                <span className="text-slate-400">Inference Device:</span>
                <span className="text-slate-200 font-medium">Not reported</span>
              </div>

              <div className="pt-2 border-t border-slate-800/80 flex justify-between items-center text-xs">
                <span className="text-slate-400">Temporal Aggregation:</span>
                <span className="text-slate-400 font-medium">Not reported</span>
              </div>
            </div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
            <h2 className="text-sm font-semibold text-white tracking-wide uppercase flex items-center justify-between">
              <span>Lifeguard Alerts ({alerts.length})</span>
              <span className="text-xs font-mono text-rose-400 bg-rose-500/10 px-2 py-0.5 rounded border border-rose-500/20">
                Alert History
              </span>
            </h2>

            {alerts.length === 0 ? (
              <p className="text-xs text-slate-500 italic">No alerts available. This does not indicate safe conditions.</p>
            ) : (
              <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                {alerts.map((alt) => (
                  <div
                    key={alt.id}
                    className="p-2.5 rounded-lg bg-rose-950/30 border border-rose-500/30 text-xs space-y-1"
                  >
                    <div className="flex justify-between items-center text-rose-400 font-semibold">
                      <span>{alt.priority} ALERT</span>
                      <span className="text-slate-400 font-mono text-[10px]">{alt.timestamp}</span>
                    </div>
                    <p className="text-slate-300 text-[11px] leading-relaxed">{alt.message}</p>
                  </div>
                ))}
              </div>
            )}

            {/* Webhook Dispatch Config */}
            <form onSubmit={handleRegisterWebhook} className="pt-2 border-t border-slate-800 space-y-2">
              <span className="text-[11px] text-slate-400 font-medium block">Dispatch Webhook (Slack / Twilio)</span>
              <div className="flex space-x-1.5">
                <input
                  type="url"
                  placeholder="https://hooks.slack.com/services/..."
                  value={webhookUrl}
                  onChange={(e) => setWebhookUrl(e.target.value)}
                  className="bg-slate-950 border border-slate-700 text-slate-300 text-xs rounded px-2 py-1 flex-1 focus:outline-none focus:border-sky-500"
                />
                <button
                  type="submit"
                  className="bg-sky-500 hover:bg-sky-600 text-white text-xs px-2.5 py-1 rounded font-medium"
                >
                  Save
                </button>
              </div>
              {webhookSuccess && (
                <span className="text-[11px] text-emerald-400 block font-medium">✓ Webhook registered</span>
              )}
            </form>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
            <h2 className="text-sm font-semibold text-white tracking-wide uppercase">Tower & Edge Hardware</h2>
            <p className="text-xs text-slate-400">
              Hardware, camera calibration, power use, and sustained throughput have not been verified for this feed.
            </p>
          </div>

          <div className="bg-slate-900/60 border border-slate-800/60 rounded-xl p-4 text-xs text-slate-400 space-y-2">
            <div className="font-semibold text-slate-300 flex items-center space-x-1.5">
              <Camera className="w-4 h-4 text-sky-400" />
              <span>Camera Setup Guide</span>
            </div>
            <p>
              For RTSP beach cams, provide URL formatted as <code className="text-slate-300 bg-slate-800 px-1 py-0.5 rounded">rtsp://user:pass@host:port/h264</code>. For built-in or USB webcams, enter device index <code className="text-slate-300 bg-slate-800 px-1 py-0.5 rounded">0</code>.
            </p>
          </div>
        </div>
      </div>

      <DisclaimerBanner />
    </div>
  );
};
