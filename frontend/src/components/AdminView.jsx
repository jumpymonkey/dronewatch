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
  Activity,
  FileText,
  X,
  Copy,
  Check,
} from 'lucide-react';

const GEMINI_MODELS = [
  { id: 'gemini-3.8-flash', label: 'gemini-3.8-flash (Next-Gen Fast Multimodal Reasoning)' },
  { id: 'gemini-3.7-flash', label: 'gemini-3.7-flash (Hybrid Reasoning Flash)' },
  { id: 'gemini-3.6-flash', label: 'gemini-3.6-flash (Default Stable Flash)' },
  { id: 'gemini-4-aragon', label: 'gemini-4-aragon (Advanced Multimodal Agent)' },
];

const GEMMA_MODELS = [
  { id: 'google/gemma-4-E2B-it', label: 'google/gemma-4-E2B-it (Default Cloud Run Gemma 4)' },
  { id: 'google/gemma-3-4b-it', label: 'google/gemma-3-4b-it (Gemma 3 4B Vision / Instruct)' },
  { id: 'google/gemma-4-4b-it', label: 'google/gemma-4-4b-it (Gemma 4 4B Multimodal)' },
  { id: 'google/gemma-4-9b-it', label: 'google/gemma-4-9b-it (Gemma 4 9B High Capacity)' },
  { id: 'google/gemma-2-2b-it', label: 'google/gemma-2-2b-it (Lightweight 2B Edge)' },
];

const DEFAULT_ALERT_KEYWORDS = [
  'alert',
  'suspicious',
  'anomalous',
  'anomaly',
  'intruder',
  'unauthorized',
  'trespass',
  'trespassing',
  'breach',
  'danger',
  'hazard',
  'threat',
  'weapon',
  'climbing',
  'fire',
  'smoke',
  'loitering',
  'equipment',
  'machinery',
  'vehicle',
  'cart',
  'lift',
  'crane',
  'obstruction',
  'blocked',
];

const DEFAULT_BENIGN_KEYWORDS = [
  'safe',
  'normal',
  'benign',
  'clear',
  'empty',
  'routine',
  'authorized',
];

const arraysEqual = (a, b) => {
  if (a === b) return true;
  if (!a || !b) return false;
  if (a.length !== b.length) return false;
  return a.every((val, idx) => val === b[idx]);
};

function KeywordTagEditor({
  title,
  subtitle,
  tags = [],
  onChange,
  onResetDefaults,
  chipType = 'alert',
  placeholder = 'Add keyword...',
}) {
  const [inputValue, setInputValue] = useState('');

  const handleAdd = () => {
    const trimmed = inputValue.trim().toLowerCase();
    if (!trimmed) return;
    if (!tags.includes(trimmed)) {
      onChange([...tags, trimmed]);
    }
    setInputValue('');
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      handleAdd();
    }
  };

  const handleRemove = (tagToRemove) => {
    onChange(tags.filter((t) => t !== tagToRemove));
  };

  return (
    <div className="keyword-editor-container">
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '0.5rem',
        }}
      >
        <div>
          <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>
            {title}
          </span>
          {subtitle && (
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: '0.15rem 0 0 0' }}>
              {subtitle}
            </p>
          )}
        </div>
        {onResetDefaults && (
          <button
            type="button"
            className="btn-ghost"
            style={{ fontSize: '0.72rem', padding: '0.2rem 0.5rem' }}
            onClick={onResetDefaults}
          >
            Reset Defaults
          </button>
        )}
      </div>

      <div className="keyword-chips-wrap">
        {tags.map((tag) => (
          <span
            key={tag}
            className={`keyword-chip ${chipType === 'alert' ? 'alert-chip' : 'benign-chip'}`}
          >
            <span>{tag}</span>
            <button
              type="button"
              className="keyword-chip-remove"
              onClick={() => handleRemove(tag)}
              title={`Remove "${tag}"`}
            >
              <X size={12} />
            </button>
          </span>
        ))}
      </div>

      <div className="keyword-input-row">
        <input
          type="text"
          className="keyword-input-field"
          placeholder={placeholder}
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button
          type="button"
          className="btn-secondary"
          style={{ padding: '0.45rem 0.8rem', fontSize: '0.8rem' }}
          onClick={handleAdd}
          disabled={!inputValue.trim()}
        >
          Add
        </button>
      </div>
    </div>
  );
}

