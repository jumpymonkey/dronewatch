import React from 'react';
import { ShieldAlert, Cpu, PlusCircle, LayoutDashboard, Sliders } from 'lucide-react';

export default function Header({
  activeTab = 'dashboard',
  onTabChange,
  activeCount,
  onTriggerSim,
  onOpenRegisterModal,
}) {
  return (
    <header className="app-header">
      <div className="logo-group">
        <div className="logo-icon">
          <ShieldAlert size={22} />
        </div>
        <div>
          <h1 className="logo-title">DroneWatch Command</h1>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            Gemini 3.6 Flash & Gemma 4 Multi-Drone Patrol
          </p>
        </div>
      </div>

      {/* Navigation Switcher */}
      <div className="header-nav-tabs">
        <button
          className={`nav-tab-btn ${activeTab === 'dashboard' ? 'active' : ''}`}
          onClick={() => onTabChange('dashboard')}
        >
          <LayoutDashboard size={15} />
          <span>Operations Dashboard</span>
        </button>
        <button
          className={`nav-tab-btn ${activeTab === 'admin' ? 'active' : ''}`}
          onClick={() => onTabChange('admin')}
        >
          <Sliders size={15} />
          <span>Workflow Administration</span>
        </button>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <div className="status-badge">
          <div className="status-dot"></div>
          <span>{activeCount} Active Feeds</span>
        </div>

        <button
          className="btn-primary"
          onClick={onOpenRegisterModal}
          style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}
        >
          <PlusCircle size={16} />
          <span>Register Feed</span>
        </button>

        <button className="btn-trigger-sim" onClick={onTriggerSim}>
          Simulate Alert
        </button>
      </div>
    </header>
  );
}
