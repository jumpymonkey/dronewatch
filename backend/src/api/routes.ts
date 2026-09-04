import { Router, Request, Response } from 'express';
import { query } from '../db/index.js';
import { rtspSimulator } from '../services/simulator/rtspSimulator.js';
import { streamManager } from '../services/rtsp/streamManager.js';

export const router = Router();

// GET /api/v1/streams - List all drone streams
router.get('/streams', async (req: Request, res: Response) => {
  try {
    const result = await query(
      'SELECT stream_id, drone_name, rtsp_url, status, is_simulation, source_file, created_at, updated_at FROM drone_streams ORDER BY created_at DESC'
    );
    res.json(result.rows);
  } catch (error) {
    console.error('Error fetching streams:', error);
    res.status(500).json({ error: 'Failed to fetch drone streams' });
  }
});

// POST /api/v1/streams - Register a new RTSP drone stream
router.post('/streams', async (req: Request, res: Response) => {
  try {
    const { drone_name, rtsp_url } = req.body;
    if (!drone_name || !rtsp_url) {
      return res.status(400).json({ error: 'drone_name and rtsp_url are required fields.' });
    }

    const result = await query(
      `INSERT INTO drone_streams (drone_name, rtsp_url, status, is_simulation)
       VALUES ($1, $2, 'ACTIVE', false)
       RETURNING stream_id, drone_name, rtsp_url, status, created_at`,
      [drone_name, rtsp_url]
    );

    const newStream = result.rows[0];
    await streamManager.startStream(newStream.stream_id, newStream.drone_name, newStream.rtsp_url);

    res.status(201).json(newStream);
  } catch (error) {
    console.error('Error adding stream:', error);
    res.status(500).json({ error: 'Failed to register RTSP drone stream' });
  }
});

// DELETE /api/v1/streams/:stream_id - Stop and delete a stream
router.delete('/streams/:stream_id', async (req: Request, res: Response) => {
  try {
    const { stream_id } = req.params;
    await streamManager.stopStream(stream_id);
    await query('DELETE FROM drone_streams WHERE stream_id = $1', [stream_id]);
    res.json({ message: 'Stream deleted successfully', stream_id });
  } catch (error) {
    console.error('Error deleting stream:', error);
    res.status(500).json({ error: 'Failed to delete stream' });
  }
});

// GET /api/v1/simulations/videos - List available MP4 test videos
router.get('/simulations/videos', (req: Request, res: Response) => {
  try {
    const videos = rtspSimulator.getAvailableVideos();
    res.json({ videos });
  } catch (error) {
    res.status(500).json({ error: 'Failed to list local simulation test videos' });
  }
});

// POST /api/v1/simulations/launch - Launch an RTSP test simulation stream
router.post('/simulations/launch', async (req: Request, res: Response) => {
  try {
    const { drone_name, source_file } = req.body;
    if (!drone_name || !source_file) {
      return res.status(400).json({ error: 'drone_name and source_file are required fields.' });
    }

    const sim = await rtspSimulator.launchSimulation({ drone_name, source_file });
    res.status(201).json(sim);
  } catch (error: any) {
    console.error('Error launching RTSP simulation:', error);
    res.status(500).json({ error: error.message || 'Failed to launch RTSP simulation' });
  }
});

// GET /api/v1/analytics - Fetch timestamped logs with filters
router.get('/analytics', async (req: Request, res: Response) => {
  try {
    const { stream_id, severity, limit = '50', offset = '0' } = req.query;

    let queryText = `
      SELECT a.event_id, a.stream_id, d.drone_name, a.timestamp, a.severity, 
             a.category, a.summary, a.detailed_analysis, a.bounding_boxes, a.created_at
      FROM stream_analytics a
      JOIN drone_streams d ON a.stream_id = d.stream_id
      WHERE 1=1
    `;

    const params: any[] = [];
    let paramIdx = 1;

    if (stream_id) {
      queryText += ` AND a.stream_id = $${paramIdx++}`;
      params.push(stream_id);
    }

    if (severity) {
      queryText += ` AND a.severity = $${paramIdx++}`;
      params.push(severity);
    }

    queryText += ` ORDER BY a.timestamp DESC LIMIT $${paramIdx++} OFFSET $${paramIdx++}`;
    params.push(parseInt(limit as string, 10), parseInt(offset as string, 10));

    const result = await query(queryText, params);
    res.json(result.rows);
  } catch (error) {
    console.error('Error fetching analytics logs:', error);
    res.status(500).json({ error: 'Failed to fetch analytics logs' });
  }
});

// GET /api/v1/alerts/unacknowledged - Get pending urgent alerts
router.get('/alerts/unacknowledged', async (req: Request, res: Response) => {
  try {
    const result = await query(`
      SELECT u.alert_id, u.event_id, u.stream_id, d.drone_name, u.timestamp, u.severity,
             a.category, a.summary, a.bounding_boxes
      FROM urgent_alerts u
      JOIN drone_streams d ON u.stream_id = d.stream_id
      JOIN stream_analytics a ON u.event_id = a.event_id
      WHERE u.is_acknowledged = false
      ORDER BY u.timestamp DESC
    `);
    res.json(result.rows);
  } catch (error) {
    console.error('Error fetching unacknowledged alerts:', error);
    res.status(500).json({ error: 'Failed to fetch urgent alerts' });
  }
});

// POST /api/v1/alerts/:alert_id/acknowledge - Acknowledge an alert
router.post('/alerts/:alert_id/acknowledge', async (req: Request, res: Response) => {
  try {
    const { alert_id } = req.params;
    const { acknowledged_by, notes } = req.body;

    await query(
      `UPDATE urgent_alerts 
       SET is_acknowledged = true, acknowledged_by = $1, acknowledged_at = CURRENT_TIMESTAMP, notes = $2
       WHERE alert_id = $3`,
      [acknowledged_by || 'Pilot', notes || '', alert_id]
    );

    res.json({ message: 'Alert acknowledged successfully', alert_id });
  } catch (error) {
    console.error('Error acknowledging alert:', error);
    res.status(500).json({ error: 'Failed to acknowledge alert' });
  }
});
