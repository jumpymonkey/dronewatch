import React from 'react';
import { Bell, CheckCircle2, ShieldAlert } from 'lucide-react';

export default function AlertSidebar({ alerts, onAcknowledge }) {
  return (
    <aside className="sidebar glass-panel">
      <div className="sidebar-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Bell size={18} color="var(--threat-high)" />
          <h2 className="sidebar-title">Real-Time Pilot Alerts</h2>
        </div>
        <span
          style={{
            fontSize: '0.8rem',
            padding: '0.2rem 0.6rem',
            borderRadius: '12px',
            background: 'rgba(255,255,255,0.08)',
          }}
        >
          {alerts.filter((a) => !a.acknowledged_by_pilot).length} Unread
        </span>
      </div>

      <div className="alert-list">
        {alerts.length === 0 ? (
          <div
            style={{
              padding: '2rem',
              textAlign: 'center',
              color: 'var(--text-muted)',
              fontSize: '0.9rem',
            }}
          >
            <ShieldAlert size={32} style={{ marginBottom: '0.5rem', opacity: 0.5 }} />
            <p>No active threats detected. Campus clear.</p>
          </div>
        ) : (
          alerts.map((alert) => (
            <div key={alert.event_id} className={`alert-item ${alert.threat_level}`}>
              <div className="alert-item-header">
                <span className="alert-drone-tag">{alert.drone_id}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  {alert.video_timestamp_formatted && (
                    <span className="video-timecode-tag" title="Video Stream Timecode">
                      TC {alert.video_timestamp_formatted}
                    </span>
                  )}
                  <span className="alert-time">
                    {new Date(alert.timestamp).toLocaleTimeString()}
                  </span>
                </div>
              </div>

              <p className="alert-description">
                {alert.video_timestamp_formatted && (
                  <span className="timecode-pill">
                    Video Marker: {alert.video_timestamp_formatted}
                  </span>
                )}
                {alert.description}
              </p>

              {!alert.acknowledged_by_pilot ? (
                <button
                  className="btn-acknowledge"
                  onClick={() => onAcknowledge(alert.event_id)}
                >
                  Acknowledge Threat
                </button>
              ) : (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.3rem',
                    fontSize: '0.75rem',
                    color: 'var(--threat-low)',
                  }}
                >
                  <CheckCircle2 size={14} />
                  <span>Acknowledged by Pilot</span>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </aside>
  );
}