export default function AdminView() {
  const [config, setConfig] = useState(null);
  const [initialConfig, setInitialConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [statusMessage, setStatusMessage] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);

  const [recentResponses, setRecentResponses] = useState([]);
  const [loadingResponses, setLoadingResponses] = useState(false);
  const [selectedResponse, setSelectedResponse] = useState(null);
  const [copiedResponse, setCopiedResponse] = useState(false);

  const normalizeConfig = (data) => ({
    ...data,
    alert_keywords: data.alert_keywords || [...DEFAULT_ALERT_KEYWORDS],
    benign_keywords: data.benign_keywords || [...DEFAULT_BENIGN_KEYWORDS],
    ambiguity_policy: data.ambiguity_policy || 'FAIL_SAFE',
    gemma_model: data.gemma_model || 'google/gemma-4-E2B-it',
    gemma_timeout_seconds: data.gemma_timeout_seconds ?? 2.0,
    vllm_temperature: data.vllm_temperature ?? 0.0,
    vllm_max_tokens: data.vllm_max_tokens ?? 32,
  });

  const fetchConfig = async () => {
    setLoading(true);
    setErrorMessage(null);
    try {
      const res = await fetch('/api/admin/workflow-config');
      if (!res.ok) {
        throw new Error(`Failed to load configuration (HTTP ${res.status})`);
      }
      const data = await res.json();
      const normalized = normalizeConfig(data);
      setConfig(normalized);
      setInitialConfig(normalized);
    } catch (err) {
      console.error('Error loading workflow configuration:', err);
      setErrorMessage(err.message || 'Unable to load configuration from backend.');
    } finally {
      setLoading(false);
    }
  };

  const fetchRecentResponses = async () => {
    setLoadingResponses(true);
    try {
      const res = await fetch('/api/ai/responses?limit=30');
      if (res.ok) {
        const data = await res.json();
        setRecentResponses(data);
      }
    } catch (err) {
      console.error('Failed to fetch recent AI responses:', err);
    } finally {
      setLoadingResponses(false);
    }
  };

  useEffect(() => {
    fetchConfig();
    fetchRecentResponses();
  }, []);

  const isDirty =
    config &&
    initialConfig &&
    (config.enable_tier1_gemma !== initialConfig.enable_tier1_gemma ||
      config.gemma_triage_prompt !== initialConfig.gemma_triage_prompt ||
      config.gemma_triage_threshold !== initialConfig.gemma_triage_threshold ||
      config.escalation_target !== initialConfig.escalation_target ||
      config.gemini_escalation_prompt !== initialConfig.gemini_escalation_prompt ||
      config.gemma_escalation_prompt !== initialConfig.gemma_escalation_prompt ||
      config.gemini_model !== initialConfig.gemini_model ||
      config.gemma_model !== initialConfig.gemma_model ||
      (config.gemma_service_url || '') !== (initialConfig.gemma_service_url || '') ||
      config.gemma_timeout_seconds !== initialConfig.gemma_timeout_seconds ||
      config.ambiguity_policy !== initialConfig.ambiguity_policy ||
      config.vllm_temperature !== initialConfig.vllm_temperature ||
      config.vllm_max_tokens !== initialConfig.vllm_max_tokens ||
      !arraysEqual(config.alert_keywords, initialConfig.alert_keywords) ||
      !arraysEqual(config.benign_keywords, initialConfig.benign_keywords));

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
      gemini_model: config.gemini_model,
      gemma_model: config.gemma_model,
      gemma_service_url: config.gemma_service_url?.trim() || null,
      gemma_timeout_seconds: parseFloat(config.gemma_timeout_seconds),
      alert_keywords: config.alert_keywords || [],
      benign_keywords: config.benign_keywords || [],
      ambiguity_policy: config.ambiguity_policy || 'FAIL_SAFE',
      vllm_temperature: parseFloat(config.vllm_temperature),
      vllm_max_tokens: parseInt(config.vllm_max_tokens, 10),
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
      const normalized = normalizeConfig(updated);
      setConfig(normalized);
      setInitialConfig(normalized);
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
      const normalized = normalizeConfig(defaultCfg);
      setConfig(normalized);
      setInitialConfig(normalized);
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

        {/* Gemma 4 & vLLM Runtime Parameters Section */}
        <div className="admin-section glass-panel">
          <div className="section-header">
            <div className="section-title-group">
              <div className="section-badge gemma-badge">
                <Cpu size={16} />
                <span>Runtime Engine</span>
              </div>
              <h3>Gemma 4 & vLLM Runtime Parameters</h3>
            </div>
          </div>

          <p className="section-description">
            Fine-tune vLLM inference parameters, model identifiers, service endpoints, triage ambiguity
            handling, and keyword taxonomy. Changes hot-reload across all streams without restart.
          </p>

          {/* Grid 2-col: Service URL & Model Selection */}
          <div className="admin-grid-2col">
            <div className="form-group">
              <div className="label-with-hint">
                <label htmlFor="gemma-service-url">vLLM Service Endpoint URL</label>
                <span className="hint-text">Leave blank to use internal Cloud Run default</span>
              </div>
              <input
                id="gemma-service-url"
                type="text"
                className="admin-input mono-font"
                placeholder="http://gemma-vllm.internal:8000 (default)"
                value={config?.gemma_service_url || ''}
                onChange={(e) =>
                  setConfig((prev) => ({ ...prev, gemma_service_url: e.target.value }))
                }
              />
            </div>

            <div className="form-group">
              <div className="label-with-hint">
                <label htmlFor="gemma-model-select">Gemma Model Identifier</label>
                <span className="hint-text">Model served by the vLLM instance</span>
              </div>
              <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                <select
                  id="gemma-model-select"
                  className="admin-select"
                  value={
                    GEMMA_MODELS.some((m) => m.id === config?.gemma_model)
                      ? config?.gemma_model
                      : 'custom'
                  }
                  onChange={(e) => {
                    if (e.target.value !== 'custom') {
                      setConfig((prev) => ({ ...prev, gemma_model: e.target.value }));
                    }
                  }}
                >
                  {GEMMA_MODELS.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                  <option value="custom">Custom Model Identifier...</option>
                </select>
                {!GEMMA_MODELS.some((m) => m.id === config?.gemma_model) && (
                  <input
                    type="text"
                    placeholder="e.g. google/gemma-4-E2B-it"
                    className="admin-input mono-font"
                    value={config?.gemma_model || ''}
                    onChange={(e) =>
                      setConfig((prev) => ({ ...prev, gemma_model: e.target.value }))
                    }
                  />
                )}
              </div>
            </div>
          </div>

          {/* Grid 3-col: Timeout, Temperature, Max Tokens */}
          <div className="admin-grid-3col">
            <div className="form-group">
              <div className="label-with-hint">
                <label htmlFor="gemma-timeout">
                  Timeout ({(config?.gemma_timeout_seconds ?? 2.0).toFixed(1)}s)
                </label>
                <span className="hint-text">Per-request HTTP timeout (0.5s - 30.0s)</span>
              </div>
              <input
                id="gemma-timeout"
                type="number"
                step="0.5"
                min="0.5"
                max="30.0"
                className="admin-input mono-font"
                value={config?.gemma_timeout_seconds ?? 2.0}
                onChange={(e) =>
                  setConfig((prev) => ({
                    ...prev,
                    gemma_timeout_seconds: parseFloat(e.target.value) || 2.0,
                  }))
                }
              />
            </div>

            <div className="form-group">
              <div className="label-with-hint">
                <label htmlFor="vllm-temperature">
                  Temperature ({(config?.vllm_temperature ?? 0.0).toFixed(2)})
                </label>
                <span className="hint-text">Sampling randomness (0.0 = deterministic)</span>
              </div>
              <input
                id="vllm-temperature"
                type="range"
                min="0.0"
                max="2.0"
                step="0.05"
                className="threshold-slider"
                value={config?.vllm_temperature ?? 0.0}
                onChange={(e) =>
                  setConfig((prev) => ({
                    ...prev,
                    vllm_temperature: parseFloat(e.target.value),
                  }))
                }
              />
            </div>

            <div className="form-group">
              <div className="label-with-hint">
                <label htmlFor="vllm-max-tokens">
                  Max Tokens ({config?.vllm_max_tokens ?? 32})
                </label>
                <span className="hint-text">Max generation tokens for triage</span>
              </div>
              <input
                id="vllm-max-tokens"
                type="range"
                min="8"
                max="512"
                step="8"
                className="threshold-slider"
                value={config?.vllm_max_tokens ?? 32}
                onChange={(e) =>
                  setConfig((prev) => ({
                    ...prev,
                    vllm_max_tokens: parseInt(e.target.value, 10) || 32,
                  }))
                }
              />
            </div>
          </div>

          {/* Ambiguity Policy Cards */}
          <div className="form-group" style={{ marginTop: '1.25rem' }}>
            <div className="label-with-hint">
              <label>Triage Ambiguity & Unclassified Handling Policy</label>
              <span className="hint-text">
                Determines action when Gemma 4 response contains neither explicit alert nor benign verdict
              </span>
            </div>
            <div className="policy-cards">
              <div
                className={`policy-card ${
                  (config?.ambiguity_policy || 'FAIL_SAFE') === 'FAIL_SAFE'
                    ? 'selected-fail-safe'
                    : ''
                }`}
                onClick={() =>
                  setConfig((prev) => ({ ...prev, ambiguity_policy: 'FAIL_SAFE' }))
                }
              >
                <div className="policy-card-header">
                  <span className="policy-title">FAIL_SAFE (Recommended)</span>
                  <div className="target-radio-indicator">
                    <div
                      className="radio-inner"
                      style={{
                        opacity:
                          (config?.ambiguity_policy || 'FAIL_SAFE') === 'FAIL_SAFE' ? 1 : 0,
                      }}
                    />
                  </div>
                </div>
                <p className="policy-desc">
                  Treat ambiguous or verbose output as suspicious (score 0.80). Automatically escalates
                  the frame to Tier 2 Gemini for verification, preventing missed hazards.
                </p>
              </div>

              <div
                className={`policy-card ${
                  config?.ambiguity_policy === 'CONSERVATIVE' ? 'selected-conservative' : ''
                }`}
                onClick={() =>
                  setConfig((prev) => ({ ...prev, ambiguity_policy: 'CONSERVATIVE' }))
                }
              >
                <div className="policy-card-header">
                  <span className="policy-title">CONSERVATIVE (Cost Saver)</span>
                  <div className="target-radio-indicator">
                    <div
                      className="radio-inner"
                      style={{
                        opacity: config?.ambiguity_policy === 'CONSERVATIVE' ? 1 : 0,
                      }}
                    />
                  </div>
                </div>
                <p className="policy-desc">
                  Treat unclassified output as benign (score 0.20) unless explicit alert keywords appear.
                  Reduces Gemini API calls in high-traffic or benign environments.
                </p>
              </div>
            </div>
          </div>

          {/* Dynamic Keyword Tag Editors */}
          <div className="admin-grid-2col" style={{ marginTop: '1.25rem' }}>
            <KeywordTagEditor
              title="Alert Trigger Keywords"
              subtitle="Tokens indicating suspicious activity, equipment, hazards, or security threats"
              tags={config?.alert_keywords || []}
              chipType="alert"
              placeholder="e.g. equipment, forklift, hazard..."
              onChange={(newTags) =>
                setConfig((prev) => ({ ...prev, alert_keywords: newTags }))
              }
              onResetDefaults={() =>
                setConfig((prev) => ({ ...prev, alert_keywords: [...DEFAULT_ALERT_KEYWORDS] }))
              }
            />

            <KeywordTagEditor
              title="Benign Classification Keywords"
              subtitle="Tokens indicating normal, safe, nominal, or routine campus conditions"
              tags={config?.benign_keywords || []}
              chipType="benign"
              placeholder="e.g. routine, nominal, normal..."
              onChange={(newTags) =>
                setConfig((prev) => ({ ...prev, benign_keywords: newTags }))
              }
              onResetDefaults={() =>
                setConfig((prev) => ({ ...prev, benign_keywords: [...DEFAULT_BENIGN_KEYWORDS] }))
              }
            />
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
                  <h4>Gemini Cloud ({config?.gemini_model || 'gemini-3.6-flash'})</h4>
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
                <span className="target-pill">{config?.gemini_model || 'gemini-3.6-flash'}</span>
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
              <>
                <div className="form-group" style={{ marginBottom: '1.25rem' }}>
                  <div className="label-with-hint">
                    <label htmlFor="gemini-model-select">Gemini Escalation Model</label>
                    <span className="hint-text">
                      Select Vertex AI Gemini model version for Tier 2 escalation
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                    <select
                      id="gemini-model-select"
                      style={{
                        flex: 1,
                        padding: '0.75rem 1rem',
                        borderRadius: '8px',
                        border: '1px solid var(--border-glass)',
                        background: 'rgba(0, 0, 0, 0.45)',
                        color: 'var(--text-primary)',
                        fontFamily: 'var(--font-mono, monospace)',
                        fontSize: '0.9rem',
                        outline: 'none',
                      }}
                      value={
                        GEMINI_MODELS.some((m) => m.id === config?.gemini_model)
                          ? config?.gemini_model
                          : 'custom'
                      }
                      onChange={(e) => {
                        if (e.target.value !== 'custom') {
                          setConfig((prev) => ({ ...prev, gemini_model: e.target.value }));
                        }
                      }}
                    >
                      {GEMINI_MODELS.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.label}
                        </option>
                      ))}
                      <option value="custom">Custom Model Identifier...</option>
                    </select>
                    {!GEMINI_MODELS.some((m) => m.id === config?.gemini_model) && (
                      <input
                        type="text"
                        placeholder="e.g. gemini-3.8-flash"
                        className="admin-textarea mono-font"
                        style={{
                          flex: 1,
                          padding: '0.75rem 1rem',
                          height: 'auto',
                        }}
                        value={config?.gemini_model || ''}
                        onChange={(e) =>
                          setConfig((prev) => ({ ...prev, gemini_model: e.target.value }))
                        }
                      />
                    )}
                  </div>
                </div>

                <div className="form-group">
                  <div className="label-with-hint">
                    <label htmlFor="gemini-escalation-prompt">
                      Gemini Escalation Prompt ({config?.gemini_model || 'gemini-3.6-flash'})
                    </label>
                    <span className="hint-text">
                      Prompt instructing Gemini to analyze campus threat and return schema JSON
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
              </>
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

      {/* Live AI Responses Telemetry Section */}
      <div className="admin-section glass-panel" style={{ marginTop: '2rem' }}>
        <div className="section-header" style={{ justifyContent: 'space-between' }}>
          <div className="section-title-group">
            <div
              className="section-badge"
              style={{ background: 'rgba(0, 242, 254, 0.15)', color: 'var(--accent-cyan)' }}
            >
              <Activity size={16} />
              <span>Live AI Telemetry</span>
            </div>
            <h3>Recent AI Responses &bull; Triage & Escalation Log</h3>
          </div>
          <button
            type="button"
            className="btn-secondary"
            onClick={fetchRecentResponses}
            disabled={loadingResponses}
            style={{
              fontSize: '0.8rem',
              padding: '0.4rem 0.8rem',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem',
            }}
          >
            <RefreshCw size={13} className={loadingResponses ? 'spin-icon' : ''} />
            <span>Refresh Log</span>
          </button>
        </div>

        <p className="section-description">
          Review live raw outputs from frontline Gemma 4 triage and escalated Gemini / Gemma deep reasoning.
        </p>

        {recentResponses.length === 0 ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
            <p>
              No AI inference responses recorded yet in the ring buffer. Start or register drone streams to view live telemetry.
            </p>
          </div>
        ) : (
          <div className="ai-log-table-wrap">
            <table className="ai-log-table">
              <thead>
                <tr>
                  <th>Time / TC</th>
                  <th>Drone ID</th>
                  <th>Pipeline Tier</th>
                  <th>Model Engine</th>
                  <th>Threat / Verdict</th>
                  <th>Latency</th>
                  <th>Scene Summary</th>
                  <th>Raw Output</th>
                </tr>
              </thead>
              <tbody>
                {recentResponses.map((item, idx) => {
                  const isEscalation = item.source_tier === 'escalation';
                  const isGemini = item.source_model === 'gemini';
                  return (
                    <tr key={item.event_id || idx}>
                      <td style={{ whiteSpace: 'nowrap' }}>
                        {item.video_timestamp_formatted
                          ? `TC ${item.video_timestamp_formatted}`
                          : new Date(item.timestamp).toLocaleTimeString()}
                      </td>
                      <td style={{ fontWeight: 600, color: 'var(--accent-cyan)' }}>
                        {item.drone_id}
                      </td>
                      <td>
                        <span
                          className={`alert-tier-tag ${
                            isEscalation
                              ? isGemini
                                ? 'tier-tag-gemini'
                                : 'tier-tag-gemma-escalation'
                              : 'tier-tag-gemma-triage'
                          }`}
                        >
                          {isEscalation ? 'Tier 2 Escalation' : 'Tier 1 Triage'}
                        </span>
                      </td>
                      <td>{item.model_name || (isGemini ? 'Gemini Flash' : 'Gemma 4')}</td>
                      <td>
                        <span
                          style={{
                            fontWeight: 600,
                            color:
                              item.threat_level !== 'CLEAR' && item.threat_level !== 'NONE'
                                ? 'var(--threat-critical)'
                                : 'var(--threat-clear)',
                          }}
                        >
                          {item.threat_level || 'CLEAR'}
                        </span>
                      </td>
                      <td>{item.latency_ms != null ? `${Math.round(item.latency_ms)}ms` : '-'}</td>
                      <td
                        style={{
                          maxWidth: '280px',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                        title={item.scene_summary || item.description}
                      >
                        {item.scene_summary || item.description || '-'}
                      </td>
                      <td>
                        <button
                          type="button"
                          className="btn-hud-raw"
                          onClick={() => setSelectedResponse(item)}
                          disabled={!item.raw_response}
                          style={{ opacity: item.raw_response ? 1 : 0.4 }}
                        >
                          <FileText size={11} style={{ marginRight: '3px' }} />
                          Inspect
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Raw Response Modal in Admin View */}
      {selectedResponse && (
        <div className="raw-modal-backdrop" onClick={() => setSelectedResponse(null)}>
          <div className="raw-modal-dialog glass-panel" onClick={(e) => e.stopPropagation()}>
            <div className="raw-modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                <Cpu size={18} color="var(--accent-cyan)" />
                <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600 }}>
                  AI Response Inspector &bull; {selectedResponse.drone_id}
                </h3>
              </div>
              <button
                type="button"
                className="btn-modal-close"
                onClick={() => setSelectedResponse(null)}
              >
                <X size={16} />
              </button>
            </div>

            <div className="raw-modal-meta-grid">
              <div className="raw-meta-item">
                <span className="raw-meta-label">Pipeline Tier:</span>
                <span className="raw-meta-val">
                  {selectedResponse.source_tier === 'escalation'
                    ? 'Tier 2 Escalation'
                    : 'Tier 1 Triage'}
                </span>
              </div>
              <div className="raw-meta-item">
                <span className="raw-meta-label">Model Engine:</span>
                <span className="raw-meta-val">
                  {selectedResponse.model_name || selectedResponse.source_model}
                </span>
              </div>
              <div className="raw-meta-item">
                <span className="raw-meta-label">Threat Level:</span>
                <span
                  className="raw-meta-val"
                  style={{
                    color:
                      selectedResponse.threat_level !== 'CLEAR' &&
                      selectedResponse.threat_level !== 'NONE'
                        ? 'var(--threat-critical)'
                        : 'var(--threat-clear)',
                  }}
                >
                  {selectedResponse.threat_level || 'CLEAR'}
                </span>
              </div>
              <div className="raw-meta-item">
                <span className="raw-meta-label">Confidence:</span>
                <span className="raw-meta-val">
                  {selectedResponse.confidence_score != null
                    ? `${(selectedResponse.confidence_score * 100).toFixed(1)}%`
                    : 'N/A'}
                </span>
              </div>
              <div className="raw-meta-item">
                <span className="raw-meta-label">Latency:</span>
                <span className="raw-meta-val">
                  {selectedResponse.latency_ms != null
                    ? `${selectedResponse.latency_ms.toFixed(1)} ms`
                    : 'N/A'}
                </span>
              </div>
              <div className="raw-meta-item">
                <span className="raw-meta-label">Timecode:</span>
                <span className="raw-meta-val">
                  {selectedResponse.video_timestamp_formatted || 'N/A'}
                </span>
              </div>
            </div>

            <div className="raw-modal-section">
              <div className="raw-section-title">Scene Summary</div>
              <div className="raw-summary-box">
                {selectedResponse.scene_summary ||
                  selectedResponse.description ||
                  '(No summary recorded)'}
              </div>
            </div>

            <div className="raw-modal-section">
              <div className="raw-section-header">
                <span className="raw-section-title">Raw Model Response Output</span>
                <button
                  type="button"
                  className="btn-copy-raw"
                  onClick={() => {
                    navigator.clipboard.writeText(selectedResponse.raw_response || '');
                    setCopiedResponse(true);
                    setTimeout(() => setCopiedResponse(false), 2000);
                  }}
                >
                  {copiedResponse ? (
                    <>
                      <Check size={12} color="#00e676" />
                      <span style={{ color: '#00e676' }}>Copied!</span>
                    </>
                  ) : (
                    <>
                      <Copy size={12} />
                      <span>Copy Output</span>
                    </>
                  )}
                </button>
              </div>
              <pre className="raw-response-pre">
                {selectedResponse.raw_response || '(No raw model response payload captured)'}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
