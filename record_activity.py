"""Windows activity recorder: foreground context and labels logged to JSONL."""

from __future__ import annotations

import json
import logging
import re
import socket
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

from context import get_foreground_context
from labeling import (
    get_manual_label,
    get_manual_set_at,
    infer_label,
    load_rules,
)
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


def _resolve_hostname(config: dict) -> str:
    configured = config.get("hostname")
    if isinstance(configured, str) and configured.strip():
        raw = configured.strip()
    else:
        raw = socket.gethostname()
    sanitized = re.sub(r"[^\w.-]", "_", raw)
    return sanitized or "unknown"


def _append_activity(log_path: Path, record: dict) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _sample_once(
    rules: dict,
    activity_dir: Path,
    hostname: str,
) -> None:
    ctx = get_foreground_context()
    label = infer_label(ctx, rules)

    now = datetime.now()
    record: dict = {
        "timestamp": now.astimezone().isoformat(),
        "hostname": hostname,
        "process": ctx.process,
        "window_title": ctx.window_title,
        "tab_title": ctx.tab_title,
        "label": label,
    }

    manual_label = get_manual_label(BASE_DIR)
    if manual_label is not None:
        record["manual_label"] = manual_label
        manual_set_at = get_manual_set_at(BASE_DIR)
        if manual_set_at is not None:
            record["manual_set_at"] = manual_set_at

    date_str = now.strftime("%Y-%m-%d")
    log_path = activity_dir / hostname / f"{date_str}.jsonl"
    _append_activity(log_path, record)
    logger.info(
        "Recorded activity (label=%s, manual=%s, process=%s)",
        label,
        manual_label or "none",
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

    interval_seconds = config.get("activity_interval_seconds", 60)
    activity_dir = BASE_DIR / config.get("activity_dir", "./activity")
    hostname = _resolve_hostname(config)
    labels: list[str] = config.get("labels", ["work", "uni", "gaming", "unknown"])
    hotkeys: dict[str, str] = config.get("hotkeys", {})

    controller = AppController()
    _, tray_icon = start_tray(BASE_DIR, labels, hotkeys, controller)

    try:
        logger.info(
            "Activity recording started (interval=%ds, host=%s, output=%s)",
            interval_seconds,
            hostname,
            activity_dir / hostname,
        )

        while not controller.should_quit():
            if controller.is_paused():
                logger.debug("Recording paused, skipping sample")
            else:
                try:
                    _sample_once(rules, activity_dir, hostname)
                except Exception:
                    logger.exception("Activity sample failed, will retry next interval")

            deadline = time.monotonic() + interval_seconds
            while time.monotonic() < deadline:
                if controller.should_quit():
                    break
                time.sleep(min(0.5, deadline - time.monotonic()))

    finally:
        stop_tray()
        tray_icon.stop()
        logger.info("Activity recording stopped")

    return 0


if __name__ == "__main__":
    sys.exit(main())
