import React from 'react';
import { AlertTriangle, CheckCircle2, ShieldAlert } from 'lucide-react';
import { AnalyticsEvent } from '../types';

interface AlertBannerProps {
  alert: AnalyticsEvent | null;
  onAcknowledge: (alertId?: string) => void;
}

export const AlertBanner: React.FC<AlertBannerProps> = ({ alert, onAcknowledge }) => {
  if (!alert) return null;

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 w-full max-w-3xl px-4 animate-bounce-short">
      <div className="bg-gradient-to-r from-red-950 via-slate-900 to-red-950 border-2 border-red-500 text-white rounded-2xl p-4 shadow-2xl shadow-red-500/40 backdrop-blur-xl flex items-center justify-between gap-4">
        <div className="flex items-center gap-3.5">
          <div className="bg-red-500/20 p-2.5 rounded-xl border border-red-500/40 text-red-400 animate-pulse">
            <ShieldAlert className="w-7 h-7" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="bg-red-500 text-white font-mono text-[10px] font-extrabold px-2 py-0.5 rounded tracking-wider uppercase">
                URGENT {alert.severity} THREAT
              </span>
              <span className="text-xs font-mono text-slate-400">
                {alert.drone_name || 'Drone Stream'} • {new Date(alert.timestamp).toLocaleTimeString()}
              </span>
            </div>
            <p className="text-sm font-semibold text-slate-100 mt-1 line-clamp-1">
              {alert.summary}
            </p>
          </div>
        </div>

        <button
          onClick={() => onAcknowledge(alert.event_id)}
          className="bg-gradient-to-r from-red-600 to-rose-600 hover:from-red-500 hover:to-rose-500 text-white text-xs font-bold px-4 py-2.5 rounded-xl shadow-lg shadow-red-600/30 transition-all flex items-center gap-1.5 whitespace-nowrap border border-red-400/40"
        >
          <CheckCircle2 className="w-4 h-4" />
          <span>Acknowledge</span>
        </button>
      </div>
    </div>
  );
};
