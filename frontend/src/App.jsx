import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import StreamGrid from './components/StreamGrid';
import AlertSidebar from './components/AlertSidebar';
import RegisterStreamModal from './components/RegisterStreamModal';
import './App.css';

export default function App() {
  const [streams, setStreams] = useState([]);
  const [isRegisterModalOpen, setIsRegisterModalOpen] = useState(false);
  const [alerts, setAlerts] = useState([]);
  const [telemetry, setTelemetry] = useState({});

  // Fetch active streams from backend on mount
  const fetchStreams = async () => {
    try {
      const res = await fetch('/api/streams');
      if (res.ok) {
        const data = await res.json();
        setStreams(data);
      }
    } catch (err) {
      console.error('Failed to fetch streams:', err);
    }
  };

  useEffect(() => {
    fetchStreams();

    let ws = null;
    let reconnectTimeout = null;

    const connectWebSocket = () => {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/ws/alerts`;
      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log('WebSocket connected to DroneWatch pilot dispatch server');
      };

      ws.onmessage = (event) => {
        try {
          const incident = JSON.parse(event.data);

          // Update real-time Gemini telemetry HUD for this drone ID
          if (incident.drone_id) {
            setTelemetry((prev) => ({
              ...prev,
              [incident.drone_id]: incident,
            }));
          }

          // Cap alerts list to 50 items and deduplicate by event_id
          if (incident.threat_level && incident.threat_level !== 'CLEAR' && incident.threat_level !== 'NONE') {
            setAlerts((prev) => {
              const exists = prev.some((a) => a.event_id === incident.event_id);
              if (exists) return prev;
              return [incident, ...prev].slice(0, 50);
            });
          }
        } catch (err) {
          console.error('Error parsing WebSocket message:', err);
        }
      };

      ws.onclose = () => {
        console.warn('WebSocket closed. Scheduling reconnect in 3s...');
        reconnectTimeout = setTimeout(connectWebSocket, 3000);
      };

      ws.onerror = (err) => {
        console.error('WebSocket error encountered:', err);
        ws.close();
      };
    };

    connectWebSocket();

    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (ws) {
        ws.onclose = null; // Prevent reconnect loop on unmount
        ws.close();
      }
    };
  }, []);

  const handleRegisterStream = async (newStream) => {
    try {
      const res = await fetch('/api/streams', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newStream),
      });

      if (!res.ok) {
        const errData = await res.json();
        alert(`Failed to register stream: ${errData.detail || 'Unknown error'}`);
        return;
      }

      await fetchStreams();
    } catch (err) {
      console.error('Error registering stream:', err);
      setStreams((prev) => [...prev, { ...newStream, status: 'ONLINE' }]);
    }
  };

  const handleUnregisterStream = async (droneId) => {
    try {
      const res = await fetch(`/api/streams/${droneId}`, { method: 'DELETE' });
      if (res.ok) {
        setStreams((prev) => prev.filter((s) => s.drone_id !== droneId));
      }
    } catch (err) {
      console.error('Error unregistering stream:', err);
      setStreams((prev) => prev.filter((s) => s.drone_id !== droneId));
    }
  };

  const handleAcknowledge = async (eventId) => {
    setAlerts((prev) =>
      prev.map((a) => (a.event_id === eventId ? { ...a, acknowledged_by_pilot: true } : a))
    );
    try {
      await fetch(`/api/incidents/${eventId}/acknowledge`, { method: 'POST' });
    } catch (err) {
      console.error('Failed to post acknowledgment:', err);
    }
  };

  const handleTriggerSimulation = async () => {
    const targetDrone = streams.length > 0 ? streams[0].drone_id : 'Drone-Alpha';
    try {
      const res = await fetch('/api/simulation/trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          drone_id: targetDrone,
          threat_level: 'CRITICAL',
          category: 'PERIMETER_BREACH',
          description: `Simulated intrusion near server building perimeter reported by ${targetDrone}.`,
        }),
      });
      const newAlert = await res.json();

      setTelemetry((prev) => ({
        ...prev,
        [targetDrone]: newAlert,
      }));

      setAlerts((prev) => [newAlert, ...prev]);
    } catch (err) {
      console.error('Simulation trigger error:', err);
      const mockAlert = {
        event_id: String(Date.now()),
        drone_id: targetDrone,
        timestamp: new Date().toISOString(),
        threat_level: 'CRITICAL',
        category: 'PERIMETER_BREACH',
        description: `Simulated intrusion near server building perimeter reported by ${targetDrone}.`,
        acknowledged_by_pilot: false,
      };
      setAlerts((prev) => [mockAlert, ...prev]);
    }
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Header
        activeCount={streams.length}
        onTriggerSim={handleTriggerSimulation}
        onOpenRegisterModal={() => setIsRegisterModalOpen(true)}
      />

      <main className="dashboard-grid">
        <StreamGrid
          streams={streams}
          activeAlerts={alerts}
          telemetry={telemetry}
          onUnregisterStream={handleUnregisterStream}
          onOpenRegisterModal={() => setIsRegisterModalOpen(true)}
        />
        <AlertSidebar alerts={alerts} onAcknowledge={handleAcknowledge} />
      </main>

      <RegisterStreamModal
        isOpen={isRegisterModalOpen}
        onClose={() => setIsRegisterModalOpen(false)}
        onRegister={handleRegisterStream}
      />
    </div>
  );
}
