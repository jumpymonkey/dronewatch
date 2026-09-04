import React, { useState } from 'react';
import { Radio, X, Video } from 'lucide-react';

interface AddStreamModalProps {
  isOpen: boolean;
  onClose: () => void;
  onStreamAdded: () => void;
}

export const AddStreamModal: React.FC<AddStreamModalProps> = ({
  isOpen,
  onClose,
  onStreamAdded
}) => {
  const [droneName, setDroneName] = useState('');
  const [rtspUrl, setRtspUrl] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!droneName.trim() || !rtspUrl.trim()) return;

    setIsSubmitting(true);
    setErrorMsg('');

    try {
      const res = await fetch('/api/v1/streams', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          drone_name: droneName.trim(),
          rtsp_url: rtspUrl.trim()
        })
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || 'Failed to add live RTSP drone stream');
      }

      setIsSubmitting(false);
      setDroneName('');
      setRtspUrl('');
      onStreamAdded();
      onClose();
    } catch (err: any) {
      setIsSubmitting(false);
      setErrorMsg(err.message || 'Stream registration error');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
      <div className="bg-[#131A26] border border-[#212D40] rounded-2xl max-w-lg w-full p-6 shadow-2xl relative">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-[#1E293B]"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-3 mb-4">
          <div className="bg-gradient-to-tr from-emerald-500 to-teal-600 p-2.5 rounded-xl text-white shadow-lg shadow-emerald-500/20">
            <Radio className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-slate-100">
              Add Live RTSP Drone Stream
            </h3>
            <p className="text-xs text-slate-400">
              Register an active IP camera or RTSP stream feed for real-time Gemini AI monitoring.
            </p>
          </div>
        </div>

        {errorMsg && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 text-red-400 rounded-xl text-xs font-mono">
            {errorMsg}
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1.5">
              Drone Designation / Sector Name
            </label>
            <input
              type="text"
              value={droneName}
              onChange={(e) => setDroneName(e.target.value)}
              placeholder="e.g. Perimeter Guard Alpha"
              className="w-full bg-[#0B0F17] border border-[#212D40] rounded-xl px-3.5 py-2.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500/50 font-mono"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1.5">
              RTSP Camera Stream URL
            </label>
            <input
              type="text"
              value={rtspUrl}
              onChange={(e) => setRtspUrl(e.target.value)}
              placeholder="rtsp://10.0.0.50:8554/live or rtsp://admin:pass@ip:554/stream1"
              className="w-full bg-[#0B0F17] border border-[#212D40] rounded-xl px-3.5 py-2.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500/50 font-mono"
              required
            />
          </div>

          <div className="bg-[#0B0F17] border border-[#212D40] rounded-xl p-3.5 text-xs text-slate-400 flex items-start gap-2.5">
            <Video className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
            <p className="leading-relaxed">
              The backend will connect to the RTSP URL, transcode video frames, and run real-time Vertex AI Gemini visual surveillance.
            </p>
          </div>

          <div className="flex items-center justify-end gap-3 mt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-xs font-semibold text-slate-400 hover:text-slate-200 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-semibold text-xs px-5 py-2.5 rounded-xl shadow-lg shadow-emerald-500/20 transition-all flex items-center gap-2 border border-emerald-400/30 disabled:opacity-50"
            >
              <Radio className="w-4 h-4" />
              <span>{isSubmitting ? 'Registering Stream...' : 'Connect Drone Stream'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
