export interface DroneStream {
  stream_id: string;
  drone_name: string;
  rtsp_url: string;
  status: 'ACTIVE' | 'INACTIVE' | 'RECONNECTING' | 'ERROR';
  is_simulation: boolean;
  source_file?: string;
  created_at: string;
  updated_at?: string;
}

export interface BoundingBox {
  label: string;
  confidence?: number;
  box: [number, number, number, number]; // [ymin, xmin, ymax, xmax] normalized 0-1000
}

export interface AnalyticsEvent {
  event_id: string;
  stream_id: string;
  drone_name?: string;
  timestamp: string;
  severity: 'LOW' | 'MEDIUM' | 'CRITICAL';
  category: string;
  summary: string;
  detailed_analysis?: string;
  bounding_boxes: BoundingBox[];
  created_at?: string;
}

export interface UrgentAlert {
  alert_id: string;
  event_id: string;
  stream_id: string;
  drone_name?: string;
  timestamp: string;
  severity: 'CRITICAL' | 'MEDIUM';
  category?: string;
  summary?: string;
  bounding_boxes?: BoundingBox[];
}
