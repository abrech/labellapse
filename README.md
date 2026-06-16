# Desk Activity Timelapse

Captures a webcam photo every 15 minutes and labels each image based on what you are doing on your PC. Labels are inferred from the foreground app or browser tab title, with manual override via hotkeys and a system tray menu.

## Requirements

- Windows 10/11
- Python 3.10+
- A webcam

## Setup

```powershell
cd C:\Privat\time_label
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```powershell
python timelapse.py
```

A tray icon appears in the notification area. The script waits until the next 15-minute boundary, then captures and saves a photo. Use the tray menu or hotkeys to override the label when inference is wrong.

### Hotkeys (default)

| Hotkey | Action |
|--------|--------|
| `Ctrl+Alt+W` | Set label to **work** |
| `Ctrl+Alt+U` | Set label to **uni** |
| `Ctrl+Alt+G` | Set label to **gaming** |
| `Ctrl+Alt+0` | Clear manual label |

Hotkeys are configured in [`config.yaml`](config.yaml). The `keyboard` library may require running the terminal as administrator if hotkeys do not register.

### Tray menu

- Pick a label (work / uni / gaming) — stays active until changed or cleared
- **Clear manual label** — return to automatic inference
- **Pause capturing** — skip captures until resumed
- **Quit** — stop the script

## Output

Photos and metadata are stored under `output/`:

```
output/
└── 2026-06-16/
    ├── 143000_work.jpg
    ├── 151500_uni.jpg
    └── metadata.jsonl
```

Each line in `metadata.jsonl` records the timestamp, label, inference source, foreground process, window title, and filename.

Manual override state is stored in `state.json` (gitignored).

## Configuration

### [`config.yaml`](config.yaml)

- `interval_minutes` — capture interval (default: 15)
- `output_dir` — where images are saved
- `camera_index` — webcam device index (default: 0)
- `jpeg_quality` — JPEG compression 0–100
- `labels` — labels shown in the tray menu
- `hotkeys` — global shortcut map

### [`rules.yaml`](rules.yaml)

Maps labels to foreground processes and window/tab title patterns. Matching is case-insensitive; title patterns use substring matching.

When the foreground app is a browser (Chrome, Edge, Firefox, etc.), the active tab title is extracted from the window title and matched against the `titles` lists.

Example:

```yaml
labels:
  work:
    processes: [Cursor.exe, Code.exe]
    titles: [GitHub, Jira]
  uni:
    titles: [Canvas, Moodle, Zoom]
  gaming:
    processes: [steam.exe]
    titles: [Steam, Elden Ring]
```

Labels are checked in the order listed under `priority`. The first match wins; otherwise the `default` label is used (`unknown`).

## Tuning rules

1. Run the script for a day.
2. Open `output/YYYY-MM-DD/metadata.jsonl` and find rows where `label` is wrong.
3. Add the `process` or `window_title` / `tab_title` pattern to the appropriate label in `rules.yaml`.
4. Restart the script.

If inference is unreliable for a session, set a manual label from the tray or hotkey — it overrides inference until you clear it.

## Run at login (optional)

To start automatically when you log in:

1. Open **Task Scheduler** → Create Basic Task
2. Trigger: **When I log on**
3. Action: **Start a program**
4. Program: `C:\Privat\time_label\.venv\Scripts\python.exe`
5. Arguments: `C:\Privat\time_label\timelapse.py`
6. Start in: `C:\Privat\time_label`

## Privacy

All data stays local on your machine. Photos are not uploaded anywhere. Pause or quit from the tray when you do not want captures.
