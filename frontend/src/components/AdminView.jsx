import React, { useState, useEffect } from 'react';
import {
  Sliders,
  Save,
  RotateCcw,
  RefreshCw,
  Cpu,
  Sparkles,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  Database,
  Layers,
  ArrowRight,
} from 'lucide-react';

export default function AdminView() {
  const [config, setConfig] = useState(null);
  const [initialConfig, setInitialConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [statusMessage, setStatusMessage] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);

  const fetchConfig = async () => {
    setLoading(true);
    setErrorMessage(null);
    try {
      const res = await fetch('/api/admin/workflow-config');
      if (!res.ok) {
        throw new Error(`Failed to load configuration (HTTP ${res.status})`);
      }
      const data = await res.json();
      setConfig(data);
      setInitialConfig(data);
    } catch (err) {
      console.error('Error loading workflow configuration:', err);
      setErrorMessage(err.message || 'Unable to load configuration from backend.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  const isDirty =
    config &&
    initialConfig &&
    (config.enable_tier1_gemma !== initialConfig.enable_tier1_gemma ||
      config.gemma_triage_prompt !== initialConfig.gemma_triage_prompt ||
      config.gemma_triage_threshold !== initialConfig.gemma_triage_threshold ||
      config.escalation_target !== initialConfig.escalation_target ||
      config.gemini_escalation_prompt !== initialConfig.gemini_escalation_prompt ||
      config.gemma_escalation_prompt !== initialConfig.gemma_escalation_prompt);

  const handleSave = async (e) => {
    if (e) e.preventDefault();
    if (!config) return;

    setSaving(true);
    setStatusMessage(null);
    setErrorMessage(null);

    const payload = {
      enable_tier1_gemma: config.enable_tier1_gemma,
      gemma_triage_prompt: config.gemma_triage_prompt,
      gemma_triage_threshold: parseFloat(config.gemma_triage_threshold),
      escalation_target: config.escalation_target,
      gemini_escalation_prompt: config.gemini_escalation_prompt,
      gemma_escalation_prompt: config.gemma_escalation_prompt,
    };

    try {
      const res = await fetch('/api/admin/workflow-config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || `Save failed (HTTP ${res.status})`);
      }

      const updated = await res.json();
      setConfig(updated);
      setInitialConfig(updated);
      setStatusMessage('Workflow configuration saved and hot-reloaded across all active streams.');
      setTimeout(() => setStatusMessage(null), 5000);
    } catch (err) {
      console.error('Failed to save configuration:', err);
      setErrorMessage(err.message || 'Failed to save configuration.');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (
      !window.confirm(
        'Reset image understanding configuration to factory defaults? This will overwrite existing custom prompts and thresholds.'
      )
    ) {
      return;
    }

    setResetting(true);
    setStatusMessage(null);
    setErrorMessage(null);

    try {
      const res = await fetch('/api/admin/workflow-config/reset', {
        method: 'POST',
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || `Reset failed (HTTP ${res.status})`);
      }

      const defaultCfg = await res.json();
      setConfig(defaultCfg);
      setInitialConfig(defaultCfg);
      setStatusMessage('Workflow configuration successfully reset to factory defaults.');
      setTimeout(() => setStatusMessage(null), 5000);
    } catch (err) {
      console.error('Failed to reset configuration:', err);
      setErrorMessage(err.message || 'Failed to reset configuration.');
    } finally {
      setResetting(false);
    }
  };

  const handleDiscard = () => {
    if (initialConfig) {
      setConfig({ ...initialConfig });
    }
  };

  if (loading) {
    return (
      <div className="admin-loading-container">
        <RefreshCw className="spin-icon" size={32} />
        <p>Loading workflow settings from AlloyDB...</p>
      </div>
    );
  }

  return (
    <div className="admin-view-wrapper">
      <div className="admin-header-panel glass-panel">
        <div className="admin-header-title-group">
          <div className="admin-header-icon">
            <Sliders size={24} />
          </div>
          <div>
            <h2>Image Understanding Workflow Administration</h2>
            <p className="admin-subtitle">
              Configure front-line Gemma 4 vision triage, escalation thresholds, and Tier 2 deep
              reasoning models.
            </p>
          </div>
        </div>

        <div className="admin-meta-chips">
          <div className="meta-chip">
            <Database size={14} />
            <span>AlloyDB Active</span>
          </div>
          <div className="meta-chip version-chip">
            <span>Rev v{config?.version || 1}</span>
          </div>
          {isDirty && (
            <div className="meta-chip dirty-chip">
              <span>Unsaved Changes</span>
            </div>
          )}
          <button
            type="button"
            className="btn-primary header-save-btn"
            disabled={saving || !isDirty}
            onClick={handleSave}
            style={{ marginLeft: '0.75rem', padding: '0.45rem 0.9rem', fontSize: '0.85rem' }}
          >
            {saving ? (
              <>
                <RefreshCw className="spin-icon" size={14} />
                <span>Saving...</span>
              </>
            ) : (
              <>
                <Save size={14} />
                <span>Save Settings</span>
              </>
            )}
          </button>
        </div>
      </div>

      {statusMessage && (
        <div className="status-toast success glass-panel">
          <CheckCircle2 size={18} />
          <span>{statusMessage}</span>
        </div>
      )}

      {errorMessage && (
        <div className="status-toast error glass-panel">
          <AlertTriangle size={18} />
          <span>{errorMessage}</span>
        </div>
      )}

      <form onSubmit={handleSave} className="admin-form">
        {/* Tier 1 Gemma Triage Section */}
        <div className="admin-section glass-panel">
          <div className="section-header">
            <div className="section-title-group">
              <div className="section-badge gemma-badge">
                <Cpu size={16} />
                <span>Tier 1 Triage</span>
              </div>
              <h3>Front-Line Gemma 4 Vision Triage</h3>
            </div>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={config?.enable_tier1_gemma ?? true}
                onChange={(e) =>
                  setConfig((prev) => ({ ...prev, enable_tier1_gemma: e.target.checked }))
                }
              />
              <span className="slider round"></span>
            </label>
          </div>

          <p className="section-description">
            Low-latency local screening using Google Gemma 4 on Cloud Run. Benign frames are filtered
            at zero API cost, preserving latency and quota.
          </p>

          <div
            className={`section-body-collapsible ${
              !config?.enable_tier1_gemma ? 'disabled-dim' : ''
            }`}
          >
            <div className="form-group">
              <div className="label-with-hint">
                <label htmlFor="gemma-triage-prompt">Triage Prompt (Safe vs. Alert Verdict)</label>
                <span className="hint-text">Passed directly to Gemma 4 for binary classification</span>
              </div>
              <textarea
                id="gemma-triage-prompt"
                rows={3}
                className="admin-textarea mono-font"
                value={config?.gemma_triage_prompt || ''}
                disabled={!config?.enable_tier1_gemma}
                onChange={(e) =>
                  setConfig((prev) => ({ ...prev, gemma_triage_prompt: e.target.value }))
                }
                placeholder="detect campus security anomalies, unauthorized persons, or perimeter breaches; answer safe or alert"
              />
            </div>
          </div>

          <div
            className="form-group threshold-group"
            style={{
              marginTop: '1.25rem',
              paddingTop: '1.25rem',
              borderTop: '1px solid rgba(255, 255, 255, 0.08)',
            }}
          >
            <div className="label-with-hint">
              <label htmlFor="gemma-threshold">Alert & Escalation Confidence Threshold</label>
              <span className="hint-text">
                Confidence cutoff score (0.10 to 0.95) required to escalate (Tier 1) and dispatch alerts (Tier 2)
              </span>
            </div>
            <div className="threshold-control-row">
              <input
                id="gemma-threshold"
                type="range"
                min="0.10"
                max="0.95"
                step="0.05"
                className="threshold-slider"
                value={config?.gemma_triage_threshold || 0.5}
                onChange={(e) =>
                  setConfig((prev) => ({
                    ...prev,
                    gemma_triage_threshold: parseFloat(e.target.value),
                  }))
                }
              />
              <div className="threshold-value-badge">
                {(config?.gemma_triage_threshold ?? 0.5).toFixed(2)}
              </div>
              <span className="threshold-level-tag">
                {config?.gemma_triage_threshold <= 0.35
                  ? 'Sensitive (High Alert/Escalation Rate)'
                  : config?.gemma_triage_threshold >= 0.70
                  ? 'Strict (High-Confidence Alerts Only)'
                  : 'Balanced Default'}
              </span>
            </div>
          </div>
        </div>

        {/* Tier 2 Escalation Routing Section */}
        <div className="admin-section glass-panel">
          <div className="section-header">
            <div className="section-title-group">
              <div className="section-badge escalation-badge">
                <Layers size={16} />
                <span>Tier 2 Escalation</span>
              </div>
              <h3>Escalation Routing & Deep Reasoning Target</h3>
            </div>
          </div>

          <p className="section-description">
            When Tier 1 triggers an alert (or if Tier 1 is disabled), route the suspicious frame to
            either cloud-scale Gemini Flash or escalate back to Gemma 4.
          </p>

          <div className="escalation-target-cards">
            {/* Gemini Card */}
            <div
              className={`target-card ${
                config?.escalation_target === 'GEMINI' ? 'selected gemini-selected' : ''
              }`}
              onClick={() => setConfig((prev) => ({ ...prev, escalation_target: 'GEMINI' }))}
            >
              <div className="target-card-header">
                <div className="target-title-wrap">
                  <Sparkles size={20} className="card-gemini-icon" />
                  <h4>Gemini 3.6 Flash (Vertex AI)</h4>
                </div>
                <div className="target-radio-indicator">
                  <div className="radio-inner" />
                </div>
              </div>
              <p className="target-card-desc">
                Default high-accuracy multimodal engine. Produces normalized JSON schema with
                spatial bounding boxes and incident categories.
              </p>
              <div className="target-card-footer">
                <span className="target-pill">Vertex AI API</span>
                <span className="target-pill">Bounding Boxes</span>
                <span className="target-pill">Default</span>
              </div>
            </div>

            {/* Gemma Card */}
            <div
              className={`target-card ${
                config?.escalation_target === 'GEMMA' ? 'selected gemma-selected' : ''
              }`}
              onClick={() => setConfig((prev) => ({ ...prev, escalation_target: 'GEMMA' }))}
            >
              <div className="target-card-header">
                <div className="target-title-wrap">
                  <Cpu size={20} className="card-gemma-icon" />
                  <h4>Gemma 4 Deep Reasoner (vLLM)</h4>
                </div>
                <div className="target-radio-indicator">
                  <div className="radio-inner" />
                </div>
              </div>
              <p className="target-card-desc">
                Escalates back to local Gemma 4 with a detailed escalation prompt. Generates
                lightweight natural language assessment without third-party API dependencies.
              </p>
              <div className="target-card-footer">
                <span className="target-pill">Cloud Run Private</span>
                <span className="target-pill">Text Explanation</span>
                <span className="target-pill">Zero Cloud Costs</span>
              </div>
            </div>
          </div>

          {/* Dynamic Prompt Editor based on selection */}
          <div className="prompt-editor-group">
            {config?.escalation_target === 'GEMINI' ? (
              <div className="form-group">
                <div className="label-with-hint">
                  <label htmlFor="gemini-escalation-prompt">Gemini 3.6 Flash Escalation Prompt</label>
                  <span className="hint-text">
                    Prompt instructing Gemini Flash to analyze campus threat and return schema JSON
                  </span>
                </div>
                <textarea
                  id="gemini-escalation-prompt"
                  rows={10}
                  className="admin-textarea mono-font"
                  value={config?.gemini_escalation_prompt || ''}
                  onChange={(e) =>
                    setConfig((prev) => ({ ...prev, gemini_escalation_prompt: e.target.value }))
                  }
                />
              </div>
            ) : (
              <div className="form-group">
                <div className="label-with-hint">
                  <label htmlFor="gemma-escalation-prompt">Gemma 4 Deep Escalation Prompt</label>
                  <span className="hint-text">
                    Prompt sent back to Gemma 4 to analyze the alerted scene in detail
                  </span>
                </div>
                <textarea
                  id="gemma-escalation-prompt"
                  rows={6}
                  className="admin-textarea mono-font"
                  value={config?.gemma_escalation_prompt || ''}
                  onChange={(e) =>
                    setConfig((prev) => ({ ...prev, gemma_escalation_prompt: e.target.value }))
                  }
                />
              </div>
            )}
          </div>
        </div>

        {/* Global Action Bar */}
        <div className="admin-actions-bar glass-panel">
          <div className="actions-left">
            <button
              type="button"
              className="btn-danger-outline"
              disabled={resetting || saving}
              onClick={handleReset}
            >
              <RotateCcw size={16} />
              <span>Reset to Defaults</span>
            </button>
            {isDirty && (
              <button
                type="button"
                className="btn-ghost"
                disabled={saving}
                onClick={handleDiscard}
              >
                <span>Discard Changes</span>
              </button>
            )}
          </div>

          <div className="actions-right">
            <button
              type="submit"
              className="btn-primary save-btn"
              disabled={saving || !isDirty}
            >
              {saving ? (
                <>
                  <RefreshCw className="spin-icon" size={16} />
                  <span>Saving Configuration...</span>
                </>
              ) : (
                <>
                  <Save size={16} />
                  <span>Save Workflow Settings</span>
                </>
              )}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
