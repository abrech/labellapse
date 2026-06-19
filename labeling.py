"""Label inference from rules and manual override state."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from context import ForegroundContext

STATE_FILENAME = "state.json"
INACTIVE_MANUAL_LABEL = "inactive"


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


def _context_anchor(ctx: ForegroundContext) -> dict[str, str | None]:
    return {
        "process": ctx.process or "",
        "window_title": ctx.window_title or "",
        "tab_title": ctx.tab_title or "",
    }


def set_manual_label(base_dir: Path, label: str) -> None:
    state = load_state(base_dir)
    state["manual_label"] = label
    state["manual_set_at"] = datetime.now(timezone.utc).isoformat()
    state.pop("inactive_anchor", None)
    save_state(base_dir, state)


def set_inactive_label(base_dir: Path, ctx: ForegroundContext) -> None:
    state = load_state(base_dir)
    state["manual_label"] = INACTIVE_MANUAL_LABEL
    state["manual_set_at"] = datetime.now(timezone.utc).isoformat()
    state["inactive_anchor"] = _context_anchor(ctx)
    save_state(base_dir, state)


def maybe_clear_inactive_on_context_change(base_dir: Path, ctx: ForegroundContext) -> bool:
    state = load_state(base_dir)
    if state.get("manual_label") != INACTIVE_MANUAL_LABEL:
        return False

    anchor = state.get("inactive_anchor")
    if not isinstance(anchor, dict):
        clear_manual_label(base_dir)
        return True

    current = _context_anchor(ctx)
    if (
        current["process"] != anchor.get("process", "")
        or current["window_title"] != anchor.get("window_title", "")
        or current["tab_title"] != (anchor.get("tab_title") or "")
    ):
        clear_manual_label(base_dir)
        return True

    return False


def clear_manual_label(base_dir: Path) -> None:
    state = load_state(base_dir)
    state.pop("manual_label", None)
    state.pop("manual_set_at", None)
    state.pop("inactive_anchor", None)
    save_state(base_dir, state)


def _matches_pattern(text: str, patterns: list[str]) -> bool:
    text_lower = text.lower()
    for pattern in patterns:
        if pattern.lower() in text_lower:
            return True
    return False


def infer_label(
    ctx: ForegroundContext,
    rules: dict[str, Any],
    hostname: str | None = None,
) -> str:
    priority, labels = _rules_for_host(rules, hostname)
    default = _default_for_host(rules, hostname)

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


def _host_profile_for_hostname(
    rules: dict[str, Any],
    hostname: str,
) -> dict[str, Any] | None:
    hosts_cfg = rules.get("hosts")
    if not hosts_cfg:
        return None

    profiles: list[dict[str, Any]]
    if isinstance(hosts_cfg, dict):
        profiles = [
            {"hostnames": [key], **cfg}
            for key, cfg in hosts_cfg.items()
            if isinstance(cfg, dict)
        ]
    elif isinstance(hosts_cfg, list):
        profiles = [p for p in hosts_cfg if isinstance(p, dict)]
    else:
        return None

    hostname_lower = hostname.lower()
    for profile in profiles:
        names = profile.get("hostnames", [])
        if any(isinstance(name, str) and name.lower() == hostname_lower for name in names):
            return profile
    return None


def _default_for_host(rules: dict[str, Any], hostname: str | None) -> str:
    if hostname:
        host_cfg = _host_profile_for_hostname(rules, hostname)
        if host_cfg is not None:
            host_default = host_cfg.get("default")
            if isinstance(host_default, str) and host_default:
                return host_default
    return rules.get("default", "unknown")


def _rules_for_host(
    rules: dict[str, Any],
    hostname: str | None,
) -> tuple[list[str], dict[str, dict[str, list[str]]]]:
    base_labels: dict[str, dict[str, list[str]]] = rules.get("labels", {})
    base_priority: list[str] = rules.get("priority", list(base_labels.keys()))

    if not hostname:
        return base_priority, base_labels

    host_cfg = _host_profile_for_hostname(rules, hostname)
    if host_cfg is None:
        return base_priority, base_labels

    merged_labels = {**base_labels, **host_cfg.get("labels", {})}
    priority = host_cfg.get("priority", base_priority)
    return priority, merged_labels
