import React, { useState } from 'react';
import {
  Camera,
  MapPin,
  AlertCircle,
  Trash2,
  PlusCircle,
  Cpu,
  Eye,
  ShieldCheck,
  FileText,
  Copy,
  Check,
  X,
  Sparkles,
  Activity,
} from 'lucide-react';

export default function StreamGrid({
  streams,
  activeAlerts,
  telemetry = {},
  decisionTelemetry = {},
  onUnregisterStream,
  onOpenRegisterModal,
}) {
  const maxStreams = 4;
  const emptySlots = Math.max(0, maxStreams - streams.length);
  const [selectedRawResponse, setSelectedRawResponse] = useState(null);
  const [copied, setCopied] = useState(false);

  const handleCopyRaw = (text) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const getVideoSource = (stream) => {
    if (stream.stream_url && (stream.stream_url.startsWith('http://') || stream.stream_url.startsWith('https://'))) {
      return stream.stream_url;
    }
    const streamParam = stream.stream_url ? `?stream_url=${encodeURIComponent(stream.stream_url)}` : '';
    return `/api/streams/${encodeURIComponent(stream.drone_id)}/video${streamParam}`;
  };

  const getRoutingPillClass = (action) => {
    if (!action) return 'decision-pill-suppress';
    if (action === 'SUPPRESS') return 'decision-pill-suppress';
    if (action === 'CORROBORATE_HOLD') return 'decision-pill-hold';
    if (action === 'COOLDOWN_SKIP') return 'decision-pill-cooldown';
    return 'decision-pill-escalate';
  };

  return (
    <div className="streams-container">
      {streams.map((stream) => {
        const droneTelemetry = telemetry[stream.drone_id];
        const decision = decisionTelemetry[stream.drone_id];
        const hasAlert = activeAlerts.some(
          (a) => a.drone_id === stream.drone_id && !a.acknowledged_by_pilot
        );

        const threatLevel = droneTelemetry?.threat_level || (hasAlert ? 'ALERT' : 'CLEAR');
        const isThreat = threatLevel !== 'CLEAR' && threatLevel !== 'NONE';

        // Dynamic AI reasoning provenance
        const sourceTier = droneTelemetry?.source_tier || (isThreat ? 'escalation' : 'triage');
        const sourceModel = droneTelemetry?.source_model || (isThreat ? 'gemini' : 'gemma');
        const isEscalation = sourceTier === 'escalation';
        const isGemini = sourceModel === 'gemini';
        const modelLabel = droneTelemetry?.model_name || (isGemini ? 'Gemini Flash' : 'Gemma 4');
        const tierLabel = isEscalation ? 'Tier 2 Escalation' : 'Tier 1 Triage';

        // System 1 Decision Engine live metrics
        const pThreat = decision?.p_threat ?? null;
        const suppressThresh = decision?.suppress_threshold ?? 0.25;
        const escalateThresh = decision?.escalate_threshold ?? 0.5;
        const windowCap = decision?.corroboration_window_capacity ?? 3;
        const windowHits = decision?.window_hits ?? 0;
        const hitsRequired = decision?.corroboration_hits_required ?? 2;
        const counts = decision?.counts || {};
        const totalEval = counts.total_evaluated || 0;
        const nonEscalated = (counts.suppressed || 0) + (counts.corroborate_hold || 0) + (counts.cooldown_skip || 0);
        const savedPct = totalEval > 0 ? Math.round((nonEscalated / totalEval) * 100) : 100;
        const meterFillClass =
          pThreat == null
            ? 'meter-band0'
            : pThreat >= escalateThresh
            ? 'meter-band2'
            : pThreat >= suppressThresh
            ? 'meter-band1'
            : 'meter-band0';

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

            {/* Live AI Telemetry HUD Banner */}
            <div className={`gemini-hud-banner ${isThreat ? 'threat-active' : ''}`}>
              {/* Real-Time System 1 Decision Engine Strip (Updates Every 1 FPS Frame) */}
              <div className="decision-hud-strip">
                {decision ? (
                  <>
                    <div className="decision-hud-top">
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', flexWrap: 'wrap' }}>
                        <span
                          className={`decision-mode-tag ${
                            decision.calibrated_from_logprobs ? 'mode-logprob' : 'mode-keyword'
                          }`}
                          title={
                            decision.calibrated_from_logprobs
                              ? 'Calibrated via exact vLLM top-logprobs softmax'
                              : `Mode: ${decision.triage_mode}`
                          }
                        >
                          <Activity size={10} style={{ marginRight: '3px' }} />
                          {decision.calibrated_from_logprobs ? 'SYS-1 LOGPROB' : 'SYS-1 GATE'}
                        </span>
                        <span
                          className={`decision-action-pill ${getRoutingPillClass(decision.routing_action)}`}
                          title={`Reason: ${decision.reason}`}
                        >
                          {decision.routing_action}
                        </span>
                        {decision.dispatch_action && decision.dispatch_action !== 'CLEAR_ROUTINE' && (
                          <span className="decision-dispatch-tag">
                            &rarr; {decision.dispatch_action}
                          </span>
                        )}
                      </div>
                      <span className="decision-hud-timing">
                        {decision.video_timestamp_formatted
                          ? `TC ${decision.video_timestamp_formatted} • `
                          : ''}
                        {Math.round(decision.latency_ms || 0)}ms
                      </span>
                    </div>

                    <div className="decision-hud-meter-row">
                      <span
                        className="decision-p-readout"
                        title={`P(SAFE)=${(decision.p_safe ?? 1).toFixed(3)} | P(SUSP)=${(
                          decision.p_suspicious ?? 0
                        ).toFixed(3)} | P(CRIT)=${(decision.p_critical ?? 0).toFixed(3)}`}
                      >
                        P(threat): <strong>{pThreat.toFixed(3)}</strong>
                        <span className="decision-entropy">H={Number(decision.entropy || 0).toFixed(2)}</span>
                      </span>

                      <div
                        className="p-threat-meter-track"
                        title={`3-Band Gate: Suppress < ${suppressThresh.toFixed(
                          2
                        )} | Corroborate [${suppressThresh.toFixed(2)}, ${escalateThresh.toFixed(
                          2
                        )}) | Escalate >= ${escalateThresh.toFixed(2)}`}
                      >
                        <div
                          className={`p-threat-meter-fill ${meterFillClass}`}
                          style={{ width: `${Math.min(100, Math.max(2, pThreat * 100))}%` }}
                        />
                        <div
                          className="p-threat-marker marker-suppress"
                          style={{ left: `${suppressThresh * 100}%` }}
                        />
                        <div
                          className="p-threat-marker marker-escalate"
                          style={{ left: `${escalateThresh * 100}%` }}
                        />
                      </div>

                      <div
                        className="corroboration-dots"
                        title={`Temporal k-of-n Corroboration Buffer: ${windowHits}/${windowCap} active Band 1+ hits (k=${hitsRequired} required)`}
                      >
                        {Array.from({ length: Math.min(windowCap, 8) }).map((_, idx) => (
                          <span
                            key={idx}
                            className={`corrob-dot ${idx < windowHits ? 'hit' : ''}`}
                          />
                        ))}
                        <span className="corrob-label">
                          {windowHits}/{windowCap}
                        </span>
                      </div>
                    </div>

                    <div className="decision-counters-row">
                      <span>Frames: <strong>{totalEval}</strong></span>
                      <span className="cnt-sep">&bull;</span>
                      <span className="cnt-good">
                        Suppressed: <strong>{counts.suppressed || 0}</strong> ({savedPct}% Saved)
                      </span>
                      <span className="cnt-sep">&bull;</span>
                      <span className="cnt-warn">Held: <strong>{counts.corroborate_hold || 0}</strong></span>
                      <span className="cnt-sep">&bull;</span>
                      <span className="cnt-esc">Escalated: <strong>{counts.escalated || 0}</strong></span>
                      {(counts.cooldown_skip || 0) > 0 && (
                        <>
                          <span className="cnt-sep">&bull;</span>
                          <span className="cnt-shed">Shed: <strong>{counts.cooldown_skip}</strong></span>
                        </>
                      )}
                    </div>
                  </>
                ) : (
                  <div className="decision-hud-idle">
                    <Activity size={11} color="var(--accent-cyan)" />
                    <span>SYS-1 Decision Framework armed &bull; awaiting first motion-gated frame...</span>
                  </div>
                )}
              </div>

              <div className="gemini-hud-header">
                {isEscalation ? (
                  isGemini ? (
                    <span className="gemini-badge threat-badge-hud" title={`Escalated to ${modelLabel}`}>
                      <Sparkles size={12} style={{ marginRight: '4px' }} />
                      Tier 2 Escalation &bull; {modelLabel}
                    </span>
                  ) : (
                    <span className="gemini-badge escalation-gemma-badge" title="Escalated to Gemma 4">
                      <Cpu size={12} style={{ marginRight: '4px' }} />
                      Tier 2 Escalation &bull; Gemma 4
                    </span>
                  )
                ) : (
                  <span className="gemini-badge gemma-badge-hud" title="Frontline Gemma 4 Triage">
                    <Cpu size={12} style={{ marginRight: '4px' }} />
                    Tier 1 Triage &bull; Gemma 4
                  </span>
                )}

                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  {droneTelemetry?.latency_ms != null && (
                    <span className="hud-latency-pill" title="Inference Latency">
                      {Math.round(droneTelemetry.latency_ms)}ms
                    </span>
                  )}
                  <span className="gemini-hud-time">
                    {droneTelemetry?.video_timestamp_formatted
                      ? `TC ${droneTelemetry.video_timestamp_formatted} • ${new Date(
                          droneTelemetry.timestamp
                        ).toLocaleTimeString()}`
                      : droneTelemetry?.timestamp
                      ? new Date(droneTelemetry.timestamp).toLocaleTimeString()
                      : 'Awaiting heartbeat...'}
                  </span>
                </div>
              </div>

              {/* HUD Scene Summary with Explicit Provenance Origin */}
              <div className="gemini-hud-body">
                <div className="hud-origin-row">
                  <span
                    className={`hud-origin-pill ${
                      isEscalation
                        ? isGemini
                          ? 'origin-escalation-gemini'
                          : 'origin-escalation-gemma'
                        : 'origin-triage-gemma'
                    }`}
                  >
                    Summary Origin: {tierLabel} ({modelLabel})
                  </span>

                  {droneTelemetry?.raw_response && (
                    <button
                      type="button"
                      className="btn-hud-raw"
                      onClick={() => setSelectedRawResponse(droneTelemetry)}
                      title="Inspect full raw AI response"
                    >
                      <FileText size={11} style={{ marginRight: '3px' }} />
                      RAW
                    </button>
                  )}
                </div>

                <div className="hud-summary-text-row">
                  <Eye size={13} className="hud-eye-icon" />
                  <span className="hud-description">
                    {droneTelemetry?.scene_summary ||
                      droneTelemetry?.description ||
                      'Active stream monitoring: triaging frames...'}
                  </span>
                </div>
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
                  {droneTelemetry?.category || 'SUSPICIOUS ACTIVITY'} (
                  {droneTelemetry?.confidence_score
                    ? (droneTelemetry.confidence_score * 100).toFixed(0)
                    : 92}
                  %)
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

      {/* Raw AI Response Inspector Modal */}
      {selectedRawResponse && (
        <div className="raw-modal-backdrop" onClick={() => setSelectedRawResponse(null)}>
          <div className="raw-modal-dialog glass-panel" onClick={(e) => e.stopPropagation()}>
            <div className="raw-modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                <Cpu size={18} color="var(--accent-cyan)" />
                <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600 }}>
                  AI Response Inspector &bull; {selectedRawResponse.drone_id}
                </h3>
              </div>
              <button
                type="button"
                className="btn-modal-close"
                onClick={() => setSelectedRawResponse(null)}
              >
                <X size={16} />
              </button>
            </div>

            <div className="raw-modal-meta-grid">
              <div className="raw-meta-item">
                <span className="raw-meta-label">Pipeline Tier:</span>
                <span className="raw-meta-val">
                  {selectedRawResponse.source_tier === 'escalation'
                    ? 'Tier 2 Escalation'
                    : 'Tier 1 Triage'}
                </span>
              </div>
              <div className="raw-meta-item">
                <span className="raw-meta-label">Model Engine:</span>
                <span className="raw-meta-val">
                  {selectedRawResponse.model_name || selectedRawResponse.source_model}
                </span>
              </div>
              <div className="raw-meta-item">
                <span className="raw-meta-label">Threat Level:</span>
                <span
                  className="raw-meta-val"
                  style={{
                    color:
                      selectedRawResponse.threat_level !== 'CLEAR' &&
                      selectedRawResponse.threat_level !== 'NONE'
                        ? 'var(--threat-critical)'
                        : 'var(--threat-clear)',
                  }}
                >
                  {selectedRawResponse.threat_level || 'CLEAR'}
                </span>
              </div>
              <div className="raw-meta-item">
                <span className="raw-meta-label">Confidence:</span>
                <span className="raw-meta-val">
                  {selectedRawResponse.confidence_score != null
                    ? `${(selectedRawResponse.confidence_score * 100).toFixed(1)}%`
                    : 'N/A'}
                </span>
              </div>
              <div className="raw-meta-item">
                <span className="raw-meta-label">Latency:</span>
                <span className="raw-meta-val">
                  {selectedRawResponse.latency_ms != null
                    ? `${selectedRawResponse.latency_ms.toFixed(1)} ms`
                    : 'N/A'}
                </span>
              </div>
              <div className="raw-meta-item">
                <span className="raw-meta-label">Timecode:</span>
                <span className="raw-meta-val">
                  {selectedRawResponse.video_timestamp_formatted || 'N/A'}
                </span>
              </div>
              {selectedRawResponse.routing_action && (
                <div className="raw-meta-item">
                  <span className="raw-meta-label">Routing Action:</span>
                  <span className="raw-meta-val" style={{ color: 'var(--accent-cyan)' }}>
                    {selectedRawResponse.routing_action}
                  </span>
                </div>
              )}
              {selectedRawResponse.dispatch_action && (
                <div className="raw-meta-item">
                  <span className="raw-meta-label">Dispatch Action:</span>
                  <span className="raw-meta-val" style={{ color: '#00e676' }}>
                    {selectedRawResponse.dispatch_action}
                  </span>
                </div>
              )}
            </div>

            <div className="raw-modal-section">
              <div className="raw-section-title">Scene Summary</div>
              <div className="raw-summary-box">
                {selectedRawResponse.scene_summary ||
                  selectedRawResponse.description ||
                  '(No summary recorded)'}
              </div>
            </div>

            <div className="raw-modal-section">
              <div className="raw-section-header">
                <span className="raw-section-title">Raw Model Response Output</span>
                <button
                  type="button"
                  className="btn-copy-raw"
                  onClick={() => handleCopyRaw(selectedRawResponse.raw_response)}
                >
                  {copied ? (
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
                {selectedRawResponse.raw_response || '(No raw model response payload captured)'}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
