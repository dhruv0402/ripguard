import React, { useState } from 'react';
import { apiFetch } from '../api';
import { UploadCloud, Video, MapPin, AlertCircle, ArrowLeft } from 'lucide-react';

interface UploadScreenProps {
  onSessionCreated: (sessionId: string) => void;
  onCancel: () => void;
}

export const UploadScreen: React.FC<UploadScreenProps> = ({ onSessionCreated, onCancel }) => {
  const [file, setFile] = useState<File | null>(null);
  const [locationLabel, setLocationLabel] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="flex items-center space-x-3">
        <button
          onClick={onCancel}
          className="p-2 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 hover:text-white transition-colors"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">New Surveillance Analysis</h1>
          <p className="text-sm text-slate-400 mt-0.5">
            Upload footage to run the deep U-Net segmentation model
          </p>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-950/50 border border-rose-800 text-rose-300 text-sm flex items-start space-x-2">
          <AlertCircle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-6 shadow-xl">
        {/* Drag and Drop Box */}
        <div>
          <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
            Beach Video Recording (MP4 / MOV / AVI)
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
                <span className="text-xs text-sky-400 hover:underline">Click or drag another to replace</span>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="w-12 h-12 rounded-full bg-sky-500/10 text-sky-400 flex items-center justify-center mx-auto border border-sky-500/20">
                  <UploadCloud className="w-6 h-6" />
                </div>
                <div>
                  <span className="text-sm font-semibold text-slate-200">Click to browse video</span>
                  <span className="text-sm text-slate-400"> or drag and drop</span>
                </div>
                <p className="text-xs text-slate-500">
                  Supports coastal videos up to 500 MB (RipVIS dataset clips or beach cam streams)
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Location metadata */}
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
            className="px-6 py-2.5 rounded-lg bg-sky-500 hover:bg-sky-400 text-white text-sm font-medium transition-colors shadow-lg shadow-sky-500/20 disabled:opacity-50"
          >
            {loading ? 'Uploading & Starting Analysis...' : 'Start Video Analysis'}
          </button>
        </div>
      </form>
    </div>
  );
};
