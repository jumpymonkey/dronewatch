import React from 'react';
import { Shield, Radio, PlayCircle, Volume2, VolumeX, AlertTriangle, Cpu } from 'lucide-react';

interface NavbarProps {
  activeCount: number;
  unackAlertCount: number;
  isConnected: boolean;
  isMuted: boolean;
  onToggleMute: () => void;
  onOpenSimulationModal: () => void;
  onOpenAddStreamModal: () => void;
  layoutGrid: '1x1' | '2x2' | '3x3';
  setLayoutGrid: (grid: '1x1' | '2x2' | '3x3') => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeCount,
  unackAlertCount,
  isConnected,
  isMuted,
  onToggleMute,
  onOpenSimulationModal,
  onOpenAddStreamModal,
  layoutGrid,
  setLayoutGrid
}) => {
  return (
    <header className="sticky top-0 z-40 bg-[#131A26]/90 backdrop-blur-md border-b border-[#212D40] px-6 py-3.5 flex items-center justify-between">
      {/* Brand & Logo */}
      <div className="flex items-center gap-3">
        <div className="bg-gradient-to-tr from-cyan-500 to-blue-600 p-2 rounded-xl shadow-lg shadow-cyan-500/20">
          <Shield className="w-6 h-6 text-white" />
        </div>
        <div>
          <h1 className="text-xl font-bold tracking-tight bg-gradient-to-r from-white via-slate-100 to-slate-400 bg-clip-text text-transparent">
            DroneWatch
          </h1>
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <span className="inline-flex items-center gap-1 font-mono text-cyan-400">
              <Cpu className="w-3 h-3" /> Gemini 3.1 Flash Live
            </span>
            <span>•</span>
            <span className="flex items-center gap-1 text-emerald-400 font-medium">
              <span className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-emerald-400 animate-ping' : 'bg-red-500'}`}></span>
              {isConnected ? 'System Live' : 'Disconnected'}
            </span>
          </div>
        </div>
      </div>

      {/* Grid Controls & Actions */}
      <div className="flex items-center gap-3">
        {/* Layout Selector */}
        <div className="hidden md:flex bg-[#0B0F17] p-1 rounded-lg border border-[#212D40] text-xs font-mono text-slate-300">
          <button
            onClick={() => setLayoutGrid('1x1')}
            className={`px-2.5 py-1 rounded-md transition-all ${layoutGrid === '1x1' ? 'bg-cyan-500/20 text-cyan-400 font-semibold border border-cyan-500/30' : 'hover:text-white'}`}
          >
            1x1
          </button>
          <button
            onClick={() => setLayoutGrid('2x2')}
            className={`px-2.5 py-1 rounded-md transition-all ${layoutGrid === '2x2' ? 'bg-cyan-500/20 text-cyan-400 font-semibold border border-cyan-500/30' : 'hover:text-white'}`}
          >
            2x2
          </button>
          <button
            onClick={() => setLayoutGrid('3x3')}
            className={`px-2.5 py-1 rounded-md transition-all ${layoutGrid === '3x3' ? 'bg-cyan-500/20 text-cyan-400 font-semibold border border-cyan-500/30' : 'hover:text-white'}`}
          >
            3x3
          </button>
        </div>

        {/* Mute Audio Toggle */}
        <button
          onClick={onToggleMute}
          className={`p-2 rounded-lg border text-xs font-medium flex items-center gap-1.5 transition-all ${
            isMuted 
              ? 'bg-amber-500/10 text-amber-400 border-amber-500/30' 
              : 'bg-[#1E293B] text-slate-300 border-[#212D40] hover:bg-[#334155]'
          }`}
          title={isMuted ? 'Audio Alerts Muted' : 'Audio Alerts Enabled'}
        >
          {isMuted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4 text-emerald-400" />}
        </button>

        {/* Add Live RTSP Drone Button */}
        <button
          onClick={onOpenAddStreamModal}
          className="bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-semibold px-3.5 py-2 rounded-lg shadow-md shadow-emerald-500/20 transition-all flex items-center gap-2 border border-emerald-400/30"
        >
          <Radio className="w-4 h-4" />
          <span>Add Live RTSP Drone</span>
        </button>

        {/* Launch Test Simulator Button */}
        <button
          onClick={onOpenSimulationModal}
          className="bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white text-xs font-semibold px-3.5 py-2 rounded-lg shadow-md shadow-cyan-500/20 transition-all flex items-center gap-2 border border-cyan-400/30"
        >
          <PlayCircle className="w-4 h-4" />
          <span>Launch RTSP Test Simulator</span>
        </button>

        {/* Unacknowledged Alerts Badge */}
        {unackAlertCount > 0 && (
          <div className="flex items-center gap-1.5 bg-red-500/20 text-red-400 border border-red-500/40 px-3 py-1.5 rounded-lg font-mono text-xs animate-pulse">
            <AlertTriangle className="w-4 h-4 text-red-400" />
            <span className="font-bold">{unackAlertCount}</span>
            <span className="hidden sm:inline">Active Alerts</span>
          </div>
        )}
      </div>
    </header>
  );
};
