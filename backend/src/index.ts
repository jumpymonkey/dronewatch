import express from 'express';
import http from 'http';
import path from 'path';
import cors from 'cors';
import { config } from './config/index.js';
import { router } from './api/routes.js';
import { WebSocketPushGateway } from './websocket/pushGateway.js';

const app = express();
const server = http.createServer(app);

// Middleware
app.use(cors());
app.use(express.json());

// API v1 Router
app.use('/api/v1', router);

// Serve Static Frontend Assets in Production
const publicPath = path.join(__dirname, '../public');
app.use(express.static(publicPath));

app.get('*', (req, res, next) => {
  if (req.path.startsWith('/api') || req.path.startsWith('/socket.io')) {
    return next();
  }
  res.sendFile(path.join(publicPath, 'index.html'), (err) => {
    if (err) {
      res.status(200).send('DroneWatch Platform API Server is Running.');
    }
  });
});

// Initialize Socket.io Push Gateway
new WebSocketPushGateway(server);

// Start HTTP Server
server.listen(config.port, () => {
  console.log(`==================================================`);
  console.log(`  DroneWatch GCP Backend Service Running`);
  console.log(`  Port:        ${config.port}`);
  console.log(`  Environment: ${config.appEnv}`);
  console.log(`  Pub/Sub:     ${config.gcp.pubsubTopicAlerts || 'Local Event Bus'}`);
  console.log(`  AlloyDB Host: ${config.db.host}:${config.db.port}`);
  console.log(`==================================================`);
});
