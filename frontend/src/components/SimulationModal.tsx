import React, { useEffect, useState } from 'react';
import { Play, X, Film, Sparkles } from 'lucide-react';

interface SimulationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSimulationLaunched: () => void;
}

export const SimulationModal: React.FC<SimulationModalProps> = ({
  isOpen,
  onClose,
  onSimulationLaunched
}) => {
  const [availableVideos, setAvailableVideos] = useState<string[]>([]);
  const [selectedVideo, setSelectedVideo] = useState<string>('');
  const [droneName, setDroneName] = useState<string>('');
  const [isLaunching, setIsLaunching] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    if (isOpen) {
      fetch('/api/v1/simulations/videos')
        .then((res) => res.json())
        .then((data) => {
          if (data.videos && Array.isArray(data.videos)) {
            setAvailableVideos(data.videos);
            if (data.videos.length > 0) {
              setSelectedVideo(data.videos[0]);
              setDroneName(`Simulated Drone ${data.videos[0].replace('.MP4', '')}`);
            }
          }
        })
        .catch((err) => console.error('Failed to list simulation videos:', err));
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleLaunch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedVideo || !droneName) return;

    setIsLaunching(true);
    setErrorMsg('');

    try {
      const res = await fetch('/api/v1/simulations/launch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          drone_name: droneName,
          source_file: selectedVideo
        })
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || 'Failed to launch RTSP simulation');
      }

      setIsLaunching(false);
      onSimulationLaunched();
      onClose();
    } catch (err: any) {
      setIsLaunching(false);
      setErrorMsg(err.message || 'Simulation launch error');
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
          <div className="bg-gradient-to-tr from-cyan-500 to-blue-600 p-2.5 rounded-xl text-white shadow-lg shadow-cyan-500/20">
            <Film className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-slate-100">
              RTSP Test & Simulation Suite
            </h3>
            <p className="text-xs text-slate-400">
              Stream local archived MP4 videos as live RTSP feeds for offline AI testing.
            </p>
          </div>
        </div>

        {errorMsg && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 text-red-400 rounded-xl text-xs font-mono">
            {errorMsg}
          </div>
        )}

        <form onSubmit={handleLaunch} className="flex flex-col gap-4">
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1.5">
              Select Test MP4 Video File
            </label>
            <select
              value={selectedVideo}
              onChange={(e) => {
                setSelectedVideo(e.target.value);
                setDroneName(`Simulated Drone ${e.target.value.replace('.MP4', '')}`);
              }}
              className="w-full bg-[#0B0F17] border border-[#212D40] rounded-xl px-3.5 py-2.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500/50 font-mono"
            >
              {availableVideos.map((vid) => (
                <option key={vid} value={vid}>
                  {vid}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1.5">
              Simulated Drone Designation Name
            </label>
            <input
              type="text"
              value={droneName}
              onChange={(e) => setDroneName(e.target.value)}
              placeholder="e.g. North Gate Test Drone"
              className="w-full bg-[#0B0F17] border border-[#212D40] rounded-xl px-3.5 py-2.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500/50 font-mono"
              required
            />
          </div>

          <div className="bg-[#0B0F17] border border-[#212D40] rounded-xl p-3.5 text-xs text-slate-400 flex items-start gap-2.5">
            <Sparkles className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5" />
            <p className="leading-relaxed">
              Clicking launch will start a continuous simulated video feed from GCS and run real-time Gemini AI visual analysis.
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
              disabled={isLaunching}
              className="bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-semibold text-xs px-5 py-2.5 rounded-xl shadow-lg shadow-cyan-500/20 transition-all flex items-center gap-2 border border-cyan-400/30 disabled:opacity-50"
            >
              <Play className="w-4 h-4" />
              <span>{isLaunching ? 'Provisioning Stream...' : 'Launch Test Stream'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
