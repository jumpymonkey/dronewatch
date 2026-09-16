import React from 'react';
import { Camera, MapPin, AlertCircle, Trash2, PlusCircle, Cpu, Eye, ShieldCheck } from 'lucide-react';

export default function StreamGrid({
  streams,
  activeAlerts,
  telemetry = {},
  onUnregisterStream,
  onOpenRegisterModal,
}) {
  const maxStreams = 4;
  const emptySlots = Math.max(0, maxStreams - streams.length);

  const getVideoSource = (stream) => {
    if (stream.stream_url && (stream.stream_url.startsWith('http://') || stream.stream_url.startsWith('https://'))) {
      return stream.stream_url;
    }
    const streamParam = stream.stream_url ? `?stream_url=${encodeURIComponent(stream.stream_url)}` : '';
    return `/api/streams/${encodeURIComponent(stream.drone_id)}/video${streamParam}`;
  };

  return (
    <div className="streams-container">
      {streams.map((stream) => {
        const droneTelemetry = telemetry[stream.drone_id];
        const hasAlert = activeAlerts.some(
          (a) => a.drone_id === stream.drone_id && !a.acknowledged_by_pilot
        );

        const threatLevel = droneTelemetry?.threat_level || (hasAlert ? 'ALERT' : 'CLEAR');
        const isThreat = threatLevel !== 'CLEAR' && threatLevel !== 'NONE';

        return (
          <div
            key={stream.drone_id}
            className={`stream-card glass-panel ${hasAlert ? 'alert-active' : ''}`}
          >
            {/* Stream Header Bar */}
            <div className="stream-overlay">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Camera size={16} color="var(--accent-cyan)" />
                <div>
                  <div className="stream-title">{stream.drone_id}</div>
                  <div className="stream-zone">
                    <MapPin size={12} style={{ display: 'inline', marginRight: '3px' }} />
                    {stream.zone_name}
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                {isThreat ? (
                  <div className="threat-badge threat-critical">
                    <AlertCircle size={14} />
                    <span>{threatLevel}</span>
                  </div>
                ) : (
                  <div className="threat-badge threat-clear">
                    <ShieldCheck size={14} />
                    <span>CLEAR</span>
                  </div>
                )}

                <button
                  className="btn-icon-danger"
                  title="Unregister Feed"
                  onClick={() => onUnregisterStream(stream.drone_id)}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>

            {/* Live Drone Video Feed Visualizer */}
            {stream.stream_url?.toLowerCase().startsWith('rtsp://') ? (
              <img
                className="video-player"
                src={getVideoSource(stream)}
                alt={stream.drone_id}
                onError={(e) => {
                  const img = e.target;
                  if (img && !img.dataset.retrying) {
                    img.dataset.retrying = 'true';
                    setTimeout(() => {
                      delete img.dataset.retrying;
                      const base = getVideoSource(stream);
                      img.src = `${base}${base.includes('?') ? '&' : '?'}_t=${Date.now()}`;
                    }, 1500);
                  }
                }}
              />
            ) : (
              <video
                className="video-player"
                src={getVideoSource(stream)}
                autoPlay
                loop
                muted
                playsInline
              />
            )}

            {/* Live Gemini AI Telemetry HUD Banner */}
            <div className="gemini-hud-banner">
              <div className="gemini-hud-header">
                <span className="gemini-badge">
                  <Cpu size={12} style={{ marginRight: '4px' }} />
                  Gemini Flash AI Vision
                </span>
                <span className="gemini-hud-time">
                  {droneTelemetry?.video_timestamp_formatted
                    ? `TC ${droneTelemetry.video_timestamp_formatted} • ${new Date(droneTelemetry.timestamp).toLocaleTimeString()}`
                    : droneTelemetry?.timestamp
                    ? new Date(droneTelemetry.timestamp).toLocaleTimeString()
                    : 'Analyzing...'}
                </span>
              </div>

              <div className="gemini-hud-body">
                <Eye size={13} className="hud-eye-icon" />
                <span className="hud-description">
                  {droneTelemetry?.description || 'Evaluating video stream with Gemini 3.6 Flash...'}
                </span>
              </div>
            </div>

            {/* Stream source URL footer */}
            <div className="stream-source-footer">
              <span className="source-label">Source:</span>
              <span className="source-url" title={stream.stream_url}>
                {stream.stream_url || 'RTSP Live Feed'}
              </span>
            </div>

            {/* Bounding Box SVG Overlay for Threat Detection */}
            {isThreat && (
              <svg className="bbox-canvas" viewBox="0 0 100 100" preserveAspectRatio="none">
                <rect
                  x="25"
                  y="20"
                  width="50"
                  height="55"
                  fill="rgba(255, 0, 85, 0.15)"
                  stroke="var(--threat-critical)"
                  strokeWidth="2"
                  strokeDasharray="4 2"
                />
                <text x="27" y="18" fill="var(--threat-critical)" fontSize="4.5" fontWeight="bold">
                  {droneTelemetry?.category || 'SUSPICIOUS ACTIVITY'} ({(droneTelemetry?.confidence_score ? (droneTelemetry.confidence_score * 100).toFixed(0) : 92)}%)
                </text>
              </svg>
            )}
          </div>
        );
      })}

      {/* Render placeholder cards for available stream slots */}
      {Array.from({ length: emptySlots }).map((_, index) => (
        <div
          key={`empty-slot-${index}`}
          className="stream-card glass-panel empty-slot-card"
          onClick={onOpenRegisterModal}
        >
          <div className="empty-slot-content">
            <PlusCircle size={36} color="var(--accent-cyan)" />
            <h4>Register Drone Feed</h4>
            <p>RTSP Stream URL or Local/GCS MP4</p>
          </div>
        </div>
      ))}
    </div>
  );
}
