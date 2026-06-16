"""Raspberry Pi webcam capture: periodic photos saved by date folder."""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

from capture import WebcamCapture

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _sleep_until_next_interval(interval_seconds: float) -> None:
    now = time.time()
    elapsed = now % interval_seconds
    wait = interval_seconds - elapsed if elapsed > 0 else interval_seconds
    time.sleep(wait)


def _capture_once(camera: WebcamCapture, config: dict, output_dir: Path) -> None:
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M%S")
    filename = f"{time_str}.jpg"
    image_path = output_dir / date_str / filename

    frame = camera.capture_frame()
    camera.save_jpeg(frame, image_path, quality=config.get("jpeg_quality", 85))
    logger.info("Captured %s/%s", date_str, filename)


def main() -> int:
    config_path = BASE_DIR / "config.pi.yaml"
    if not config_path.exists():
        logger.error("Missing config file: %s", config_path)
        return 1

    config = load_config(config_path)
    interval_minutes = config.get("interval_minutes", 15)
    interval_seconds = interval_minutes * 60
    output_dir = BASE_DIR / config.get("output_dir", "./images")
    camera_index = config.get("camera_index", 0)

    output_dir.mkdir(parents=True, exist_ok=True)

    camera = WebcamCapture(camera_index=camera_index)
    try:
        camera.open()
        logger.info(
            "Pi capture started (interval=%d min, output=%s)",
            interval_minutes,
            output_dir,
        )

        while True:
            _sleep_until_next_interval(interval_seconds)
            try:
                _capture_once(camera, config, output_dir)
            except Exception:
                logger.exception("Capture failed, will retry next interval")

    except KeyboardInterrupt:
        logger.info("Pi capture stopped")
    finally:
        camera.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
