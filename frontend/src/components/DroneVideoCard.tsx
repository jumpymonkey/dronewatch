import React, { useEffect, useRef, useState } from 'react';
import Hls from 'hls.js';
import { DroneStream, AnalyticsEvent } from '../types';
import { BoundingBoxOverlay } from './BoundingBoxOverlay';
import { Video, ShieldAlert, Cpu, Maximize2, Trash2 } from 'lucide-react';

interface DroneVideoCardProps {
  stream: DroneStream;
  latestEvent?: AnalyticsEvent;
  onFocusStream?: (stream: DroneStream) => void;
  onDeleteStream?: (streamId: string) => void;
}

export const DroneVideoCard: React.FC<DroneVideoCardProps> = ({
  stream,
  latestEvent,
  onFocusStream,
  onDeleteStream
}) => {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);

  // Derive HLS streaming URL from MediaMTX
  const pathKey = stream.source_file
    ? stream.source_file.toLowerCase().replace(/[^a-z0-9]/g, '_')
    : stream.drone_name.toLowerCase().replace(/[^a-z0-9]/g, '_');

  const hlsUrl = `http://localhost:8888/sim/${pathKey}/index.m3u8`;

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    let hls: Hls | null = null;

    if (Hls.isSupported()) {
      hls = new Hls({
        lowLatencyMode: true,
        backBufferLength: 5
      });
      hls.loadSource(hlsUrl);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        video.play().catch(() => {});
        setIsPlaying(true);
      });
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = hlsUrl;
      video.addEventListener('loadedmetadata', () => {
        video.play().catch(() => {});
        setIsPlaying(true);
      });
    }

    return () => {
      if (hls) {
        hls.destroy();
      }
    };
  }, [hlsUrl]);

  const isCritical = latestEvent?.severity === 'CRITICAL';
  const isMedium = latestEvent?.severity === 'MEDIUM';

  return (
    <div
      className={`relative group bg-[#131A26] rounded-2xl overflow-hidden border transition-all duration-300 ${
        isCritical
          ? 'border-red-500 shadow-xl shadow-red-500/30 animate-pulse-glow'
          : isMedium
          ? 'border-amber-500/60 shadow-lg shadow-amber-500/10'
          : 'border-[#212D40] hover:border-slate-600'
      }`}
    >
      {/* Header Overlay */}
      <div className="absolute top-0 inset-x-0 z-30 p-3 flex items-center justify-between bg-gradient-to-b from-black/80 via-black/40 to-transparent">
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 bg-black/60 backdrop-blur-md px-2.5 py-1 rounded-lg border border-white/10 text-xs font-semibold">
            <Video className="w-3.5 h-3.5 text-cyan-400" />
            <span>{stream.drone_name}</span>
          </div>

          {stream.is_simulation && (
            <span className="bg-purple-500/20 text-purple-300 border border-purple-500/30 px-2 py-0.5 rounded-md text-[10px] font-mono">
              SIMULATED
            </span>
          )}
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
          {onFocusStream && (
            <button
              onClick={() => onFocusStream(stream)}
              className="p-1.5 bg-black/60 hover:bg-cyan-600 text-white rounded-lg border border-white/10 transition-colors"
              title="Focus Stream"
            >
              <Maximize2 className="w-3.5 h-3.5" />
            </button>
          )}
          {onDeleteStream && (
            <button
              onClick={() => onDeleteStream(stream.stream_id)}
              className="p-1.5 bg-black/60 hover:bg-red-600 text-white rounded-lg border border-white/10 transition-colors"
              title="Remove Stream"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Video Container */}
      <div className="relative aspect-video bg-black flex items-center justify-center overflow-hidden">
        <video
          ref={videoRef}
          muted
          playsInline
          className="w-full h-full object-cover"
        />

        {/* Bounding Box Overlay Canvas */}
        <BoundingBoxOverlay
          boundingBoxes={latestEvent?.bounding_boxes || []}
          severity={latestEvent?.severity}
        />

        {/* Fallback Simulation Banner if video offline */}
        {!isPlaying && (
          <div className="absolute inset-0 bg-slate-950/80 flex flex-col items-center justify-center p-4 text-center">
            <Cpu className="w-8 h-8 text-cyan-500/60 mb-2 animate-spin" />
            <p className="text-xs text-slate-400 font-mono">
              Connecting RTSP Stream...
            </p>
            <p className="text-[10px] text-slate-500 mt-1 font-mono break-all px-4">
              {stream.rtsp_url}
            </p>
          </div>
        )}
      </div>

      {/* Footer Info & Gemini Insight */}
      <div className="p-3 bg-[#131A26] border-t border-[#212D40] flex flex-col gap-1.5">
        <div className="flex items-center justify-between text-xs">
          <span className="flex items-center gap-1 font-mono text-[11px] text-slate-400">
            <span className={`w-2 h-2 rounded-full ${stream.status === 'ACTIVE' ? 'bg-emerald-500' : 'bg-amber-500'}`}></span>
            {stream.status}
          </span>

          {latestEvent && (
            <span
              className={`px-2 py-0.5 rounded-full font-mono text-[10px] font-bold uppercase tracking-wider ${
                isCritical
                  ? 'bg-red-500/20 text-red-400 border border-red-500/40'
                  : isMedium
                  ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40'
                  : 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
              }`}
            >
              {latestEvent.severity}
            </span>
          )}
        </div>

        {/* Gemini Detection Summary */}
        {latestEvent ? (
          <p className="text-xs text-slate-200 font-medium line-clamp-2 leading-snug">
            {latestEvent.summary}
          </p>
        ) : (
          <p className="text-xs text-slate-500 italic">
            Monitoring active. Waiting for Gemini visual analysis...
          </p>
        )}
      </div>
    </div>
  );
};
