"""Desk activity timelapse: periodic webcam capture with activity labels."""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

from capture import WebcamCapture
from context import get_foreground_context
from labeling import load_rules, resolve_label
from tray import AppController, start_tray, stop_tray

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


def _append_metadata(metadata_path: Path, record: dict) -> None:
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with metadata_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _capture_once(
    camera: WebcamCapture,
    config: dict,
    rules: dict,
    output_dir: Path,
) -> None:
    ctx = get_foreground_context()
    result = resolve_label(ctx, rules, BASE_DIR)

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M%S")
    filename = f"{time_str}_{result.label}.jpg"

    day_dir = output_dir / date_str
    image_path = day_dir / filename
    metadata_path = day_dir / "metadata.jsonl"

    frame = camera.capture_frame()
    camera.save_jpeg(frame, image_path, quality=config.get("jpeg_quality", 85))

    record = {
        "timestamp": now.astimezone().isoformat(),
        "label": result.label,
        "source": result.source,
        "process": ctx.process,
        "window_title": ctx.window_title,
        "tab_title": ctx.tab_title,
        "file": filename,
    }
    _append_metadata(metadata_path, record)
    logger.info(
        "Captured %s (label=%s, source=%s, process=%s)",
        filename,
        result.label,
        result.source,
        ctx.process or "unknown",
    )


def main() -> int:
    config_path = BASE_DIR / "config.yaml"
    rules_path = BASE_DIR / "rules.yaml"

    if not config_path.exists():
        logger.error("Missing config file: %s", config_path)
        return 1
    if not rules_path.exists():
        logger.error("Missing rules file: %s", rules_path)
        return 1

    config = load_config(config_path)
    rules = load_rules(rules_path)

    interval_minutes = config.get("interval_minutes", 15)
    interval_seconds = interval_minutes * 60
    output_dir = BASE_DIR / config.get("output_dir", "./output")
    camera_index = config.get("camera_index", 0)
    labels: list[str] = config.get("labels", ["work", "uni", "gaming", "unknown"])
    hotkeys: dict[str, str] = config.get("hotkeys", {})

    controller = AppController()
    _, tray_icon = start_tray(BASE_DIR, labels, hotkeys, controller)

    camera = WebcamCapture(camera_index=camera_index)
    try:
        camera.open()
        logger.info(
            "Timelapse started (interval=%d min, output=%s)",
            interval_minutes,
            output_dir,
        )

        while not controller.should_quit():
            _sleep_until_next_interval(interval_seconds)
            if controller.should_quit():
                break
            if controller.is_paused():
                logger.info("Capture paused, skipping interval")
                continue

            try:
                _capture_once(camera, config, rules, output_dir)
            except Exception:
                logger.exception("Capture failed, will retry next interval")

    finally:
        stop_tray()
        tray_icon.stop()
        camera.close()
        logger.info("Timelapse stopped")

    return 0


if __name__ == "__main__":
    sys.exit(main())
