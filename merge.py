"""Merge Pi images with Windows activity logs by timestamp."""

from __future__ import annotations

import json
import logging
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_FILENAME_RE = re.compile(r"^(\d{6})\.jpg$", re.IGNORECASE)
INACTIVE_LABEL = "inactive"


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _parse_image_timestamp(image_path: Path) -> datetime | None:
    date_str = image_path.parent.name
    if not DATE_DIR_RE.match(date_str):
        return None
    match = TIME_FILENAME_RE.match(image_path.name)
    if not match:
        return None
    time_part = match.group(1)
    try:
        return datetime.strptime(f"{date_str}_{time_part}", "%Y-%m-%d_%H%M%S")
    except ValueError:
        return None


def _parse_image_timestamp_legacy(filename: str) -> datetime | None:
    """Support flat YYYY-MM-DD_HHMMSS.jpg names from older captures."""
    match = re.match(r"^(\d{4}-\d{2}-\d{2})_(\d{6})\.jpg$", filename, re.IGNORECASE)
    if not match:
        return None
    date_part, time_part = match.groups()
    try:
        return datetime.strptime(f"{date_part}_{time_part}", "%Y-%m-%d_%H%M%S")
    except ValueError:
        return None


def _read_activity_log(log_path: Path) -> list[dict]:
    samples: list[dict] = []
    with log_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("Skipping invalid JSON in %s", log_path)
    return samples


def _load_activity_samples(activity_dirs: list[Path], date_str: str) -> list[dict]:
    samples: list[dict] = []
    log_name = f"{date_str}.jsonl"

    for activity_dir in activity_dirs:
        if not activity_dir.is_dir():
            continue

        direct_log = activity_dir / log_name
        if direct_log.exists():
            samples.extend(_read_activity_log(direct_log))
            continue

        for host_dir in activity_dir.iterdir():
            if not host_dir.is_dir():
                continue
            log_path = host_dir / log_name
            if log_path.exists():
                samples.extend(_read_activity_log(log_path))

    return samples


def _sample_timestamp(sample: dict) -> datetime | None:
    raw = sample.get("timestamp")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _find_closest_sample(
    image_ts: datetime,
    samples: list[dict],
) -> tuple[dict | None, float | None]:
    best_sample: dict | None = None
    best_gap: float | None = None
    image_epoch = image_ts.timestamp()

    for sample in samples:
        sample_ts = _sample_timestamp(sample)
        if sample_ts is None:
            continue
        gap = abs(sample_ts.timestamp() - image_epoch)
        if best_gap is None or gap < best_gap:
            best_gap = gap
            best_sample = sample

    return best_sample, best_gap


def _rebuild_metadata_for_date(metadata_path: Path, records: list[dict]) -> None:
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with metadata_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _image_timestamp(image_path: Path) -> datetime | None:
    return _parse_image_timestamp(image_path) or _parse_image_timestamp_legacy(
        image_path.name
    )


def _merge_image(
    image_path: Path,
    samples: list[dict],
    output_dir: Path,
    max_gap_seconds: float,
    metadata_by_date: dict[str, list[dict]],
) -> None:
    image_ts = _image_timestamp(image_path)
    if image_ts is None:
        logger.warning("Skipping unrecognized path: %s", image_path)
        return

    date_str = image_ts.strftime("%Y-%m-%d")
    time_str = image_ts.strftime("%H%M%S")
    closest, gap = _find_closest_sample(image_ts, samples)

    if closest is None or gap is None or gap > max_gap_seconds:
        label = INACTIVE_LABEL
        record: dict = {
            "timestamp": image_ts.isoformat(),
            "label": label,
            "file": f"{time_str}_{label}.jpg",
        }
        if gap is not None:
            record["activity_gap_seconds"] = round(gap, 1)
    else:
        label = closest.get("label", "unknown")
        record = {
            "timestamp": image_ts.isoformat(),
            "label": label,
            "hostname": closest.get("hostname"),
            "process": closest.get("process"),
            "window_title": closest.get("window_title"),
            "tab_title": closest.get("tab_title"),
            "file": f"{time_str}_{label}.jpg",
            "activity_gap_seconds": round(gap, 1),
        }
        if "manual_label" in closest:
            record["manual_label"] = closest["manual_label"]
        if "manual_set_at" in closest:
            record["manual_set_at"] = closest["manual_set_at"]

    output_name = record["file"]
    day_output_dir = output_dir / date_str
    day_output_dir.mkdir(parents=True, exist_ok=True)
    output_path = day_output_dir / output_name
    shutil.copy2(image_path, output_path)

    metadata_by_date.setdefault(date_str, []).append(record)
    logger.info(
        "Merged %s -> %s (label=%s, gap=%s)",
        image_path.name,
        output_name,
        label,
        f"{gap:.1f}s" if gap is not None else "none",
    )


def _discover_images(images_dir: Path) -> list[Path]:
    image_paths: list[Path] = []

    for day_dir in sorted(images_dir.iterdir()):
        if day_dir.is_dir() and DATE_DIR_RE.match(day_dir.name):
            image_paths.extend(sorted(day_dir.glob("*.jpg")))

    for image_path in sorted(images_dir.glob("*.jpg")):
        if _parse_image_timestamp_legacy(image_path.name) is not None:
            image_paths.append(image_path)

    return sorted(image_paths)


def main() -> int:
    config_path = BASE_DIR / "config.yaml"
    if not config_path.exists():
        logger.error("Missing config file: %s", config_path)
        return 1

    config = load_config(config_path)
    merge_config = config.get("merge", {})

    images_dir = BASE_DIR / merge_config.get("images_dir", "./images")
    output_dir = BASE_DIR / merge_config.get("output_dir", "./output")
    max_gap_seconds = float(merge_config.get("max_gap_seconds", 120))

    activity_dirs_raw = merge_config.get("activity_dirs", ["./activity"])
    activity_dirs = [BASE_DIR / Path(p) for p in activity_dirs_raw]

    if not images_dir.is_dir():
        logger.error("Images directory not found: %s", images_dir)
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)

    image_paths = _discover_images(images_dir)
    if not image_paths:
        logger.warning("No images found in %s", images_dir)
        return 0

    dates_needed = set()
    for image_path in image_paths:
        image_ts = _image_timestamp(image_path)
        if image_ts is not None:
            dates_needed.add(image_ts.strftime("%Y-%m-%d"))

    samples_by_date: dict[str, list[dict]] = {}
    for date_str in dates_needed:
        samples_by_date[date_str] = _load_activity_samples(activity_dirs, date_str)

    metadata_by_date: dict[str, list[dict]] = {}

    for image_path in image_paths:
        image_ts = _image_timestamp(image_path)
        if image_ts is None:
            continue
        date_str = image_ts.strftime("%Y-%m-%d")
        _merge_image(
            image_path,
            samples_by_date.get(date_str, []),
            output_dir,
            max_gap_seconds,
            metadata_by_date,
        )

    for date_str, records in metadata_by_date.items():
        records.sort(key=lambda r: r["timestamp"])
        metadata_path = output_dir / date_str / "metadata.jsonl"
        _rebuild_metadata_for_date(metadata_path, records)

    logger.info("Merge complete (%d images)", len(image_paths))
    return 0


if __name__ == "__main__":
    sys.exit(main())
