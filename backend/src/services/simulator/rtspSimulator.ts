import path from 'path';
import fs from 'fs';
import { Storage } from '@google-cloud/storage';
import { config } from '../../config/index.js';
import { query } from '../../db/index.js';
import { streamManager } from '../rtsp/streamManager.js';

export interface SimulationLaunchParams {
  drone_name: string;
  source_file: string; // e.g. "DJI_0104.MP4"
}

class RtspSimulatorService {
  private videosDir: string;
  private tempDir: string;
  private storage: Storage;

  constructor() {
    this.videosDir = path.resolve(process.cwd(), '../videos');
    if (!fs.existsSync(this.videosDir)) {
      this.videosDir = path.resolve(process.cwd(), 'videos');
    }

    this.tempDir = path.resolve(process.cwd(), 'temp_videos');
    if (!fs.existsSync(this.tempDir)) {
      fs.mkdirSync(this.tempDir, { recursive: true });
    }

    this.storage = new Storage();
  }

  public async getAvailableVideos(): Promise<string[]> {
    const videoFiles = new Set<string>();

    // 1. Try listing from GCS bucket videos/ folder
    try {
      const bucketName = config.gcp.gcsBucketName;
      const bucket = this.storage.bucket(bucketName);
      const [files] = await bucket.getFiles({ prefix: 'videos/' });

      for (const file of files) {
        const basename = path.basename(file.name);
        if (basename && basename.toUpperCase().endsWith('.MP4')) {
          videoFiles.add(basename);
        }
      }
    } catch (err: any) {
      console.warn('Notice: Could not list GCS simulation videos:', err.message);
    }

    // 2. Also check local disk videos/ directory
    if (fs.existsSync(this.videosDir)) {
      const localFiles = fs.readdirSync(this.videosDir).filter((f) => f.toUpperCase().endsWith('.MP4'));
      localFiles.forEach((f) => videoFiles.add(f));
    }

    return Array.from(videoFiles).sort();
  }

  public async launchSimulation(params: SimulationLaunchParams): Promise<{
    stream_id: string;
    rtsp_url: string;
    drone_name: string;
    source_file: string;
  }> {
    // 1. Locate video file locally or download from GCS
    let videoPath = path.join(this.videosDir, params.source_file);

    if (!fs.existsSync(videoPath)) {
      videoPath = path.join(this.tempDir, params.source_file);

      if (!fs.existsSync(videoPath)) {
        console.log(`Downloading ${params.source_file} from GCS bucket ${config.gcp.gcsBucketName}...`);
        const bucket = this.storage.bucket(config.gcp.gcsBucketName);
        const gcsFile = bucket.file(`videos/${params.source_file}`);

        const [exists] = await gcsFile.exists();
        if (!exists) {
          throw new Error(`Simulation MP4 video not found in GCS or local disk: ${params.source_file}`);
        }

        await gcsFile.download({ destination: videoPath });
        console.log(`Successfully downloaded ${params.source_file} to ${videoPath}`);
      }
    }

    const pathKey = params.source_file.toLowerCase().replace(/[^a-z0-9]/g, '_');
    const simulatedRtspUrl = `rtsp://${config.rtsp.host}:${config.rtsp.port}/sim/${pathKey}`;

    // 2. Insert or update stream record in AlloyDB
    const dbRes = await query(
      `INSERT INTO drone_streams (drone_name, rtsp_url, status, is_simulation, source_file)
       VALUES ($1, $2, 'ACTIVE', true, $3)
       ON CONFLICT (rtsp_url) DO UPDATE
       SET drone_name = EXCLUDED.drone_name, status = 'ACTIVE', updated_at = CURRENT_TIMESTAMP
       RETURNING stream_id`,
      [params.drone_name, simulatedRtspUrl, params.source_file]
    );

    const streamId = dbRes.rows[0].stream_id;

    // 3. Register simulation stream with StreamManager to start HLS transcoding & frame analysis directly from the MP4 file
    await streamManager.startStream(streamId, params.drone_name, simulatedRtspUrl, {
      isSimulation: true,
      sourcePath: videoPath
    });

    return {
      stream_id: streamId,
      rtsp_url: simulatedRtspUrl,
      drone_name: params.drone_name,
      source_file: params.source_file
    };
  }
}

export const rtspSimulator = new RtspSimulatorService();
