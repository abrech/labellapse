"""Read foreground window and process context on Windows."""

from __future__ import annotations

from dataclasses import dataclass

import psutil
import win32gui
import win32process

BROWSER_PROCESSES = {
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "brave.exe",
    "opera.exe",
    "vivaldi.exe",
}

BROWSER_TITLE_SUFFIXES = (
    " - Google Chrome",
    " - Microsoft Edge",
    " \u2014 Mozilla Firefox",
    " - Mozilla Firefox",
    " - Brave",
    " - Opera",
    " - Vivaldi",
)


@dataclass
class ForegroundContext:
    process: str
    window_title: str
    tab_title: str | None


def _extract_tab_title(window_title: str) -> str | None:
    for suffix in BROWSER_TITLE_SUFFIXES:
        if window_title.endswith(suffix):
            tab = window_title[: -len(suffix)].strip()
            return tab or None
    return window_title.strip() or None


def get_foreground_context() -> ForegroundContext:
    hwnd = win32gui.GetForegroundWindow()
    window_title = win32gui.GetWindowText(hwnd) or ""

    process = ""
    if hwnd:
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process = psutil.Process(pid).name()
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            process = ""

    tab_title = None
    if process.lower() in BROWSER_PROCESSES and window_title:
        tab_title = _extract_tab_title(window_title)

    return ForegroundContext(
        process=process,
        window_title=window_title,
        tab_title=tab_title,
    )
