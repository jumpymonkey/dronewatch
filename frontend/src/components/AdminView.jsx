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
  {
    id: 'google/diffusiongemma-26B-A4B-it',
    label: 'google/diffusiongemma-26B-A4B-it (DiffusionGemma Block-Denoising MoE)',
  },
  { id: 'google/gemma-3-4b-it', label: 'google/gemma-3-4b-it (Gemma 3 4B Vision / Instruct)' },
  { id: 'google/gemma-4-4b-it', label: 'google/gemma-4-4b-it (Gemma 4 4B Multimodal)' },
  { id: 'google/gemma-4-9b-it', label: 'google/gemma-4-9b-it (Gemma 4 9B High Capacity)' },
  { id: 'google/gemma-2-2b-it', label: 'google/gemma-2-2b-it (Lightweight 2B Edge)' },
];

const DEFAULT_SYSTEM1_PROMPT =
  'Evaluate this campus security drone frame. Classify into exactly one label:\n' +
  '- SAFE: Normal routine campus scene, empty area, or authorized walkway use.\n' +
  '- SUSPICIOUS: Ambiguous motion, unattended object, loitering, or walkway obstruction.\n' +
  '- CRITICAL: Active perimeter breach, intruder climbing, weapon, fire, or imminent danger.\n' +
  'Respond with one word only: SAFE, SUSPICIOUS, or CRITICAL.';

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

  const normalizeConfig = (data) => {
    const rawSuppress = data.suppress_threshold ?? 0.25;
    const rawEscalate = data.gemma_triage_threshold ?? 0.5;
    const inverted = rawEscalate < rawSuppress;
    return {
      ...data,
      triage_mode: 'DECISION_FRAMEWORK',
      suppress_threshold: inverted ? 0.25 : rawSuppress,
      gemma_triage_threshold: inverted ? 0.5 : rawEscalate,
      dispatch_confidence_threshold:
        data.dispatch_confidence_threshold != null ? data.dispatch_confidence_threshold : null,
      corroboration_hits: data.corroboration_hits ?? 2,
      corroboration_window: data.corroboration_window ?? 3,
      escalation_cooldown_seconds: data.escalation_cooldown_seconds ?? 3.0,
      ambiguity_policy: 'FAIL_SAFE',
      gemma_model: data.gemma_model || 'google/gemma-4-E2B-it',
      gemma_timeout_seconds: data.gemma_timeout_seconds ?? 2.0,
      vllm_temperature: data.vllm_temperature ?? 0.0,
      vllm_max_tokens: data.vllm_max_tokens ?? 32,
    };
  };

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
      config.suppress_threshold !== initialConfig.suppress_threshold ||
      config.gemma_triage_threshold !== initialConfig.gemma_triage_threshold ||
      config.dispatch_confidence_threshold !== initialConfig.dispatch_confidence_threshold ||
      config.corroboration_hits !== initialConfig.corroboration_hits ||
      config.corroboration_window !== initialConfig.corroboration_window ||
      config.escalation_cooldown_seconds !== initialConfig.escalation_cooldown_seconds ||
      config.escalation_target !== initialConfig.escalation_target ||
      config.gemini_escalation_prompt !== initialConfig.gemini_escalation_prompt ||
      config.gemma_escalation_prompt !== initialConfig.gemma_escalation_prompt ||
      config.gemini_model !== initialConfig.gemini_model ||
      config.gemma_model !== initialConfig.gemma_model ||
      (config.gemma_service_url || '') !== (initialConfig.gemma_service_url || '') ||
      config.gemma_timeout_seconds !== initialConfig.gemma_timeout_seconds ||
      config.vllm_temperature !== initialConfig.vllm_temperature ||
      config.vllm_max_tokens !== initialConfig.vllm_max_tokens);

  const handleSave = async (e) => {
    if (e) e.preventDefault();
    if (!config) return;

    setSaving(true);
    setStatusMessage(null);
    setErrorMessage(null);

    const payload = {
      enable_tier1_gemma: config.enable_tier1_gemma,
      triage_mode: 'DECISION_FRAMEWORK',
      gemma_triage_prompt: config.gemma_triage_prompt,
      suppress_threshold: parseFloat(config.suppress_threshold),
      gemma_triage_threshold: parseFloat(config.gemma_triage_threshold),
      dispatch_confidence_threshold:
        config.dispatch_confidence_threshold != null
          ? parseFloat(config.dispatch_confidence_threshold)
          : null,
      corroboration_hits: parseInt(config.corroboration_hits, 10),
      corroboration_window: parseInt(config.corroboration_window, 10),
      escalation_cooldown_seconds: parseFloat(config.escalation_cooldown_seconds),
      escalation_target: config.escalation_target,
      gemini_escalation_prompt: config.gemini_escalation_prompt,
      gemma_escalation_prompt: config.gemma_escalation_prompt,
      gemini_model: config.gemini_model,
      gemma_model: config.gemma_model,
      gemma_service_url: config.gemma_service_url?.trim() || null,
      gemma_timeout_seconds: parseFloat(config.gemma_timeout_seconds),
      ambiguity_policy: 'FAIL_SAFE',
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
            Low-latency local screening using Google Gemma 4 on Cloud Run. System 1 Decision Framework
            uses constrained vLLM choice (`SAFE` / `SUSPICIOUS` / `CRITICAL`) and exact softmax logprob
            calibration with 3-band non-blocking routing.
          </p>

          <div
            className={`section-body-collapsible ${
              !config?.enable_tier1_gemma ? 'disabled-dim' : ''
            }`}
          >
            {/* Active Tier 1 Decision Engine Mode Banner */}
            <div className="form-group" style={{ marginBottom: '1.25rem' }}>
              <div className="label-with-hint">
                <label>Tier 1 Decision Engine Mode</label>
                <span className="hint-text">
                  Canonical System 1 calibrated logprob engine (legacy keyword mode retired)
                </span>
              </div>
              <div
                className="policy-card selected-fail-safe"
                style={{ cursor: 'default' }}
              >
                <div className="policy-card-header">
                  <span className="policy-title">
                    DECISION_FRAMEWORK (Active &bull; System 1 vLLM Logprobs)
                  </span>
                </div>
                <p className="policy-desc">
                  Constrained 1-token decoding (SAFE, SUSPICIOUS, CRITICAL) with exact softmax
                  calibration over vLLM top_logprobs, Shannon entropy awareness, and 3-band
                  temporal corroboration.
                </p>
              </div>
            </div>

            <div className="form-group">
              <div className="label-with-hint">
                <label htmlFor="gemma-triage-prompt">
                  System 1 Choice Rubric Prompt (SAFE / SUSPICIOUS / CRITICAL)
                </label>
                <span className="hint-text">
                  Constrained 3-class rubric evaluated by Gemma 4 with vLLM guided_choice &amp; top_logprobs
                </span>
              </div>
              <textarea
                id="gemma-triage-prompt"
                rows={5}
                className="admin-textarea mono-font"
                value={config?.gemma_triage_prompt || ''}
                disabled={!config?.enable_tier1_gemma}
                onChange={(e) =>
                  setConfig((prev) => ({ ...prev, gemma_triage_prompt: e.target.value }))
                }
                placeholder={DEFAULT_SYSTEM1_PROMPT}
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
            <div className="admin-grid-2col">
              <div>
                <div className="label-with-hint">
                  <label htmlFor="suppress-threshold">
                    Band 0 Suppress Ceiling: P(threat) &lt;{' '}
                    {(config?.suppress_threshold ?? 0.25).toFixed(2)}
                  </label>
                  <span className="hint-text">
                    Frames below ceiling drop immediately at zero API cost (Default: 0.25)
                  </span>
                </div>
                <div className="threshold-control-row">
                  <input
                    id="suppress-threshold"
                    type="range"
                    min="0.05"
                    max="0.80"
                    step="0.05"
                    className="threshold-slider"
                    value={config?.suppress_threshold ?? 0.25}
                    onChange={(e) => {
                      const nextSuppress = parseFloat(e.target.value);
                      setConfig((prev) => ({
                        ...prev,
                        suppress_threshold: nextSuppress,
                        gemma_triage_threshold: Math.max(
                          prev.gemma_triage_threshold ?? 0.5,
                          nextSuppress
                        ),
                      }));
                    }}
                  />
                  <div className="threshold-value-badge">
                    {(config?.suppress_threshold ?? 0.25).toFixed(2)}
                  </div>
                </div>
              </div>

              <div>
                <div className="label-with-hint">
                  <label htmlFor="gemma-threshold">
                    Band 2 Immediate Escalation: P(threat) &ge;{' '}
                    {(config?.gemma_triage_threshold ?? 0.5).toFixed(2)}
                  </label>
                  <span className="hint-text">
                    Default: 0.50 &bull; Band 1 Corroboration Interval: [
                    {(config?.suppress_threshold ?? 0.25).toFixed(2)},{' '}
                    {(config?.gemma_triage_threshold ?? 0.5).toFixed(2)})
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
                    value={config?.gemma_triage_threshold ?? 0.5}
                    onChange={(e) => {
                      const nextEscalate = parseFloat(e.target.value);
                      setConfig((prev) => ({
                        ...prev,
                        gemma_triage_threshold: nextEscalate,
                        suppress_threshold: Math.min(
                          prev.suppress_threshold ?? 0.25,
                          nextEscalate
                        ),
                      }));
                    }}
                  />
                  <div className="threshold-value-badge">
                    {(config?.gemma_triage_threshold ?? 0.5).toFixed(2)}
                  </div>
                </div>
              </div>
            </div>

            {/* Band 1 Temporal Corroboration & Anti-Snowball Cooldown */}
            <div className="admin-grid-3col" style={{ marginTop: '1.1rem' }}>
              <div className="form-group">
                <div className="label-with-hint">
                  <label htmlFor="corroboration-hits">
                    Band 1 Corroboration Hits (k = {config?.corroboration_hits ?? 2})
                  </label>
                  <span className="hint-text">Required hits within ring buffer window</span>
                </div>
                <input
                  id="corroboration-hits"
                  type="number"
                  min="1"
                  max={config?.corroboration_window ?? 3}
                  step="1"
                  className="admin-input mono-font"
                  value={config?.corroboration_hits ?? 2}
                  onChange={(e) => {
                    const nextHits = Math.max(1, parseInt(e.target.value, 10) || 1);
                    setConfig((prev) => ({
                      ...prev,
                      corroboration_hits: nextHits,
                      corroboration_window: Math.max(prev.corroboration_window ?? 3, nextHits),
                    }));
                  }}
                />
              </div>

              <div className="form-group">
                <div className="label-with-hint">
                  <label htmlFor="corroboration-window">
                    Corroboration Window (n = {config?.corroboration_window ?? 3} frames)
                  </label>
                  <span className="hint-text">O(1) non-blocking ring buffer depth</span>
                </div>
                <input
                  id="corroboration-window"
                  type="number"
                  min={config?.corroboration_hits ?? 2}
                  max="10"
                  step="1"
                  className="admin-input mono-font"
                  value={config?.corroboration_window ?? 3}
                  onChange={(e) => {
                    const nextWin = Math.min(
                      10,
                      Math.max(config?.corroboration_hits ?? 1, parseInt(e.target.value, 10) || 3)
                    );
                    setConfig((prev) => ({
                      ...prev,
                      corroboration_window: nextWin,
                    }));
                  }}
                />
              </div>

              <div className="form-group">
                <div className="label-with-hint">
                  <label htmlFor="escalation-cooldown">
                    Anti-Snowball Cooldown ({(config?.escalation_cooldown_seconds ?? 3.0).toFixed(1)}s)
                  </label>
                  <span className="hint-text">Single-flight + non-CRITICAL shed window</span>
                </div>
                <input
                  id="escalation-cooldown"
                  type="number"
                  min="0.0"
                  max="60.0"
                  step="0.5"
                  className="admin-input mono-font"
                  value={config?.escalation_cooldown_seconds ?? 3.0}
                  onChange={(e) =>
                    setConfig((prev) => ({
                      ...prev,
                      escalation_cooldown_seconds: Math.max(
                        0.0,
                        parseFloat(e.target.value) || 0.0
                      ),
                    }))
                  }
                />
              </div>
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

          {/* Mandatory FAIL_SAFE Unclassified Fallback Policy Banner */}
          <div className="form-group" style={{ marginTop: '1.25rem' }}>
            <div className="label-with-hint">
              <label>Unclassified &amp; Circuit-Breaker Safety Policy</label>
              <span className="hint-text">
                Mandatory fail-safe behavior when logprobs or constrained choice tokens are unavailable
              </span>
            </div>
            <div className="policy-card selected-fail-safe" style={{ cursor: 'default' }}>
              <div className="policy-card-header">
                <span className="policy-title">
                  FAIL_SAFE (Active &bull; Zero Keyword Configuration Required)
                </span>
              </div>
              <p className="policy-desc">
                System 1 triage relies on calibrated vLLM logprobs over SAFE / SUSPICIOUS / CRITICAL
                rather than fragile keyword lists. Any uncalibrated, ambiguous, or timed-out Tier 1
                response unconditionally fails safe to Tier 2 verification so hazards are never missed.
              </p>
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

          {/* Decoupled Tier 2 Dispatch Confidence Policy */}
          <div
            className="form-group threshold-group"
            style={{
              marginTop: '1.25rem',
              paddingTop: '1.25rem',
              borderTop: '1px solid rgba(255, 255, 255, 0.08)',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '0.5rem',
              }}
            >
              <div className="label-with-hint" style={{ marginBottom: 0 }}>
                <label htmlFor="dispatch-threshold">
                  Tier 2 Alert Dispatch Confidence Cutoff
                </label>
                <span className="hint-text">
                  Decouple sensitive Tier 1 screening from high-precision Tier 2 operator sirens
                </span>
              </div>
              <label
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  fontSize: '0.8rem',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer',
                }}
              >
                <input
                  type="checkbox"
                  checked={config?.dispatch_confidence_threshold != null}
                  onChange={(e) =>
                    setConfig((prev) => ({
                      ...prev,
                      dispatch_confidence_threshold: e.target.checked
                        ? prev.gemma_triage_threshold ?? 0.65
                        : null,
                    }))
                  }
                />
                <span>Use Independent Tier 2 Cutoff</span>
              </label>
            </div>

            {config?.dispatch_confidence_threshold != null ? (
              <div className="threshold-control-row">
                <input
                  id="dispatch-threshold"
                  type="range"
                  min="0.10"
                  max="0.95"
                  step="0.05"
                  className="threshold-slider"
                  value={config.dispatch_confidence_threshold}
                  onChange={(e) =>
                    setConfig((prev) => ({
                      ...prev,
                      dispatch_confidence_threshold: parseFloat(e.target.value),
                    }))
                  }
                />
                <div className="threshold-value-badge">
                  {config.dispatch_confidence_threshold.toFixed(2)}
                </div>
                <span className="threshold-level-tag">
                  Independent Tier 2 Policy Cutoff
                </span>
              </div>
            ) : (
              <div
                style={{
                  fontSize: '0.8rem',
                  color: 'var(--text-muted)',
                  padding: '0.45rem 0.75rem',
                  borderRadius: '6px',
                  background: 'rgba(255, 255, 255, 0.03)',
                }}
              >
                Inheriting Tier 1 Band 2 Escalation Cutoff (
                <strong>{(config?.gemma_triage_threshold ?? 0.5).toFixed(2)}</strong>)
              </div>
            )}
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
          Review live raw outputs, routing actions, and dispatch policy decisions from frontline Gemma 4 triage and escalated Gemini / Gemma deep reasoning.
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
                  <th>Decision Action</th>
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
                  const decisionLabel =
                    item.dispatch_action && item.dispatch_action !== 'CLEAR_ROUTINE'
                      ? `${item.routing_action || 'TIER2'} → ${item.dispatch_action}`
                      : item.routing_action || item.dispatch_action || '-';
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
                      <td style={{ fontSize: '0.75rem', fontFamily: 'var(--font-mono, monospace)' }}>
                        {decisionLabel}
                      </td>
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
                          maxWidth: '240px',
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
                <span className="raw-meta-label">Routing Action:</span>
                <span className="raw-meta-val">
                  {selectedResponse.routing_action || 'N/A'}
                </span>
              </div>
              <div className="raw-meta-item">
                <span className="raw-meta-label">Dispatch Action:</span>
                <span className="raw-meta-val">
                  {selectedResponse.dispatch_action || 'N/A'}
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
