# Project 3000 — OBEOS perception runtime

[![CI](https://github.com/5K-bit/3000/actions/workflows/ci.yml/badge.svg)](https://github.com/5K-bit/3000/actions/workflows/ci.yml)

3000 is OBEOS's local-first camera and perception specialist. Its direction is a dependable DVR/NVR replacement for Agent DVR. It observes and preserves evidence; D.A.I.S.E. reasons over relevant observations through OBEOS's existing event backbone and context fabric.

**This is not yet a complete DVR.** Video clips, playback, object detection and HUD camera panels remain planned. A successful unit test is not camera acceptance evidence.

## Concrete delivery plan

Implement these milestones in dependency order. Keep `5K-bit/3000` authoritative; OBEOS consumes a tested, pinned revision rather than a second editable copy.

| Milestone | Implementation | Acceptance gate | Status |
| --- | --- | --- | --- |
| M1: reliable single-camera observations | Configurable USB/RTSP source and stable camera ID; reconnect with capped backoff; reset motion baseline after reconnect; snapshot cooldown; local evidence/event IDs; persistent JSON health; durable OBEOS delivery regression tests | Simulated disconnect/reconnect, image write failure, missing/stale health and queue restart tests pass; one real-camera disconnect and OBEOS receipt verified on Blackcomputer | Building in this change; hardware gate pending |
| M2: bounded recording | Segmented recording with pre/post-motion clips, evidence manifest, byte/age retention, reserved free space, restart reconciliation of partial files | A known motion interval includes configured lead-in/lead-out; kill/restart leaves playable completed clips; full disk never silently loses acknowledged evidence | Planned after M1 |
| M3: multi-camera supervision | Camera registry, one capture worker per source, bounded queues, per-camera FPS/resolution budgets and independent recovery | Disconnect one camera while another records; enforce measured memory/CPU/storage budgets on Blackcomputer | Planned after M2 |
| M4: optional local detection | Local person/object detector adapter, zones, thresholds and inference sampling; motion-only fallback if unavailable | Labeled local clips measure false alerts and missed detections; missing model keeps capture working; no model/cloud download during operation | Planned after M3 |
| M5: OBEOS operator surfaces | Authenticated evidence lookup/playback and camera health in existing Workspace/HUD; context-fabric aggregation; private iPhone access | Authorized operator can find the exact recorded incident from an OBEOS event; expired media is explicit; raw media stays outside event envelopes | Planned after M2, integration contracts and access controls |

### M1 implementation sequence

1. Audit canonical event/health contracts and both the OBEOS main and stabilization references.
2. Add configuration, reconnecting capture, cooldown and disk-space guard without changing the vendored delivery transport.
3. Persist camera runtime health and evidence metadata; provide `3000 health --json` and `3000 events --json` for automation.
4. Test capture failure/recovery, evidence integrity and durable background retries using synthetic frames and local receivers.
5. Build a wheel and publish a reviewable PR. After merge, advance OBEOS's component pin and record cross-repository acceptance separately.

### Integration baseline (2026-10-03 audit)

- 3000 main `32ffd6a` already has the bounded SQLite-backed delivery queue, despite the previous README omitting it.
- OBEOS main pins `3000-main` at `50984cc`, before the event publisher changes.
- OBEOS PR #7 (`agent/integration-stabilization-v0.9`) contains the canonical event receiver and newer component pins. It remains draft with separate release gates. Do not declare OBEOS main integrated merely because this child passes tests.
- Preserve Event Contract v1 and Health Contract v1. Do not send image/video bytes through `event_backbone`, import DAISE internals or turn every detection into a conversation.

## Install and run on Blackcomputer

Python 3.11+ and an OpenCV-compatible camera are required. From the repository directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
$env:PROJECT3000_CAMERA_SOURCE = "0"
$env:PROJECT3000_CAMERA_ID = "blackcomputer-camera"
$env:PROJECT3000_DATA_DIR = "$PWD\data"
3000 status
3000 watch
```

On Linux, activate with `source .venv/bin/activate` and set the same variables with `export`. Camera source is a device index or RTSP/HTTP(S) URL. Network streams require OpenCV's FFmpeg backend; open/read timeouts are requested from that backend. USB driver calls may still block, so hard process-level stall recovery belongs to M3.

Use one watcher per data directory. M1 runs synchronously with no accumulating frame queue. Blackcomputer must remain awake to capture; the iPhone is an operator client. No AWS runtime is required.

## Configuration and commands

| Setting | Default | Purpose |
| --- | --- | --- |
| `PROJECT3000_CAMERA_SOURCE` | `0` | USB index or network camera URL; never included in events or health |
| `PROJECT3000_CAMERA_ID` | `camera-0` | Stable non-secret identity, letters/numbers/dot/underscore/hyphen |
| `PROJECT3000_DATA_DIR` | `data` | Local evidence, SQLite events and runtime health |
| `OBEOS_EVENT_URL` | unset | Canonical OBEOS event-ingestion endpoint; unset means standalone |
| `OBEOS_DELIVERY_DB` | `~/.project3000/event-delivery.sqlite3` | Durable outbound queue; must be on local writable storage |

```text
3000 status                         Probe the configured camera (may contend with an active watcher)
3000 snapshot                       Save one frame and its local event/evidence reference
3000 watch                          Motion capture with reconnect and 5-second snapshot cooldown
3000 watch --duration-seconds 60     Bounded smoke run (subject to backend read timeouts)
3000 watch --cooldown-seconds 10     Reduce repeated snapshots during sustained movement
3000 watch --min-free-mb 256         Reserve disk headroom before snapshot writes
3000 health --json                   Read persisted runtime health without opening the camera
3000 events --json --limit 20        Read structured local evidence history
```

`health` is a runtime check, while `status` is a one-off device probe. Missing heartbeat is `unknown`, stale or stopped runtime is `down`, reconnecting/storage/delivery problems are `degraded`, and a fresh working runtime is `ok`. A local motion score is changed-area ratio, not a calibrated probability of a person or threat.

## Evidence and delivery

Snapshots live under `data/snapshots/`, events in `data/events.sqlite3`, and runtime health in `data/runtime-health.json`. Each new observation carries a camera ID, stable evidence ID, local event ID, snapshot path and `file://` evidence URI. These are host-local references, **not remotely downloadable links**. Remote evidence serving is M5.

Without OBEOS configured, capture and event history work locally. With OBEOS configured, the existing durable queue sends Event Contract v1 envelopes asynchronously. Queue acceptance is not receiver confirmation. Rejected enqueues and delivery errors degrade health; the local event remains available, but rejected enqueues are not automatically re-created from event history. The local event database and outbound queue are separate transactions; closing that crash window is a prerequisite for stronger delivery guarantees. See [delivery behavior](docs/obeos-delivery.md).

Snapshots are rate-limited and a free-space guard prevents new writes below the configured reserve. Automatic age/size cleanup is M2; monitor storage until then. Configuration URLs can contain camera credentials: keep them out of Git, screenshots and shell history.

## Validation and release evidence

```powershell
python -m pytest
python -m pip wheel . --no-deps --wheel-dir dist
```

Hardware-free tests cover synthetic motion, capture recovery, evidence persistence, health states and durable queue behavior. Before calling M1 operationally accepted, record:

1. Blackcomputer OS, camera model/source type, 3000 revision and OBEOS receiver revision (redact credentials).
2. Camera live → unplug/disconnect → degraded → reconnect → fresh baseline → real motion event.
3. Confirm the snapshot decodes, local event resolves to it and health returns to `ok`.
4. Stop the receiver, generate events, restart 3000, restore the receiver and verify queued event IDs arrive without creating duplicates in OBEOS.
5. Record receiver event IDs and evidence paths, plus CPU, memory and disk growth over a 30-minute run.
6. Update OBEOS's pin/report only after the child revision and receiver combination passes these checks.

**Live camera, Windows driver behavior and Blackcomputer end-to-end acceptance are pending.** No test in this repository can substitute for those observations.
