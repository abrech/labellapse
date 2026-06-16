"""Webcam capture via OpenCV."""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class WebcamCapture:
    def __init__(self, camera_index: int = 0) -> None:
        self._camera_index = camera_index
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> None:
        if sys.platform == "win32":
            self._cap = cv2.VideoCapture(self._camera_index, cv2.CAP_DSHOW)
        else:
            self._cap = cv2.VideoCapture(self._camera_index, cv2.CAP_V4L2)
        if not self._cap.isOpened():
            raise RuntimeError(f"Could not open camera at index {self._camera_index}")
        self._configure_capture()

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def _configure_capture(self) -> None:
        if self._cap is None or sys.platform == "win32":
            return
        # Keep one frame in the buffer; helps avoid stale reads on USB webcams.
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def capture_frame(self, retries: int = 2) -> np.ndarray:
        if self._cap is None or not self._cap.isOpened():
            raise RuntimeError("Camera is not open")

        last_error: Exception | None = None
        attempts = max(1, retries)

        for attempt in range(attempts):
            try:
                frame = self._read_frame()
                if frame is not None:
                    return frame
                last_error = RuntimeError("Failed to read frame from camera")
            except RuntimeError as exc:
                last_error = exc

            if attempt + 1 < attempts:
                logger.warning(
                    "Camera read failed (attempt %d/%d), retrying",
                    attempt + 1,
                    attempts,
                )
                time.sleep(0.5)
                self._discard_stale_frames()

        raise last_error or RuntimeError("Failed to read frame from camera")

    def _read_frame(self) -> np.ndarray | None:
        if self._cap is None:
            return None

        if sys.platform == "win32":
            for _ in range(5):
                self._cap.grab()
        else:
            # Warm-up read; USB cameras on Pi often need a moment after open.
            self._cap.read()

        ok, frame = self._cap.read()
        if not ok or frame is None:
            return None
        return frame

    def _discard_stale_frames(self) -> None:
        if self._cap is None:
            return
        for _ in range(3):
            self._cap.grab()

    def save_jpeg(self, frame: np.ndarray, path: Path, quality: int = 85) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        ok = cv2.imwrite(
            str(path),
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), quality],
        )
        if not ok:
            raise RuntimeError(f"Failed to write image to {path}")

    def __enter__(self) -> WebcamCapture:
        self.open()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
