import React, { useEffect, useState, useCallback } from 'react';
import { Navbar } from './components/Navbar';
import { DroneVideoCard } from './components/DroneVideoCard';
import { AlertBanner } from './components/AlertBanner';
import { ActivityDrawer } from './components/ActivityDrawer';
import { SimulationModal } from './components/SimulationModal';
import { useWebSocket } from './hooks/useWebSocket';
import { useAudioAlert } from './hooks/useAudioAlert';
import { DroneStream, AnalyticsEvent } from './types';
import { PlusCircle, ShieldCheck } from 'lucide-react';

export function App() {
  const [streams, setStreams] = useState<DroneStream[]>([]);
  const [events, setEvents] = useState<AnalyticsEvent[]>([]);
  const [latestEventsMap, setLatestEventsMap] = useState<Record<string, AnalyticsEvent>>({});
  const [currentCriticalAlert, setCurrentCriticalAlert] = useState<AnalyticsEvent | null>(null);
  const [unackAlertCount, setUnackAlertCount] = useState<number>(0);
  const [isSimModalOpen, setIsSimModalOpen] = useState(false);
  const [layoutGrid, setLayoutGrid] = useState<'1x1' | '2x2' | '3x3'>('2x2');

  const { isMuted, toggleMute, triggerAlarmSound } = useAudioAlert();

  // Handle incoming real-time alerts from WebSocket
  const handleAlertReceived = useCallback((evt: AnalyticsEvent) => {
    setEvents((prev) => [evt, ...prev.slice(0, 100)]);
    setLatestEventsMap((prev) => ({ ...prev, [evt.stream_id]: evt }));

    if (evt.severity === 'CRITICAL') {
      setCurrentCriticalAlert(evt);
      setUnackAlertCount((prev) => prev + 1);
      triggerAlarmSound();
    }
  }, [triggerAlarmSound]);

  const { isConnected } = useWebSocket(handleAlertReceived);

  // Fetch initial active streams
  const fetchStreams = useCallback(() => {
    fetch('/api/v1/streams')
      .then((res) => res.json())
      .then((data) => {
        if (Array.isArray(data)) {
          setStreams(data);
        }
      })
      .catch((err) => console.error('Failed to fetch streams:', err));
  }, []);

  // Fetch initial analytics logs
  const fetchAnalytics = useCallback(() => {
    fetch('/api/v1/analytics?limit=50')
      .then((res) => res.json())
      .then((data) => {
        if (Array.isArray(data)) {
          setEvents(data);
          const map: Record<string, AnalyticsEvent> = {};
          data.forEach((item) => {
            if (!map[item.stream_id]) {
              map[item.stream_id] = item;
            }
          });
          setLatestEventsMap(map);
        }
      })
      .catch((err) => console.error('Failed to fetch analytics:', err));
  }, []);

  useEffect(() => {
    fetchStreams();
    fetchAnalytics();
  }, [fetchStreams, fetchAnalytics]);

  const handleAcknowledgeAlert = (alertId?: string) => {
    setCurrentCriticalAlert(null);
    setUnackAlertCount((prev) => Math.max(0, prev - 1));
    if (alertId) {
      fetch(`/api/v1/alerts/${alertId}/acknowledge`, { method: 'POST' }).catch((e) =>
        console.error('Failed to acknowledge alert:', e)
      );
    }
  };

  const handleDeleteStream = (streamId: string) => {
    fetch(`/api/v1/streams/${streamId}`, { method: 'DELETE' })
      .then(() => fetchStreams())
      .catch((e) => console.error('Failed to delete stream:', e));
  };

  // Grid layout column classes
  const gridClasses = {
    '1x1': 'grid-cols-1 max-w-4xl mx-auto',
    '2x2': 'grid-cols-1 md:grid-cols-2',
    '3x3': 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3'
  }[layoutGrid];

  return (
    <div className="min-h-screen bg-[#0B0F17] flex flex-col">
      {/* Top Navbar */}
      <Navbar
        activeCount={streams.length}
        unackAlertCount={unackAlertCount}
        isConnected={isConnected}
        isMuted={isMuted}
        onToggleMute={toggleMute}
        onOpenSimulationModal={() => setIsSimModalOpen(true)}
        layoutGrid={layoutGrid}
        setLayoutGrid={setLayoutGrid}
      />

      {/* Main Workspace Layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* Drone Stream Grid Area */}
        <main className="flex-1 p-6 overflow-y-auto">
          {streams.length === 0 ? (
            <div className="flex flex-col items-center justify-center min-h-[60vh] border-2 border-dashed border-[#212D40] rounded-3xl p-8 text-center max-w-2xl mx-auto my-12 bg-[#131A26]/40">
              <div className="bg-cyan-500/10 p-4 rounded-2xl border border-cyan-500/20 text-cyan-400 mb-4">
                <ShieldCheck className="w-10 h-10" />
              </div>
              <h3 className="text-xl font-bold text-slate-100 mb-2">
                No Drone Video Feeds Connected
              </h3>
              <p className="text-sm text-slate-400 max-w-md mb-6 leading-relaxed">
                Launch an RTSP simulation stream using local test videos or add a live drone feed URL to start real-time Gemini AI surveillance.
              </p>
              <button
                onClick={() => setIsSimModalOpen(true)}
                className="bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-semibold text-xs px-6 py-3 rounded-xl shadow-lg shadow-cyan-500/20 transition-all flex items-center gap-2 border border-cyan-400/30"
              >
                <PlusCircle className="w-4 h-4" />
                <span>Launch RTSP Test Simulator</span>
              </button>
            </div>
          ) : (
            <div className={`grid gap-5 ${gridClasses}`}>
              {streams.map((stream) => (
                <DroneVideoCard
                  key={stream.stream_id}
                  stream={stream}
                  latestEvent={latestEventsMap[stream.stream_id]}
                  onDeleteStream={handleDeleteStream}
                />
              ))}
            </div>
          )}
        </main>

        {/* Right Drawer Activity Feed */}
        <ActivityDrawer events={events} />
      </div>

      {/* Floating Urgent Critical Alert Banner */}
      <AlertBanner
        alert={currentCriticalAlert}
        onAcknowledge={handleAcknowledgeAlert}
      />

      {/* RTSP Test Simulator Modal */}
      <SimulationModal
        isOpen={isSimModalOpen}
        onClose={() => setIsSimModalOpen(false)}
        onSimulationLaunched={fetchStreams}
      />
    </div>
  );
}

export default App;
