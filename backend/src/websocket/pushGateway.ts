import { Server as HttpServer } from 'http';
import { Server, Socket } from 'socket.io';
import { eventBus, AlertEventPayload } from '../services/events/eventBus.js';

export class WebSocketPushGateway {
  private io: Server;

  constructor(server: HttpServer) {
    this.io = new Server(server, {
      cors: {
        origin: '*',
        methods: ['GET', 'POST']
      }
    });

    this.initSocketHandlers();
    this.subscribeToEventBus();
  }

  private initSocketHandlers(): void {
    this.io.on('connection', (socket: Socket) => {
      console.log(`Pilot UI WebSocket client connected: ${socket.id}`);

      socket.on('disconnect', () => {
        console.log(`Pilot UI WebSocket client disconnected: ${socket.id}`);
      });
    });
  }

  private subscribeToEventBus(): void {
    eventBus.onAlert((payload: AlertEventPayload) => {
      console.log(`Broadcasting [${payload.severity}] alert to connected WebSocket clients for stream: ${payload.stream_id}`);
      this.io.emit('alert', payload);
    });
  }
}
