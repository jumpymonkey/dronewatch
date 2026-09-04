import express from 'express';
import http from 'http';
import path from 'path';
import cors from 'cors';
import { config } from './config';
import routes from './api/routes';
import { initWebSocketGateway } from './websocket/pushGateway';

const app = express();
const server = http.createServer(app);

// Middleware
app.use(cors());
app.use(express.json());

// API v1 Router
app.use('/api/v1', routes);

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
initWebSocketGateway(server);

// Start HTTP Server
server.listen(config.port, () => {
  console.log(`==================================================`);
  console.log(`  DroneWatch GCP Backend Service Running`);
  console.log(`  Port:        ${config.port}`);
  console.log(`  Environment: ${config.nodeEnv}`);
  console.log(`  Pub/Sub:     ${config.gcpPubSubTopic || 'Local Event Bus'}`);
  console.log(`  AlloyDB Host: ${config.dbHost}:${config.dbPort}`);
  console.log(`==================================================`);
});
