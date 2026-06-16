# Desk Activity Timelapse

A split setup for desk timelapses: a Raspberry Pi captures webcam photos on an interval, Windows PCs record foreground activity and labels, and a merge step joins them by timestamp.

## Architecture

| Script | Machine | Purpose |
|--------|---------|---------|
| [`pi_capture.py`](pi_capture.py) | Raspberry Pi | Webcam photos every N minutes |
| [`record_activity.py`](record_activity.py) | Desktop / laptop | Activity sampling + tray hotkeys |
| [`merge.py`](merge.py) | Desktop | Join images with activity logs |

Sync Pi images and laptop activity logs to the desktop manually (Syncthing, rsync, copy, etc.) — paths are configurable in [`config.yaml`](config.yaml).

## Requirements

**Raspberry Pi**

- Python 3.10+
- USB webcam
- [`requirements-pi.txt`](requirements-pi.txt)

**Windows (desktop / laptop)**

- Windows 10/11
- Python 3.10+
- [`requirements.txt`](requirements.txt)

## Setup

### Raspberry Pi

```bash
cd ~/labellapse
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-pi.txt
```

Edit [`config.pi.yaml`](config.pi.yaml) for capture interval and output path.

### Windows

```powershell
cd C:\Code\_projects\labellapse
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Edit [`config.yaml`](config.yaml) and [`rules.yaml`](rules.yaml).

## Run

### Pi — capture photos

```bash
python pi_capture.py
```

Saves timestamp-only JPEGs to `images/`:

```
images/
  2026-06-16/
    143000.jpg
    151500.jpg
```

### Windows — record activity

```powershell
python record_activity.py
```

A tray icon appears. The script samples foreground context every 60 seconds (configurable) and appends to `activity/{hostname}/YYYY-MM-DD.jsonl`.

#### Hotkeys (default)

| Hotkey | Action |
|--------|--------|
| `Ctrl+Alt+W` | Set manual label to **work** |
| `Ctrl+Alt+H` | Set manual label to **hobby** |
| `Ctrl+Alt+U` | Set manual label to **uni** |
| `Ctrl+Alt+G` | Set manual label to **gaming** |
| `Ctrl+Alt+0` | Clear manual label |

Hotkeys are configured in [`config.yaml`](config.yaml). The `keyboard` library may require running as administrator if hotkeys do not register.

#### Tray menu

- Pick a label (work / hobby / uni / gaming) — stored separately from auto-inference
- **Clear manual label**
- **Pause recording** — no samples written while paused
- **Quit**

### Desktop — merge

After Pi images and activity logs are available locally:

```powershell
python merge.py
```

Produces labeled photos and metadata under `output/`:

```
output/
  2026-06-16/
    143000_work.jpg
    151500_inactive.jpg
    metadata.jsonl
```

Re-running merge overwrites merged images and rebuilds metadata for processed dates.

## Label semantics

| Field | Meaning |
|-------|---------|
| `label` | Auto-inferred from rules (`work`, `hobby`, `uni`, `gaming`, `unknown`) — never replaced by manual |
| `manual_label` | Present when a manual override was active at the matched sample time |
| `manual_set_at` | When the manual label was last set |
| `inactive` | No activity sample within `max_gap_seconds` of the image (neither PC was recording) |

Compare `label` and `manual_label` over time to spot stale manual overrides (e.g. auto `gaming` for an hour while manual still says `work`).

Manual override state between runs is stored in `state.json` (gitignored).

## Configuration

### [`config.pi.yaml`](config.pi.yaml) (Pi)

- `interval_minutes` — capture interval (default: 15)
- `output_dir` — where images are saved (default: `./images`)
- `camera_index` — webcam device index (default: 0)
- `jpeg_quality` — JPEG compression 0–100

### [`config.yaml`](config.yaml) (Windows + merge)

- `activity_interval_seconds` — how often to sample foreground context (default: 60)
- `activity_dir` — root for activity logs (default: `./activity`)
- `activity_dir` — root for activity logs (default: `./activity`); logs go to `activity/{hostname}/` using the machine's Windows computer name
- `labels` — labels shown in the tray menu
- `hotkeys` — global shortcut map
- `merge.images_dir` — Pi images directory (synced locally)
- `merge.activity_dirs` — one or more activity log roots (supports host subdirs or direct host dirs)
- `merge.output_dir` — merged output directory
- `merge.max_gap_seconds` — beyond this gap, images are labeled `inactive`

### [`rules.yaml`](rules.yaml)

Maps labels to foreground processes and window/tab title patterns. Matching is case-insensitive; title patterns use substring matching.

When the foreground app is a browser (Chrome, Edge, Firefox, etc.), the active tab title is extracted from the window title and matched against the `titles` lists.

Labels are checked in the order listed under `priority`. The first match wins; otherwise the `default` label is used (`unknown`).

On hosts listed under `hosts` → `hostnames` in [`rules.yaml`](rules.yaml), programming apps (Cursor, VS Code, GitHub) infer as **hobby** instead of **work**. Add your desktop's Windows computer name there — it is the same `hostname` value written to activity metadata automatically.

## Tuning rules

1. Run the activity recorder for a day.
2. Open `activity/{hostname}/YYYY-MM-DD.jsonl` and find rows where `label` is wrong.
3. Add the `process` or title pattern to the appropriate label in [`rules.yaml`](rules.yaml).
4. Restart the recorder.

## Run at login

### Windows (Task Scheduler)

1. Open **Task Scheduler** → Create Basic Task
2. Trigger: **When I log on**
3. Action: **Start a program**
4. Program: `C:\Code\_projects\labellapse\.venv\Scripts\python.exe`
5. Arguments: `C:\Code\_projects\labellapse\record_activity.py`
6. Start in: `C:\Code\_projects\labellapse`

Run the same on both desktop and laptop.

### Raspberry Pi (systemd)

Create `/etc/systemd/system/labellapse-capture.service`:

```ini
[Unit]
Description=Labellapse Pi webcam capture
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/labellapse
ExecStart=/home/pi/labellapse/.venv/bin/python pi_capture.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl enable --now labellapse-capture.service
```

## Privacy

All data stays local. Photos are not uploaded anywhere. Pause or quit the recorder when you do not want activity logged.
