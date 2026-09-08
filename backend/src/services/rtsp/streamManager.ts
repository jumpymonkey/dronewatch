import ffmpeg from 'fluent-ffmpeg';
import path from 'path';
import fs from 'fs';
import { geminiEngine } from '../gemini/liveClient.js';
import { query } from '../../db/index.js';

export interface ActiveStreamState {
  streamId: string;
  droneName: string;
  rtspUrl: string;
  ffmpegProcess?: ffmpeg.FfmpegCommand;
  ffmpegHlsProcess?: ffmpeg.FfmpegCommand;
  status: 'ACTIVE' | 'INACTIVE' | 'RECONNECTING' | 'ERROR';
  lastFrameTime?: number;
  intervalTimer?: NodeJS.Timeout;
}

class StreamManagerService {
  private activeStreams: Map<string, ActiveStreamState> = new Map();
  private framesDir: string;
  private hlsDir: string;

  constructor() {
    this.framesDir = path.resolve(process.cwd(), 'temp_frames');
    this.hlsDir = path.resolve(process.cwd(), 'temp_hls');
    
    if (!fs.existsSync(this.framesDir)) {
      fs.mkdirSync(this.framesDir, { recursive: true });
    }
    if (!fs.existsSync(this.hlsDir)) {
      fs.mkdirSync(this.hlsDir, { recursive: true });
    }
  }

  public async startStream(streamId: string, droneName: string, rtspUrl: string): Promise<void> {
    if (this.activeStreams.has(streamId)) {
      console.log(`Stream ${streamId} (${droneName}) is already active.`);
      return;
    }

    const state: ActiveStreamState = {
      streamId,
      droneName,
      rtspUrl,
      status: 'ACTIVE'
    };

    this.activeStreams.set(streamId, state);

    // Update database status
    await query('UPDATE drone_streams SET status = $1, updated_at = CURRENT_TIMESTAMP WHERE stream_id = $2', [
      'ACTIVE',
      streamId
    ]);

    console.log(`Starting RTSP stream processing for [${droneName}] -> ${rtspUrl}`);

    // Create stream-specific HLS output directory
    const streamHlsDir = path.join(this.hlsDir, streamId);
    if (!fs.existsSync(streamHlsDir)) {
      fs.mkdirSync(streamHlsDir, { recursive: true });
    }

    // Launch continuous FFmpeg HLS transcoding
    const playlistPath = path.join(streamHlsDir, 'index.m3u8');
    const hlsProcess = ffmpeg(rtspUrl)
      .inputOptions(['-rtsp_transport tcp', '-analyzeduration 2000000', '-probesize 2000000'])
      .outputOptions([
        '-c:v libx264',
        '-preset ultrafast',
        '-tune zerolatency',
        '-c:a aac',
        '-f hls',
        '-hls_time 2',
        '-hls_list_size 5',
        '-hls_flags delete_segments'
      ])
      .output(playlistPath)
      .on('start', (cmd) => {
        console.log(`HLS FFmpeg started for [${droneName}]: ${cmd}`);
      })
      .on('error', (err) => {
        console.error(`HLS FFmpeg transcoding error for [${droneName}]:`, err.message);
      })
      .on('end', () => {
        console.log(`HLS FFmpeg process ended for [${droneName}]`);
      });

    hlsProcess.run();
    state.ffmpegHlsProcess = hlsProcess;

    // Set periodic frame extraction timer (1 frame every 4 seconds for Gemini AI background analysis)
    state.intervalTimer = setInterval(() => {
      this.extractAndAnalyzeFrame(state);
    }, 4000);
  }

  public async stopStream(streamId: string): Promise<void> {
    const state = this.activeStreams.get(streamId);
    if (!state) return;

    if (state.intervalTimer) {
      clearInterval(state.intervalTimer);
    }

    if (state.ffmpegHlsProcess) {
      try {
        state.ffmpegHlsProcess.kill('SIGKILL');
      } catch (e) {
        // Ignore kill errors
      }
    }

    if (state.ffmpegProcess) {
      try {
        state.ffmpegProcess.kill('SIGKILL');
      } catch (e) {
        // Ignore kill errors
      }
    }

    // Clean up HLS stream directory
    const streamHlsDir = path.join(this.hlsDir, streamId);
    if (fs.existsSync(streamHlsDir)) {
      try {
        fs.rmSync(streamHlsDir, { recursive: true, force: true });
      } catch (e) {
        console.warn(`Failed to cleanup HLS directory for ${streamId}:`, e);
      }
    }

    this.activeStreams.delete(streamId);

    await query('UPDATE drone_streams SET status = $1, updated_at = CURRENT_TIMESTAMP WHERE stream_id = $2', [
      'INACTIVE',
      streamId
    ]);

    console.log(`Stopped RTSP stream processing for [${state.droneName}]`);
  }

  private extractAndAnalyzeFrame(state: ActiveStreamState): void {
    const framePath = path.join(this.framesDir, `frame_${state.streamId}.jpg`);

    ffmpeg(state.rtspUrl)
      .inputOptions(['-rtsp_transport tcp', '-analyzeduration 1000000', '-probesize 1000000'])
      .outputOptions(['-vframes 1', '-q:v 2'])
      .output(framePath)
      .on('end', async () => {
        try {
          if (fs.existsSync(framePath)) {
            const frameBuffer = fs.readFileSync(framePath);
            await geminiEngine.analyzeFrame(state.streamId, state.droneName, frameBuffer);
            // Clean up temporary frame file
            fs.unlinkSync(framePath);
          }
        } catch (err) {
          console.error(`Frame read/analysis error for ${state.droneName}:`, err);
        }
      })
      .on('error', (err) => {
        // Soft error fallback if stream is starting up or packet dropped
        if (process.env.DEBUG === 'true') {
          console.warn(`Frame extraction warning for ${state.droneName}:`, err.message);
        }
      })
      .run();
  }

  public getActiveStreams(): ActiveStreamState[] {
    return Array.from(this.activeStreams.values());
  }
}

export const streamManager = new StreamManagerService();
