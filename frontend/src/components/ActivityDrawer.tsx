import React, { useState } from 'react';
import { AnalyticsEvent } from '../types';
import { Activity, Search, Filter, AlertOctagon, Info, AlertTriangle } from 'lucide-react';

interface ActivityDrawerProps {
  events: AnalyticsEvent[];
  onSelectEvent?: (event: AnalyticsEvent) => void;
}

export const ActivityDrawer: React.FC<ActivityDrawerProps> = ({ events, onSelectEvent }) => {
  const [filterSeverity, setFilterSeverity] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');

  const filteredEvents = events.filter((e) => {
    if (filterSeverity !== 'ALL' && e.severity !== filterSeverity) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      return (
        e.summary.toLowerCase().includes(q) ||
        (e.drone_name && e.drone_name.toLowerCase().includes(q)) ||
        e.category.toLowerCase().includes(q)
      );
    }
    return true;
  });

  return (
    <aside className="w-80 lg:w-96 bg-[#131A26] border-l border-[#212D40] flex flex-col h-[calc(100vh-61px)] sticky top-[61px]">
      {/* Drawer Header */}
      <div className="p-4 border-b border-[#212D40] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="w-5 h-5 text-cyan-400" />
          <h2 className="font-semibold text-sm text-slate-100">Live AI Activity Feed</h2>
        </div>
        <span className="font-mono text-xs text-slate-400 bg-[#0B0F17] px-2 py-0.5 rounded border border-[#212D40]">
          {filteredEvents.length} events
        </span>
      </div>

      {/* Filter & Search Bar */}
      <div className="p-3 border-b border-[#212D40] flex flex-col gap-2 bg-[#0B0F17]/50">
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search events or drone name..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-[#131A26] border border-[#212D40] rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500/50"
          />
        </div>

        <div className="flex items-center gap-1 font-mono text-[11px] text-slate-400">
          <Filter className="w-3 h-3 text-slate-500" />
          <span>Severity:</span>
          {['ALL', 'CRITICAL', 'MEDIUM', 'LOW'].map((sev) => (
            <button
              key={sev}
              onClick={() => setFilterSeverity(sev)}
              className={`px-2 py-0.5 rounded transition-colors ${
                filterSeverity === sev
                  ? 'bg-cyan-500/20 text-cyan-400 font-semibold border border-cyan-500/30'
                  : 'hover:text-slate-200'
              }`}
            >
              {sev}
            </button>
          ))}
        </div>
      </div>

      {/* Event Logs Feed List */}
      <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2.5">
        {filteredEvents.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-slate-500 text-center">
            <Info className="w-8 h-8 mb-2 opacity-50" />
            <p className="text-xs">No analytics logs match filters.</p>
          </div>
        ) : (
          filteredEvents.map((evt) => {
            const isCrit = evt.severity === 'CRITICAL';
            const isMed = evt.severity === 'MEDIUM';

            return (
              <div
                key={evt.event_id || `${evt.stream_id}-${evt.timestamp}`}
                onClick={() => onSelectEvent && onSelectEvent(evt)}
                className={`p-3 rounded-xl border text-xs cursor-pointer transition-all ${
                  isCrit
                    ? 'bg-red-950/20 border-red-500/40 hover:border-red-500'
                    : isMed
                    ? 'bg-amber-950/20 border-amber-500/30 hover:border-amber-500'
                    : 'bg-[#1E293B]/40 border-[#212D40] hover:border-slate-600'
                }`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className="font-semibold text-slate-200">
                    {evt.drone_name || 'Drone Feed'}
                  </span>
                  <span
                    className={`font-mono text-[10px] font-bold px-1.5 py-0.5 rounded ${
                      isCrit
                        ? 'bg-red-500/20 text-red-400 border border-red-500/40'
                        : isMed
                        ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40'
                        : 'bg-slate-700/50 text-slate-400'
                    }`}
                  >
                    {evt.severity}
                  </span>
                </div>

                <p className="text-slate-300 font-medium line-clamp-2 leading-relaxed mb-2">
                  {evt.summary}
                </p>

                <div className="flex items-center justify-between text-[10px] text-slate-500 font-mono">
                  <span className="bg-[#0B0F17] px-1.5 py-0.5 rounded border border-[#212D40]">
                    {evt.category}
                  </span>
                  <span>{new Date(evt.timestamp).toLocaleTimeString()}</span>
                </div>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
};
