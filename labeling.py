"""Label inference from rules and manual override state."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from context import ForegroundContext

STATE_FILENAME = "state.json"


def load_rules(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _state_path(base_dir: Path) -> Path:
    return base_dir / STATE_FILENAME


def load_state(base_dir: Path) -> dict[str, Any]:
    path = _state_path(base_dir)
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(base_dir: Path, state: dict[str, Any]) -> None:
    path = _state_path(base_dir)
    with path.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def get_manual_label(base_dir: Path) -> str | None:
    state = load_state(base_dir)
    label = state.get("manual_label")
    if isinstance(label, str) and label:
        return label
    return None


def get_manual_set_at(base_dir: Path) -> str | None:
    state = load_state(base_dir)
    value = state.get("manual_set_at")
    if isinstance(value, str) and value:
        return value
    return None


def set_manual_label(base_dir: Path, label: str) -> None:
    state = load_state(base_dir)
    state["manual_label"] = label
    state["manual_set_at"] = datetime.now(timezone.utc).isoformat()
    save_state(base_dir, state)


def clear_manual_label(base_dir: Path) -> None:
    state = load_state(base_dir)
    state.pop("manual_label", None)
    state.pop("manual_set_at", None)
    save_state(base_dir, state)


def _matches_pattern(text: str, patterns: list[str]) -> bool:
    text_lower = text.lower()
    for pattern in patterns:
        if pattern.lower() in text_lower:
            return True
    return False


def infer_label(ctx: ForegroundContext, rules: dict[str, Any]) -> str:
    labels: dict[str, dict[str, list[str]]] = rules.get("labels", {})
    priority: list[str] = rules.get("priority", list(labels.keys()))
    default: str = rules.get("default", "unknown")

    process = ctx.process or ""
    title_candidates = [t for t in (ctx.tab_title, ctx.window_title) if t]

    for label in priority:
        rule = labels.get(label, {})
        processes = rule.get("processes", [])
        titles = rule.get("titles", [])

        if process and processes:
            process_lower = process.lower()
            for proc_pattern in processes:
                if proc_pattern.lower() == process_lower:
                    return label

        for title in title_candidates:
            if titles and _matches_pattern(title, titles):
                return label

    return default
