import ffmpeg from 'fluent-ffmpeg';
import path from 'path';
import fs from 'fs';
import { config } from '../../config/index.js';
import { query } from '../../db/index.js';
import { streamManager } from '../rtsp/streamManager.js';

export interface SimulationLaunchParams {
  drone_name: string;
  source_file: string; // e.g. "DJI_0104.MP4"
}

class RtspSimulatorService {
  private activeSimulations: Map<string, ffmpeg.FfmpegCommand> = new Map();
  private videosDir: string;

  constructor() {
    this.videosDir = path.resolve(process.cwd(), '../videos');
    if (!fs.existsSync(this.videosDir)) {
      this.videosDir = path.resolve(process.cwd(), 'videos');
    }
  }

  public async launchSimulation(params: SimulationLaunchParams): Promise<{
    stream_id: string;
    rtsp_url: string;
    drone_name: string;
    source_file: string;
  }> {
    const videoPath = path.join(this.videosDir, params.source_file);

    if (!fs.existsSync(videoPath)) {
      throw new Error(`Local MP4 test video not found: ${videoPath}`);
    }

    const pathKey = params.source_file.toLowerCase().replace(/[^a-z0-9]/g, '_');
    const rtspUrl = `rtsp://${config.rtsp.host}:${config.rtsp.port}/sim/${pathKey}`;

    // 1. Insert or update stream in database
    const dbRes = await query(
      `INSERT INTO drone_streams (drone_name, rtsp_url, status, is_simulation, source_file)
       VALUES ($1, $2, 'ACTIVE', true, $3)
       ON CONFLICT (rtsp_url) DO UPDATE
       SET drone_name = EXCLUDED.drone_name, status = 'ACTIVE', updated_at = CURRENT_TIMESTAMP
       RETURNING stream_id`,
      [params.drone_name, rtspUrl, params.source_file]
    );

    const streamId = dbRes.rows[0].stream_id;

    // 2. Launch FFmpeg looping process to push stream to MediaMTX
    if (!this.activeSimulations.has(streamId)) {
      console.log(`Piping ${params.source_file} to MediaMTX RTSP endpoint: ${rtspUrl}`);

      const proc = ffmpeg(videoPath)
        .inputOptions(['-stream_loop -1', '-re'])
        .outputOptions(['-c:v libx264', '-preset ultrafast', '-tune zerolatency', '-f rtsp'])
        .output(rtspUrl)
        .on('start', (cmd) => {
          console.log(`FFmpeg RTSP Simulation process started for ${params.drone_name}`);
        })
        .on('error', (err) => {
          console.warn(`FFmpeg RTSP Simulation notice for ${params.drone_name}:`, err.message);
        });

      proc.run();
      this.activeSimulations.set(streamId, proc);
    }

    // 3. Register stream with StreamManager for frame analysis
    await streamManager.startStream(streamId, params.drone_name, rtspUrl);

    return {
      stream_id: streamId,
      rtsp_url: rtspUrl,
      drone_name: params.drone_name,
      source_file: params.source_file
    };
  }

  public getAvailableVideos(): string[] {
    if (!fs.existsSync(this.videosDir)) return [];
    return fs.readdirSync(this.videosDir).filter((f) => f.toUpperCase().endsWith('.MP4'));
  }
}

export const rtspSimulator = new RtspSimulatorService();
