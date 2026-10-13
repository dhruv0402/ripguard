import React, { useState, useEffect } from 'react';
import { Camera, Radio, AlertTriangle, ShieldCheck, Activity, RefreshCw } from 'lucide-react';
import { DisclaimerBanner } from '../components/Navbar';

interface Telemetry {
  status: string;
  confidence: number;
  risk_level: string;
  fps: number;
  timestamp: number;
}

export const LiveStreamScreen: React.FC = () => {
  const [streamSource, setStreamSource] = useState<string>('test_assets/beach_ripvis_072.mp4');
  const [activeUrl, setActiveUrl] = useState<string>('/api/stream/feed?source=test_assets/beach_ripvis_072.mp4');
  const [telemetry, setTelemetry] = useState<Telemetry>({
    status: 'connecting',
    confidence: 0,
    risk_level: 'LOW',
    fps: 0,
    timestamp: Date.now() / 1000,
  });

  useEffect(() => {
    // Poll telemetry status every 500ms
    const interval = setInterval(async () => {
      try {
        const res = await fetch('/api/stream/status');
        if (res.ok) {
          const data = await res.json();
          setTelemetry(data);
        }
      } catch {
        // stream might be starting
      }
    }, 500);

    return () => clearInterval(interval);
  }, []);

  const handleApplySource = (e: React.FormEvent) => {
    e.preventDefault();
    setActiveUrl(`/api/stream/feed?source=${encodeURIComponent(streamSource)}&t=${Date.now()}`);
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <span className="flex h-3 w-3 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-rose-500"></span>
            </span>
            <h1 className="text-2xl font-bold text-white tracking-tight flex items-center">
              Live Coastal Stream Ingestion
            </h1>
          </div>
          <p className="text-slate-400 text-sm mt-1">
            Real-time RTSP/webcam feed analysis powered by ONNX Runtime edge inference engine.
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
              <Radio className="w-3.5 h-3.5 text-rose-500 animate-pulse" />
              <span className="text-slate-200 font-semibold uppercase tracking-wider">LIVE FEED</span>
              <span className="text-slate-500">|</span>
              <span className="text-emerald-400 font-mono">{telemetry.fps} FPS</span>
            </div>

            <div className="absolute top-4 right-4 flex items-center space-x-2 bg-slate-950/80 backdrop-blur px-3 py-1.5 rounded-lg border border-slate-800 text-xs">
              <span className="text-slate-400">Risk Level:</span>
              <span
                className={`font-bold px-2 py-0.5 rounded ${
                  telemetry.risk_level === 'HIGH'
                    ? 'bg-rose-500/20 text-rose-400 border border-rose-500/40'
                    : telemetry.risk_level === 'MEDIUM'
                    ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40'
                    : 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                }`}
              >
                {telemetry.risk_level}
              </span>
            </div>
          </div>

          <div className="p-4 bg-slate-900/90 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
            <div className="flex items-center space-x-2">
              <Activity className="w-4 h-4 text-sky-400" />
              <span>Engine: <strong className="text-slate-200">ONNX Runtime (CoreML / CPU EP)</strong></span>
            </div>
            <div className="font-mono">
              Confidence: <strong className="text-sky-400">{(telemetry.confidence * 100).toFixed(1)}%</strong>
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
                  <span className="text-sky-400 font-mono">{(telemetry.confidence * 100).toFixed(1)}%</span>
                </div>
                <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
                  <div
                    className={`h-2 transition-all duration-300 ${
                      telemetry.confidence >= 0.70
                        ? 'bg-rose-500'
                        : telemetry.confidence >= 0.40
                        ? 'bg-amber-400'
                        : 'bg-emerald-400'
                    }`}
                    style={{ width: `${Math.min(100, telemetry.confidence * 100)}%` }}
                  />
                </div>
              </div>

              <div className="pt-2 border-t border-slate-800/80 flex justify-between items-center text-xs">
                <span className="text-slate-400">Processed Ingestion Rate:</span>
                <span className="text-slate-200 font-mono">{telemetry.fps} FPS</span>
              </div>

              <div className="pt-2 border-t border-slate-800/80 flex justify-between items-center text-xs">
                <span className="text-slate-400">Inference Device:</span>
                <span className="text-slate-200 font-medium">Apple Silicon MPS / CoreML</span>
              </div>

              <div className="pt-2 border-t border-slate-800/80 flex justify-between items-center text-xs">
                <span className="text-slate-400">Temporal Aggregation:</span>
                <span className="text-emerald-400 font-medium">TCA (α=0.65) Active</span>
              </div>
            </div>
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
