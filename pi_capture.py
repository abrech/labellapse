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


def _capture_once(
    camera_index: int,
    config: dict,
    output_dir: Path,
    capture_retries: int,
) -> None:
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M%S")
    filename = f"{time_str}.jpg"
    image_path = output_dir / date_str / filename

    # Open the camera per capture — USB webcams on Pi often timeout if left
    # open across long idle intervals between timelapse shots.
    camera = WebcamCapture(camera_index=camera_index)
    try:
        camera.open()
        frame = camera.capture_frame(retries=capture_retries)
        camera.save_jpeg(frame, image_path, quality=config.get("jpeg_quality", 85))
    finally:
        camera.close()

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
    capture_retries = config.get("capture_retries", 3)

    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Pi capture started (interval=%d min, output=%s)",
        interval_minutes,
        output_dir,
    )

    consecutive_failures = 0

    try:
        while True:
            _sleep_until_next_interval(interval_seconds)
            try:
                _capture_once(camera_index, config, output_dir, capture_retries)
                consecutive_failures = 0
            except Exception:
                consecutive_failures += 1
                logger.exception("Capture failed, will retry next interval")
                if consecutive_failures == 5:
                    logger.error(
                        "Five consecutive capture failures — check USB power/cable "
                        "and consider disabling USB autosuspend for the webcam"
                    )

    except KeyboardInterrupt:
        logger.info("Pi capture stopped")

    return 0


if __name__ == "__main__":
    sys.exit(main())
