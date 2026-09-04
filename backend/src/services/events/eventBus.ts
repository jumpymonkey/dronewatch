import { EventEmitter } from 'events';
import { PubSub } from '@google-cloud/pubsub';
import { config } from '../../config/index.js';

export interface AlertEventPayload {
  event_type: 'CRITICAL_ALERT' | 'STREAM_STATUS_CHANGE';
  alert_id?: string;
  event_id?: string;
  stream_id: string;
  drone_name?: string;
  timestamp: string;
  severity: 'LOW' | 'MEDIUM' | 'CRITICAL';
  category: string;
  summary: string;
  detailed_analysis?: string;
  bounding_boxes?: Array<{
    label: string;
    confidence?: number;
    box: [number, number, number, number];
  }>;
}

class EventBusService {
  private localEmitter: EventEmitter;
  private pubsubClient?: PubSub;
  private isGcpMode: boolean;

  constructor() {
    this.localEmitter = new EventEmitter();
    this.isGcpMode = config.appEnv === 'gcp';

    if (this.isGcpMode) {
      try {
        this.pubsubClient = new PubSub({ projectId: config.gcp.projectId });
        console.log('GCP Pub/Sub event bus initialized');
      } catch (err) {
        console.warn('GCP Pub/Sub initialization failed, falling back to local EventEmitter:', err);
        this.isGcpMode = false;
      }
    } else {
      console.log('Local EventEmitter event bus initialized');
    }
  }

  public async publishAlert(payload: AlertEventPayload): Promise<void> {
    // Always emit locally for real-time WebSocket push
    this.localEmitter.emit('alert', payload);

    if (this.isGcpMode && this.pubsubClient) {
      try {
        const topic = this.pubsubClient.topic(config.gcp.pubsubTopicAlerts);
        const dataBuffer = Buffer.from(JSON.stringify(payload));
        await topic.publishMessage({ data: dataBuffer });
        console.log(`Alert published to GCP Pub/Sub topic [${config.gcp.pubsubTopicAlerts}]`);
      } catch (error) {
        console.error('Error publishing to GCP Pub/Sub:', error);
      }
    }
  }

  public onAlert(listener: (payload: AlertEventPayload) => void): void {
    this.localEmitter.on('alert', listener);
  }

  public removeAlertListener(listener: (payload: AlertEventPayload) => void): void {
    this.localEmitter.off('alert', listener);
  }
}

export const eventBus = new EventBusService();
