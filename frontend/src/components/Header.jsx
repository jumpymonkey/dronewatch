import React from 'react';
import { ShieldAlert, Cpu, PlusCircle } from 'lucide-react';

export default function Header({ activeCount, onTriggerSim, onOpenRegisterModal }) {
  return (
    <header className="app-header">
      <div className="logo-group">
        <div className="logo-icon">
          <ShieldAlert size={22} />
        </div>
        <div>
          <h1 className="logo-title">DroneWatch Command</h1>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            Gemini 2.5 Flash Multi-Drone Patrol
          </p>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <div className="status-badge">
          <div className="status-dot"></div>
          <span>{activeCount} Active Feeds</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.85rem', color: 'var(--accent-cyan)' }}>
          <Cpu size={16} />
          <span>Gemini 2.5 Flash</span>
        </div>

        <button className="btn-primary" onClick={onOpenRegisterModal} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <PlusCircle size={16} />
          <span>Register Drone Feed</span>
        </button>

        <button className="btn-trigger-sim" onClick={onTriggerSim}>
          Simulate Alert
        </button>
      </div>
    </header>
  );
}
