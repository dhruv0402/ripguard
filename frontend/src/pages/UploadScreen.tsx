import React, { useState, useEffect } from 'react';
import { apiFetch } from '../api';
import { UploadCloud, Video, MapPin, AlertCircle, ArrowLeft, Play, AlertTriangle, ShieldCheck, XCircle } from 'lucide-react';

interface UploadScreenProps {
  onSessionCreated: (sessionId: string) => void;
  onCancel: () => void;
}

interface TestAssetItem {
  filename: string;
  title: string;
  category: string;
  location: string;
  size_mb: number;
}

export const UploadScreen: React.FC<UploadScreenProps> = ({ onSessionCreated, onCancel }) => {
  const [file, setFile] = useState<File | null>(null);
  const [locationLabel, setLocationLabel] = useState('');
  const [loading, setLoading] = useState(false);
  const [runningAsset, setRunningAsset] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [testAssets, setTestAssets] = useState<TestAssetItem[]>([]);

  useEffect(() => {
    fetch('/api/sessions/test-assets/list')
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => {
        if (Array.isArray(data)) setTestAssets(data);
      })
      .catch(() => {});
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setError('Please select a coastal video file to analyze.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('file', file);
      if (locationLabel.trim()) {
        formData.append('location_label', locationLabel.trim());
      }

      const res = await apiFetch('/api/sessions', {
        method: 'POST',
        body: formData,
      });

      onSessionCreated(res.id);
    } catch (err: any) {
      setError(err.message || 'Video upload failed');
      setLoading(false);
    }
  };

  const handleRunTestAsset = async (asset: TestAssetItem) => {
    setRunningAsset(asset.filename);
    setError(null);
    try {
      const formData = new FormData();
      formData.append('filename', asset.filename);
      formData.append('location_label', asset.location);
      const res = await apiFetch('/api/sessions/test-assets/run', {
        method: 'POST',
        body: formData,
      });
      onSessionCreated(res.id);
    } catch (err: any) {
      setError(err.message || 'Failed to launch test video');
      setRunningAsset(null);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <div className="flex items-center space-x-3">
        <button
          onClick={onCancel}
          className="p-2 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 hover:text-white transition-colors"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Upload or Select a Beach Video</h1>
          <p className="text-sm text-slate-400 mt-0.5">
            Upload your own video file from disk, or click any pre-loaded video from <code className="text-sky-400">test_assets/</code> below to watch live rip current detection.
          </p>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-950/50 border border-rose-800 text-rose-300 text-sm flex items-start space-x-2">
          <AlertCircle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* Custom File Upload Form */}
      <form onSubmit={handleSubmit} className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-6 shadow-xl">
        <div>
          <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
            Upload Video File (MP4 / MOV / AVI)
          </label>
          <div className="border-2 border-dashed border-slate-700 hover:border-sky-500 rounded-2xl p-8 text-center transition-colors bg-slate-950/60 relative">
            <input
              type="file"
              accept="video/mp4,video/quicktime,video/x-msvideo"
              onChange={handleFileChange}
              className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            />
            {file ? (
              <div className="space-y-2">
                <div className="w-12 h-12 rounded-full bg-emerald-500/10 text-emerald-400 flex items-center justify-center mx-auto border border-emerald-500/20">
                  <Video className="w-6 h-6" />
                </div>
                <div className="font-semibold text-slate-200 text-sm">{file.name}</div>
                <div className="text-xs text-slate-400">
                  {(file.size / (1024 * 1024)).toFixed(2)} MB • Ready for analysis
                </div>
                <span className="text-xs text-sky-400 hover:underline">Click or drag another file to replace</span>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="w-12 h-12 rounded-full bg-sky-500/10 text-sky-400 flex items-center justify-center mx-auto border border-sky-500/20">
                  <UploadCloud className="w-6 h-6" />
                </div>
                <div>
                  <span className="text-sm font-semibold text-slate-200">Click to browse video from disk</span>
                  <span className="text-sm text-slate-400"> (including any file in </span>
                  <code className="text-xs text-sky-400 bg-slate-900 px-1.5 py-0.5 rounded">test_assets/</code>
                  <span className="text-sm text-slate-400">)</span>
                </div>
                <p className="text-xs text-slate-500">
                  Supports coastal videos up to 500 MB
                </p>
              </div>
            )}
          </div>
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2 flex items-center">
            <MapPin className="w-3.5 h-3.5 mr-1 text-slate-400" />
            Beach / Camera Location (Optional)
          </label>
          <input
            type="text"
            value={locationLabel}
            onChange={(e) => setLocationLabel(e.target.value)}
            placeholder="e.g., Calangute Tower 3, Goa / Baga Beach North Cam"
            className="w-full px-4 py-2.5 rounded-lg bg-slate-950 border border-slate-800 text-slate-100 placeholder-slate-500 text-sm focus:outline-none focus:border-sky-500"
          />
        </div>

        <div className="pt-2 flex items-center justify-end space-x-3">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm font-medium transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={loading || !file}
            className="px-6 py-2.5 rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-950 text-sm font-bold transition-colors shadow-lg shadow-sky-500/20 disabled:opacity-50"
          >
            {loading ? 'Uploading & Starting Detection...' : 'Start Rip Current Detection'}
          </button>
        </div>
      </form>

      {/* 1-Click Test Assets Suite */}
      {testAssets.length > 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4 shadow-xl">
          <div>
            <h2 className="text-lg font-bold text-white">
              Quick Test Suite (<code className="text-sky-400 text-sm">test_assets/</code> — {testAssets.length} Videos Ready)
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Click <strong>Run Live Detection</strong> on any test video below to immediately ingest it and watch frame-by-frame rip current detection.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {testAssets.map((asset) => {
              const isHigh = asset.category.includes('Strong');
              const isMed = asset.category.includes('Moderate');
              const isOod = asset.category.includes('Out-of-Distribution');

              return (
                <div
                  key={asset.filename}
                  className="p-4 rounded-xl bg-slate-950 border border-slate-800 hover:border-slate-700 flex items-center justify-between gap-3 transition-all"
                >
                  <div className="min-w-0 space-y-1">
                    <div className="text-sm font-semibold text-white truncate">{asset.title}</div>
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <span className="font-mono text-slate-400">{asset.filename}</span>
                      <span className="text-slate-600">•</span>
                      <span className="text-slate-400">{asset.size_mb} MB</span>
                    </div>
                    <div className="pt-0.5">
                      {isHigh ? (
                        <span className="inline-flex items-center text-[11px] font-medium text-rose-400">
                          <AlertTriangle className="w-3 h-3 mr-1" /> {asset.category}
                        </span>
                      ) : isMed ? (
                        <span className="inline-flex items-center text-[11px] font-medium text-amber-400">
                          <AlertTriangle className="w-3 h-3 mr-1" /> {asset.category}
                        </span>
                      ) : isOod ? (
                        <span className="inline-flex items-center text-[11px] font-medium text-slate-400">
                          <XCircle className="w-3 h-3 mr-1 text-rose-400" /> {asset.category}
                        </span>
                      ) : (
                        <span className="inline-flex items-center text-[11px] font-medium text-emerald-400">
                          <ShieldCheck className="w-3 h-3 mr-1" /> {asset.category}
                        </span>
                      )}
                    </div>
                  </div>

                  <button
                    type="button"
                    disabled={runningAsset !== null}
                    onClick={() => handleRunTestAsset(asset)}
                    className="px-3.5 py-2 rounded-lg bg-sky-500/15 hover:bg-sky-500 text-sky-300 hover:text-slate-950 border border-sky-500/30 text-xs font-semibold transition-all shrink-0 flex items-center space-x-1.5 disabled:opacity-50"
                  >
                    <Play className="w-3.5 h-3.5 fill-current" />
                    <span>{runningAsset === asset.filename ? 'Starting...' : 'Run Detection'}</span>
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
