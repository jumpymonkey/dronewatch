"""OpenCV-based motion pre-filtering service to eliminate static frames before LLM evaluation."""

import logging
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class MotionFilter:
    """Lightweight frame differencing filter to detect visual motion in drone feeds."""

    def __init__(
        self,
        sensitivity_threshold: float = 15.0,
        min_motion_area: int = 500,
        blur_kernel_size: int = 21,
    ) -> None:
        """Initialize motion filter with threshold parameters.

        Args:
            sensitivity_threshold: Pixel delta intensity threshold.
            min_motion_area: Minimum area in pixels for a contour to count as motion.
            blur_kernel_size: Gaussian blur kernel size for noise reduction.
        """
        self.sensitivity_threshold: float = sensitivity_threshold
        self.min_motion_area: int = min_motion_area
        self.blur_kernel_size: int = blur_kernel_size
        self._previous_grayscale_frame: np.ndarray[Any, Any] | None = None

    def reset(self) -> None:
        """Reset the reference frame state."""
        self._previous_grayscale_frame = None

    def process_frame(self, frame_bgr: np.ndarray[Any, Any]) -> tuple[bool, float]:
        """Evaluate a BGR video frame for significant motion relative to the previous frame.

        Args:
            frame_bgr: OpenCV image array (BGR format).

        Returns:
            Tuple of (has_motion: bool, motion_score: float).
        """
        gray: np.ndarray[Any, Any] = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        gray_blurred: np.ndarray[Any, Any] = cv2.GaussianBlur(
            gray, (self.blur_kernel_size, self.blur_kernel_size), 0
        )

        if self._previous_grayscale_frame is None:
            self._previous_grayscale_frame = gray_blurred
            return True, 1.0

        frame_delta: np.ndarray[Any, Any] = cv2.absdiff(
            self._previous_grayscale_frame, gray_blurred
        )
        self._previous_grayscale_frame = gray_blurred

        thresh: np.ndarray[Any, Any] = cv2.threshold(
            frame_delta, int(self.sensitivity_threshold), 255, cv2.THRESH_BINARY
        )[1]

        thresh = cv2.dilate(thresh, None, iterations=2)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        max_contour_area: float = 0.0
        total_motion_area: float = 0.0

        for contour in contours:
            area: float = float(cv2.contourArea(contour))
            if area >= self.min_motion_area:
                total_motion_area += area
                if area > max_contour_area:
                    max_contour_area = area

        has_motion: bool = total_motion_area >= self.min_motion_area
        frame_pixels: int = frame_bgr.shape[0] * frame_bgr.shape[1]
        motion_score: float = float(min(1.0, total_motion_area / frame_pixels))

        logger.debug(
            "Motion filter evaluated frame: has_motion=%s, motion_score=%.4f",
            has_motion,
            motion_score,
        )
        return has_motion, motion_score

    def process_bytes(self, image_bytes: bytes) -> tuple[bool, float]:
        """Convenience method to process raw image byte buffer (e.g. JPEG frame).

        Args:
            image_bytes: Byte array of encoded JPEG or PNG image.

        Returns:
            Tuple of (has_motion: bool, motion_score: float).
        """
        nparr: np.ndarray[Any, Any] = np.frombuffer(image_bytes, np.uint8)
        frame: np.ndarray[Any, Any] | None = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
            logger.warning("Failed to decode image bytes in MotionFilter.")
            return True, 0.0
        return self.process_frame(frame)
