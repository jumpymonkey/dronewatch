import { useEffect, useState } from 'react';
import { io, Socket } from 'socket.io-client';
import { AnalyticsEvent } from '../types';

export function useWebSocket(onAlertReceived?: (event: AnalyticsEvent) => void) {
  const [isConnected, setIsConnected] = useState(false);
  const [socket, setSocket] = useState<Socket | null>(null);

  useEffect(() => {
    const socketInstance = io(window.location.origin, {
      transports: ['websocket', 'polling']
    });

    socketInstance.on('connect', () => {
      console.log('Connected to DroneWatch WebSocket Push Gateway');
      setIsConnected(true);
    });

    socketInstance.on('disconnect', () => {
      console.log('Disconnected from WebSocket Push Gateway');
      setIsConnected(false);
    });

    socketInstance.on('alert', (data: AnalyticsEvent) => {
      console.log('Real-time alert received via WebSocket:', data);
      if (onAlertReceived) {
        onAlertReceived(data);
      }
    });

    setSocket(socketInstance);

    return () => {
      socketInstance.disconnect();
    };
  }, []);

  return { isConnected, socket };
}
