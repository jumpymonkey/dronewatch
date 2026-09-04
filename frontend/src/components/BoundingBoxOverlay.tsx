import React, { useEffect, useRef } from 'react';
import { BoundingBox } from '../types';

interface BoundingBoxOverlayProps {
  boundingBoxes: BoundingBox[];
  severity?: 'LOW' | 'MEDIUM' | 'CRITICAL';
}

export const BoundingBoxOverlay: React.FC<BoundingBoxOverlayProps> = ({
  boundingBoxes,
  severity = 'LOW'
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Clear previous drawings
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (!boundingBoxes || boundingBoxes.length === 0) return;

    const width = canvas.width;
    const height = canvas.height;

    boundingBoxes.forEach((item) => {
      const [ymin, xmin, ymax, xmax] = item.box;

      // Scale 0-1000 normalized coordinates to canvas dimensions
      const x = (xmin / 1000) * width;
      const y = (ymin / 1000) * height;
      const w = ((xmax - xmin) / 1000) * width;
      const h = ((ymax - ymin) / 1000) * height;

      // Determine stroke color based on severity
      let strokeColor = '#38BDF8'; // Cyan default
      let fillColor = 'rgba(56, 189, 248, 0.15)';

      if (severity === 'CRITICAL') {
        strokeColor = '#EF4444'; // Red
        fillColor = 'rgba(239, 68, 68, 0.25)';
      } else if (severity === 'MEDIUM') {
        strokeColor = '#F59E0B'; // Amber
        fillColor = 'rgba(245, 158, 11, 0.2)';
      }

      // Draw box fill
      ctx.fillStyle = fillColor;
      ctx.fillRect(x, y, w, h);

      // Draw box stroke
      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = 2.5;
      ctx.strokeRect(x, y, w, h);

      // Label background
      const labelText = `${item.label} ${item.confidence ? `(${Math.round(item.confidence * 100)}%)` : ''}`;
      ctx.font = 'bold 11px Outfit, sans-serif';
      const textWidth = ctx.measureText(labelText).width;

      ctx.fillStyle = strokeColor;
      ctx.fillRect(x, y > 20 ? y - 20 : y, textWidth + 10, 20);

      // Label text
      ctx.fillStyle = '#FFFFFF';
      ctx.fillText(labelText, x + 5, y > 20 ? y - 6 : y + 14);
    });
  }, [boundingBoxes, severity]);

  return (
    <canvas
      ref={canvasRef}
      width={640}
      height={360}
      className="absolute inset-0 w-full h-full pointer-events-none z-20"
    />
  );
};
