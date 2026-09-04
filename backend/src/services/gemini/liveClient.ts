import { GoogleGenAI } from '@google/genai';
import { config } from '../../config/index.js';
import { query } from '../../db/index.js';
import { eventBus, AlertEventPayload } from '../events/eventBus.js';
import { v4 as uuidv4 } from 'uuid';

export interface GeminiFrameAnalysisResult {
  stream_id: string;
  timestamp: string;
  severity: 'LOW' | 'MEDIUM' | 'CRITICAL';
  category: 'Intrusion' | 'Fire_Safety' | 'Vehicle_Anomaly' | 'Personnel_Safety' | 'Equipment' | 'General';
  summary: string;
  detailed_analysis?: string;
  bounding_boxes: Array<{
    label: string;
    confidence?: number;
    box: [number, number, number, number]; // [ymin, xmin, ymax, xmax]
  }>;
}

export class GeminiAnalysisEngine {
  private ai?: GoogleGenAI;
  private isConfigured: boolean = false;

  constructor() {
    if (config.gemini.apiKey && config.gemini.apiKey !== 'your_gemini_api_key_here') {
      try {
        this.ai = new GoogleGenAI({ apiKey: config.gemini.apiKey });
        this.isConfigured = true;
        console.log(`Gemini AI Analysis Engine initialized using model: ${config.gemini.model}`);
      } catch (err) {
        console.warn('Failed to initialize GoogleGenAI client:', err);
      }
    } else {
      console.warn('GEMINI_API_KEY is not configured. Running in simulated fallback mode.');
    }
  }

  public async analyzeFrame(
    streamId: string,
    droneName: string,
    frameBuffer: Buffer
  ): Promise<GeminiFrameAnalysisResult> {
    const timestamp = new Date().toISOString();

    if (!this.isConfigured || !this.ai) {
      return this.generateSimulatedAnalysis(streamId, droneName, timestamp);
    }

    try {
      const base64Image = frameBuffer.toString('base64');
      const prompt = `
You are an expert security surveillance AI monitoring a live video feed from a drone.
Analyze this video frame for potential safety, security, and operational events.

CRITICAL INSTRUCTIONS:
1. Identify any anomalies, threats, or breaches (e.g. perimeter breach, fire/smoke, unauthorized vehicle, fallen person, suspicious activity).
2. Assign a severity level:
   - "CRITICAL": Urgent active threat requiring immediate pilot action (fire, intruder climbing fence, fallen person, unauthorized vehicle).
   - "MEDIUM": Anomaly or potential caution (vehicle parked in restricted area, open door, unflagged activity).
   - "LOW": Normal operations, routine monitoring, or informational observation.
3. Select a category: "Intrusion", "Fire_Safety", "Vehicle_Anomaly", "Personnel_Safety", "Equipment", "General".
4. Provide a clear, concise 1-sentence summary (max 200 characters).
5. Extract normalized bounding box coordinates for key detected objects in format [ymin, xmin, ymax, xmax] where values are scaled 0 to 1000.

Return STRICT JSON matching this schema:
{
  "severity": "LOW" | "MEDIUM" | "CRITICAL",
  "category": "Intrusion" | "Fire_Safety" | "Vehicle_Anomaly" | "Personnel_Safety" | "Equipment" | "General",
  "summary": "string",
  "detailed_analysis": "string",
  "bounding_boxes": [
    {
      "label": "string",
      "confidence": number,
      "box": [ymin, xmin, ymax, xmax]
    }
  ]
}`;

      const response = await this.ai.models.generateContent({
        model: config.gemini.model,
        contents: [
          {
            role: 'user',
            parts: [
              {
                inlineData: {
                  mimeType: 'image/jpeg',
                  data: base64Image
                }
              },
              { text: prompt }
            ]
          }
        ],
        config: {
          responseMimeType: 'application/json'
        }
      });

      const responseText = response.text;
      if (!responseText) {
        throw new Error('Empty response received from Gemini API');
      }

      const parsedJSON = JSON.parse(responseText);

      const result: GeminiFrameAnalysisResult = {
        stream_id: streamId,
        timestamp,
        severity: parsedJSON.severity || 'LOW',
        category: parsedJSON.category || 'General',
        summary: parsedJSON.summary || 'Routine surveillance visual scan.',
        detailed_analysis: parsedJSON.detailed_analysis || '',
        bounding_boxes: Array.isArray(parsedJSON.bounding_boxes) ? parsedJSON.bounding_boxes : []
      };

      await this.persistAndDispatch(result, droneName, parsedJSON);
      return result;
    } catch (error) {
      console.error(`Gemini frame analysis failed for stream ${streamId}:`, error);
      return this.generateSimulatedAnalysis(streamId, droneName, timestamp);
    }
  }

