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

export async function checkDatabaseConnection(): Promise<boolean> {
  try {
    const res = await query('SELECT NOW()');
    console.log('Database connected successfully at:', res.rows[0].now);
    return true;
  } catch (error) {
    console.error('Failed to connect to database:', error);
    return false;
  }
}
