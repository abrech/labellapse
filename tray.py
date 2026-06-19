"""System tray menu and global hotkeys for manual label override."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable

import keyboard
from PIL import Image, ImageDraw
from pystray import Icon, Menu, MenuItem

from context import get_foreground_context
from labeling import (
    INACTIVE_MANUAL_LABEL,
    clear_manual_label,
    get_manual_label,
    set_inactive_label,
    set_manual_label,
)

logger = logging.getLogger(__name__)

TRAY_LABELS_EXCLUDED = frozenset({"unknown", INACTIVE_MANUAL_LABEL})


class AppController:
    """Shared runtime flags accessed by the tray and main loop."""

    def __init__(self) -> None:
        self.paused = False
        self.quit_requested = False
        self._lock = threading.Lock()

    def request_quit(self) -> None:
        with self._lock:
            self.quit_requested = True

    def should_quit(self) -> bool:
        with self._lock:
            return self.quit_requested

    def set_paused(self, paused: bool) -> None:
        with self._lock:
            self.paused = paused

    def is_paused(self) -> bool:
        with self._lock:
            return self.paused


def _make_icon_image() -> Image.Image:
    size = 64
    image = Image.new("RGB", (size, size), color=(40, 44, 52))
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, size - 8, size - 8), fill=(97, 175, 239))
    draw.rectangle((22, 28, 42, 36), fill=(40, 44, 52))
    return image


def _label_menu_text(label: str, base_dir: Path) -> str:
    current = get_manual_label(base_dir)
    if current == label:
        return f"{label} (active)"
    return label


def _on_label_selected(base_dir: Path, label: str, icon: Icon) -> None:
    set_manual_label(base_dir, label)
    logger.info("Manual label set to %s", label)
    icon.update_menu()


def _on_inactive_selected(base_dir: Path, icon: Icon) -> None:
    ctx = get_foreground_context()
    set_inactive_label(base_dir, ctx)
    logger.info("Manual label set to inactive (process=%s)", ctx.process or "unknown")
    icon.update_menu()


def _on_clear_label(base_dir: Path, icon: Icon) -> None:
    clear_manual_label(base_dir)
    logger.info("Manual label cleared")
    icon.update_menu()


def _toggle_pause(controller: AppController, icon: Icon | None) -> None:
    controller.set_paused(not controller.is_paused())
    state = "paused" if controller.is_paused() else "resumed"
    logger.info("Recording %s", state)
    if icon is not None:
        icon.update_menu()


def _on_quit(controller: AppController, icon: Icon | None) -> None:
    controller.request_quit()
    logger.info("Quit requested")
    if icon is not None:
        icon.stop()


def _make_label_menu_item(
    base_dir: Path,
    label: str,
    icon_holder: dict[str, Icon | None],
) -> MenuItem:
    def text(_icon: Icon) -> str:
        return _label_menu_text(label, base_dir)

    def action(_icon: Icon, _item: MenuItem) -> None:
        _on_label_selected(base_dir, label, icon_holder["icon"])

    return MenuItem(text, action)


def _make_inactive_menu_item(
    base_dir: Path,
    icon_holder: dict[str, Icon | None],
) -> MenuItem:
    def text(_icon: Icon) -> str:
        if get_manual_label(base_dir) == INACTIVE_MANUAL_LABEL:
            return "Inactive (away from desk) (active)"
        return "Inactive (away from desk)"

    def action(_icon: Icon, _item: MenuItem) -> None:
        _on_inactive_selected(base_dir, icon_holder["icon"])

    return MenuItem(text, action)


def _build_menu(
    base_dir: Path,
    labels: list[str],
    controller: AppController,
    icon_holder: dict[str, Icon | None],
) -> Menu:
    label_items = [
        _make_label_menu_item(base_dir, label, icon_holder)
        for label in labels
        if label not in TRAY_LABELS_EXCLUDED
    ]

    return Menu(
        *label_items,
        _make_inactive_menu_item(base_dir, icon_holder),
        Menu.SEPARATOR,
        MenuItem(
            "Clear manual label",
            lambda _: _on_clear_label(base_dir, icon_holder["icon"]),
        ),
        MenuItem(
            lambda _: "Resume recording" if controller.is_paused() else "Pause recording",
            lambda _: _toggle_pause(controller, icon_holder["icon"]),
        ),
        MenuItem("Quit", lambda _: _on_quit(controller, icon_holder["icon"])),
    )


def _register_hotkeys(
    base_dir: Path,
    hotkeys: dict[str, str],
    labels: list[str],
    on_menu_update: Callable[[], None],
) -> None:
    valid_labels = {label for label in labels if label not in TRAY_LABELS_EXCLUDED}

    for label, combo in hotkeys.items():
        if label == "clear":
            keyboard.add_hotkey(
                combo,
                lambda: (_clear_and_update(base_dir, on_menu_update)),
            )
            logger.info("Registered hotkey %s -> clear manual label", combo)
            continue

        if label == INACTIVE_MANUAL_LABEL:
            keyboard.add_hotkey(
                combo,
                lambda: (_set_inactive_and_update(base_dir, on_menu_update)),
            )
            logger.info("Registered hotkey %s -> inactive", combo)
            continue

        if label not in valid_labels:
            logger.warning("Hotkey for unknown label %r ignored", label)
            continue

        keyboard.add_hotkey(
            combo,
            lambda lbl=label: (_set_and_update(base_dir, lbl, on_menu_update)),
        )
        logger.info("Registered hotkey %s -> %s", combo, label)


def _set_and_update(base_dir: Path, label: str, on_menu_update: Callable[[], None]) -> None:
    set_manual_label(base_dir, label)
    logger.info("Manual label set to %s (hotkey)", label)
    on_menu_update()


def _set_inactive_and_update(base_dir: Path, on_menu_update: Callable[[], None]) -> None:
    ctx = get_foreground_context()
    set_inactive_label(base_dir, ctx)
    logger.info("Manual label set to inactive (hotkey, process=%s)", ctx.process or "unknown")
    on_menu_update()


def _clear_and_update(base_dir: Path, on_menu_update: Callable[[], None]) -> None:
    clear_manual_label(base_dir)
    logger.info("Manual label cleared (hotkey)")
    on_menu_update()


def start_tray(
    base_dir: Path,
    labels: list[str],
    hotkeys: dict[str, str],
    controller: AppController,
) -> tuple[threading.Thread, Icon]:
    icon_holder: dict[str, Icon | None] = {"icon": None}

    def on_menu_update() -> None:
        icon = icon_holder["icon"]
        if icon is not None:
            icon.update_menu()

    _register_hotkeys(base_dir, hotkeys, labels, on_menu_update)

    icon = Icon(
        "time_label",
        _make_icon_image(),
        "Desk Activity Recorder",
        menu=_build_menu(base_dir, labels, controller, icon_holder),
    )
    icon_holder["icon"] = icon

    def run_icon() -> None:
        icon.run()

    thread = threading.Thread(target=run_icon, daemon=True, name="tray")
    thread.start()
    return thread, icon


def stop_tray() -> None:
    keyboard.unhook_all_hotkeys()