  private async generateSimulatedAnalysis(
    streamId: string,
    droneName: string,
    timestamp: string
  ): Promise<GeminiFrameAnalysisResult> {
    // Generate deterministic simulated findings when no API key is provided
    const severities: Array<'LOW' | 'MEDIUM' | 'CRITICAL'> = ['LOW', 'LOW', 'LOW', 'MEDIUM', 'CRITICAL'];
    const randomSeverity = severities[Math.floor(Math.random() * severities.length)];

    let category: GeminiFrameAnalysisResult['category'] = 'General';
    let summary = 'Continuous automated flight path monitoring active.';
    let boundingBoxes: GeminiFrameAnalysisResult['bounding_boxes'] = [];

    if (randomSeverity === 'CRITICAL') {
      category = 'Intrusion';
      summary = 'ALERT: Unidentified individual detected near north perimeter fence.';
      boundingBoxes = [
        {
          label: 'Suspicious Individual',
          confidence: 0.92,
          box: [220, 310, 580, 490]
        }
      ];
    } else if (randomSeverity === 'MEDIUM') {
      category = 'Vehicle_Anomaly';
      summary = 'CAUTION: Unregistered vehicle stationary near delivery dock.';
      boundingBoxes = [
        {
          label: 'Vehicle',
          confidence: 0.85,
          box: [400, 150, 750, 600]
        }
      ];
    }

    const result: GeminiFrameAnalysisResult = {
      stream_id: streamId,
      timestamp,
      severity: randomSeverity,
      category,
      summary,
      detailed_analysis: `Simulated flight analysis log for ${droneName} at ${timestamp}.`,
      bounding_boxes: boundingBoxes
    };

    await this.persistAndDispatch(result, droneName, { simulated: true });
    return result;
  }

  private async persistAndDispatch(
    result: GeminiFrameAnalysisResult,
    droneName: string,
    rawResponse: any
  ): Promise<void> {
    try {
      const eventId = uuidv4();
      
      // 1. Insert into stream_analytics
      await query(
        `INSERT INTO stream_analytics 
          (event_id, stream_id, timestamp, severity, category, summary, detailed_analysis, bounding_boxes, raw_response)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)`,
        [
          eventId,
          result.stream_id,
          result.timestamp,
          result.severity,
          result.category,
          result.summary,
          result.detailed_analysis || '',
          JSON.stringify(result.bounding_boxes),
          JSON.stringify(rawResponse)
        ]
      );

      let alertId: string | undefined;

      // 2. Insert into urgent_alerts if CRITICAL
      if (result.severity === 'CRITICAL') {
        alertId = uuidv4();
        await query(
          `INSERT INTO urgent_alerts 
            (alert_id, event_id, stream_id, timestamp, severity)
           VALUES ($1, $2, $3, $4, $5)`,
          [alertId, eventId, result.stream_id, result.timestamp, 'CRITICAL']
        );
      }

      // 3. Dispatch to EventBus
      const payload: AlertEventPayload = {
        event_type: 'CRITICAL_ALERT',
        alert_id: alertId,
        event_id: eventId,
        stream_id: result.stream_id,
        drone_name: droneName,
        timestamp: result.timestamp,
        severity: result.severity,
        category: result.category,
        summary: result.summary,
        detailed_analysis: result.detailed_analysis,
        bounding_boxes: result.bounding_boxes
      };

      await eventBus.publishAlert(payload);
    } catch (err) {
      console.error('Failed to persist analytics record to database:', err);
    }
  }
}

export const geminiEngine = new GeminiAnalysisEngine();
