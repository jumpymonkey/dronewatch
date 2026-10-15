import React, { useState, useEffect } from 'react';

export default function RegisterStreamModal({ isOpen, onClose, onRegister }) {
  const [droneId, setDroneId] = useState('');
  const [zoneName, setZoneName] = useState('');
  const [streamType, setStreamType] = useState('GCS'); // GCS, LOCAL, RTSP
  const [streamUrl, setStreamUrl] = useState('');
  const [availableVideos, setAvailableVideos] = useState([]);
  const [selectedVideo, setSelectedVideo] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    fetch('/api/videos')
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setAvailableVideos(data);
        }
      })
      .catch((err) => console.warn('Could not load videos from GCS:', err));
  }, []);

  if (!isOpen) return null;

  const handleFillSample = () => {
    setDroneId('Drone-S100');
    setZoneName('North Campus Patrol Route');
    if (streamType === 'GCS') {
      const sampleUrl = 'gs://jal-dronewatch-videos/S1002353.MP4';
      setStreamUrl(sampleUrl);
      setSelectedVideo(sampleUrl);
    } else if (streamType === 'RTSP') {
      setStreamUrl('rtsp://192.168.1.100:554/stream1');
    } else {
      setStreamUrl('/home/jeffleinen/jeffdev/dronevideos/videos/S1002353.MP4');
    }
  };

  const handleVideoSelect = (url) => {
    setSelectedVideo(url);
    setStreamUrl(url);
    const videoObj = availableVideos.find((v) => v.gcs_url === url);
    if (videoObj) {
      const cleanName = videoObj.name.replace(/\.[^/.]+$/, '');
      if (!droneId || droneId.startsWith('Drone-')) {
        setDroneId(`Drone-${cleanName}`);
      }
      if (!zoneName || zoneName.startsWith('Zone Patrol')) {
        setZoneName(`Zone Patrol (${cleanName})`);
      }
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    setError('');

    if (!droneId.trim() || !zoneName.trim() || !streamUrl.trim()) {
      setError('All fields are required.');
      return;
    }

    onRegister({
      drone_id: droneId.trim(),
      zone_name: zoneName.trim(),
      stream_url: streamUrl.trim(),
    });

    // Reset form
    setDroneId('');
    setZoneName('');
    setStreamUrl('');
    setSelectedVideo('');
    onClose();
  };

  return (
    <div className="modal-backdrop">
      <div className="modal-content glass-card">
        <div className="modal-header">
          <h3>Register New Drone Video Feed</h3>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>

        {error && <div className="error-badge">{error}</div>}

        <form onSubmit={handleSubmit} className="register-form">
          <div className="form-group">
            <label>Stream Source Type</label>
            <div className="stream-type-selector">
              <button
                type="button"
                className={`type-btn ${streamType === 'GCS' ? 'active' : ''}`}
                onClick={() => setStreamType('GCS')}
              >
                Cloud Storage (GCS)
              </button>
              <button
                type="button"
                className={`type-btn ${streamType === 'LOCAL' ? 'active' : ''}`}
                onClick={() => setStreamType('LOCAL')}
              >
                Local MP4 File
              </button>
              <button
                type="button"
                className={`type-btn ${streamType === 'RTSP' ? 'active' : ''}`}
                onClick={() => setStreamType('RTSP')}
              >
                RTSP Live Feed
              </button>
            </div>
          </div>

          {streamType === 'GCS' && availableVideos.length > 0 && (
            <div className="form-group">
              <label>Select Video from Cloud Storage</label>
              <select
                value={selectedVideo}
                onChange={(e) => handleVideoSelect(e.target.value)}
              >
                <option value="">-- Choose video from gs://jal-dronewatch-videos --</option>
                {availableVideos.map((vid) => (
                  <option key={vid.gcs_url} value={vid.gcs_url}>
                    {vid.name} ({vid.size_mb} MB)
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="form-group">
            <label>Drone Callsign / ID</label>
            <input
              type="text"
              placeholder="e.g. Drone-Alpha or Patrol-01"
              value={droneId}
              onChange={(e) => setDroneId(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label>Patrol Zone Name</label>
            <input
              type="text"
              placeholder="e.g. Executive Parking Garage B"
              value={zoneName}
              onChange={(e) => setZoneName(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label>
              {streamType === 'RTSP'
                ? 'RTSP Stream URL (rtsp://...)'
                : streamType === 'GCS'
                ? 'GCS Bucket Path (gs://...)'
                : 'Local MP4 File Path'}
            </label>
            <input
              type="text"
              placeholder={
                streamType === 'RTSP'
                  ? 'rtsp://192.168.1.100:554/stream1'
                  : streamType === 'GCS'
                  ? 'gs://jal-dronewatch-videos/S1002353.MP4'
                  : '/home/jeffleinen/jeffdev/dronevideos/videos/S1002353.MP4'
              }
              value={streamUrl}
              onChange={(e) => setStreamUrl(e.target.value)}
            />
          </div>

          <div className="quick-fill-container">
            <button type="button" className="btn-secondary" onClick={handleFillSample}>
              ⚡ Load Campus Sample MP4 (S1002353.MP4)
            </button>
          </div>

          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="btn-primary">
              Start Stream Processing
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
