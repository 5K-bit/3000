# 3000

[![CI](https://github.com/5K-bit/3000/actions/workflows/ci.yml/badge.svg)](https://github.com/5K-bit/3000/actions/workflows/ci.yml)

3000 is a local-first computer vision sentinel. It watches a camera feed, detects motion, saves snapshots, and writes events locally.

## Requirements

- Python 3.11+
- OpenCV-compatible camera source

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Commands

```bash
3000 status
3000 snapshot
3000 watch
3000 events
```

### Command behavior

All camera commands take `--source` (or `THREE_THOUSAND_SOURCE`): a camera index like `0` (default) or a path to a video file, so you can try 3000 without a webcam.

- `3000 status`: checks the source; exits `1` if unavailable (usable as a health check).
- `3000 snapshot`: captures one frame, writes it to `data/snapshots/`, and records a `snapshot_created` event.
- `3000 watch`: frame-differencing motion detection. On motion:
  - saves snapshot
  - writes event to SQLite (`data/events.sqlite3`)
  - prints a Rich alert in terminal

  Options: `--motion-threshold` (area ratio, default 0.02), `--cooldown-seconds` (min gap between events, default 5), `--interval-seconds`, `--max-frames`. A video file source stops at end of file.
- `3000 events`: lists recent events; `--limit N`, `--json` for JSON lines.

### Try it without a camera

```bash
3000 watch --source clip.mp4 --interval-seconds 0
3000 events
```

## Local data layout

- `data/snapshots/*.jpg`: captured frames
- `data/events.sqlite3`: SQLite event database

## Safety

- No cloud or network requirement.
- Handles camera access failures gracefully.
- Does not require a webcam to run tests.