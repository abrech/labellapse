"""Webcam capture via OpenCV."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


class WebcamCapture:
    def __init__(self, camera_index: int = 0) -> None:
        self._camera_index = camera_index
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> None:
        self._cap = cv2.VideoCapture(self._camera_index, cv2.CAP_DSHOW)
        if not self._cap.isOpened():
            raise RuntimeError(f"Could not open camera at index {self._camera_index}")

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def capture_frame(self) -> np.ndarray:
        if self._cap is None or not self._cap.isOpened():
            raise RuntimeError("Camera is not open")

        for _ in range(5):
            self._cap.grab()
        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise RuntimeError("Failed to read frame from camera")
        return frame

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
