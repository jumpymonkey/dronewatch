import pg from 'pg';
import { config } from '../config/index.js';

const { Pool } = pg;

export const pool = new Pool({
  host: config.db.host,
  port: config.db.port,
  database: config.db.name,
  user: config.db.user,
  password: config.db.password,
  ssl: config.db.ssl ? { rejectUnauthorized: false } : false
});

pool.on('error', (err) => {
  console.error('Unexpected error on idle PostgreSQL client:', err);
});

export async function query(text: string, params?: any[]) {
  const start = Date.now();
  const res = await pool.query(text, params);
  const duration = Date.now() - start;
  if (process.env.DEBUG === 'true') {
    console.log('Executed query', { text, duration, rows: res.rowCount });
  }
  return res;
}

export async function initDatabaseSchema() {
  try {
    const tableCheck = await query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'drone_streams'
      );
    `);

    if (!tableCheck.rows[0].exists) {
      console.log('Initializing DroneWatch database schema...');
      await query(`CREATE EXTENSION IF NOT EXISTS "uuid-ossp";`);
      await query(`CREATE EXTENSION IF NOT EXISTS vector;`);
      await query(`
        CREATE TABLE IF NOT EXISTS drone_streams (
            stream_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            drone_name VARCHAR(100) NOT NULL,
            rtsp_url VARCHAR(500) NOT NULL UNIQUE,
            status VARCHAR(20) NOT NULL DEFAULT 'INACTIVE' 
                CHECK (status IN ('ACTIVE', 'INACTIVE', 'RECONNECTING', 'ERROR')),
            is_simulation BOOLEAN NOT NULL DEFAULT FALSE,
            source_file VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
      `);
      await query(`
        CREATE TABLE IF NOT EXISTS stream_analytics (
            event_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            stream_id UUID NOT NULL REFERENCES drone_streams(stream_id) ON DELETE CASCADE,
            timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
            severity VARCHAR(20) NOT NULL CHECK (severity IN ('LOW', 'MEDIUM', 'CRITICAL')),
            category VARCHAR(50) NOT NULL,
            summary TEXT NOT NULL,
            detailed_analysis TEXT,
            bounding_boxes JSONB DEFAULT '[]'::jsonb,
            raw_response JSONB NOT NULL,
            embedding vector(768),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
      `);
      await query(`
        CREATE TABLE IF NOT EXISTS urgent_alerts (
            alert_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            event_id UUID NOT NULL REFERENCES stream_analytics(event_id) ON DELETE CASCADE,
            stream_id UUID NOT NULL REFERENCES drone_streams(stream_id) ON DELETE CASCADE,
            timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
            severity VARCHAR(20) NOT NULL DEFAULT 'CRITICAL',
            is_acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
            acknowledged_by VARCHAR(100),
            acknowledged_at TIMESTAMP WITH TIME ZONE,
            notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
      `);
      console.log('DroneWatch database schema initialized successfully.');
    }
  } catch (error) {
    console.error('Failed to initialize database schema:', error);
  }
}

export async function checkDatabaseConnection(): Promise<boolean> {
  try {
    const res = await query('SELECT NOW()');
    console.log('Database connected successfully at:', res.rows[0].now);
    await initDatabaseSchema();
    return true;
  } catch (error) {
    console.error('Failed to connect to database:', error);
    return false;
  }
}
