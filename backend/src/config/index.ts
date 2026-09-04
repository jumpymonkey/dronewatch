import dotenv from 'dotenv';
import path from 'path';

dotenv.config({ path: path.resolve(process.cwd(), '../.env') });
dotenv.config();

export const config = {
  port: parseInt(process.env.PORT || '4000', 10),
  appEnv: process.env.APP_ENV || 'local',
  db: {
    host: process.env.DB_HOST || 'localhost',
    port: parseInt(process.env.DB_PORT || '5432', 10),
    name: process.env.DB_NAME || 'dronewatch',
    user: process.env.DB_USER || 'dronewatch',
    password: process.env.DB_PASSWORD || 'dronewatch_secret',
    ssl: process.env.DB_SSL === 'true'
  },
  rtsp: {
    host: process.env.RTSP_HOST || 'localhost',
    port: parseInt(process.env.RTSP_PORT || '8554', 10),
    mediaMtxApi: process.env.MEDIAMTX_API || 'http://localhost:8554/v3'
  },
  gemini: {
    apiKey: process.env.GEMINI_API_KEY || '',
    model: process.env.GEMINI_MODEL || 'gemini-2.5-flash'
  },
  gcp: {
    projectId: process.env.GCP_PROJECT_ID || 'dronewatch-project',
    region: process.env.GCP_REGION || 'us-central1',
    pubsubTopicAlerts: process.env.PUBSUB_TOPIC_ALERTS || 'dronewatch-urgent-alerts',
    gcsBucketMedia: process.env.GCS_BUCKET_MEDIA || 'dronewatch-media-archive',
    gcsBucketSimulation: process.env.GCS_BUCKET_SIMULATION || 'dronewatch-simulation-videos'
  }
};
