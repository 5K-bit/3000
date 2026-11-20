from __future__ import annotations

import json
import time
from dataclasses import asdict
from typing import Optional

import cv2
import typer

from three_thousand.core.camera import capture_frame, is_camera_available, parse_source, save_frame
from three_thousand.core.config import AppConfig
from three_thousand.core.motion import MotionDetector
from three_thousand.obeos_events import enqueue_event as publish_event, delivery_status, shutdown_delivery, start_delivery
from three_thousand.storage.sqlite_store import SQLiteStore
from three_thousand.ui.console import console, print_error, print_events, print_motion_alert, print_snapshot_saved, print_status

app = typer.Typer(help="3000 local-first camera sentinel.", no_args_is_help=True)

SourceOption = typer.Option(
    "0",
    "--source",
    "-s",
    envvar="THREE_THOUSAND_SOURCE",
    help="Camera index (e.g. 0) or path to a video file.",
)


def _build_runtime(source: str = "0") -> tuple[AppConfig, SQLiteStore]:
    config = AppConfig(camera_index=parse_source(source))
    config.ensure_paths()
    store = SQLiteStore(config.database_path)
    store.initialize()
    return config, store


@app.command()
def status(source: str = SourceOption) -> None:
    """Check whether the configured camera is available (exit 1 if not)."""
    config, _ = _build_runtime(source)
    try:
        available = is_camera_available(config.camera_index)
    except Exception:
        available = False
    print_status(available)
    console.print({"event_delivery": delivery_status()})
    if not available:
        raise typer.Exit(code=1)


@app.command()
def snapshot(source: str = SourceOption) -> None:
    """Capture and store a single camera frame."""
    config, store = _build_runtime(source)
    try:
        frame = capture_frame(config.camera_index)
        if frame is None:
            print_error("Unable to capture frame. Is a camera available?")
            raise typer.Exit(code=1)
        snapshot_path = save_frame(frame, config.snapshots_dir)
        store.add_event(
            event_type="snapshot_created",
            confidence=1.0,
            snapshot_path=str(snapshot_path),
            metadata={},
        )
        publish_event("project3000.snapshot.created", {"snapshot_path": str(snapshot_path)})
        print_snapshot_saved(str(snapshot_path))
    except typer.Exit:
        raise
    except RuntimeError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    except Exception:
        print_error("Snapshot failed unexpectedly.")
        raise typer.Exit(code=1)


@app.command()
def watch(
    source: str = SourceOption,
    interval_seconds: float = typer.Option(0.2, "--interval-seconds", min=0.0),
    motion_threshold: float = typer.Option(0.02, "--motion-threshold", min=0.0, max=1.0),
    cooldown_seconds: float = typer.Option(
        5.0, "--cooldown-seconds", min=0.0, help="Minimum seconds between recorded motion events."
    ),
    max_frames: Optional[int] = typer.Option(None, "--max-frames", min=1, help="Stop after N frames."),
) -> None:
    """Run motion detection loop and persist local events."""
    config, store = _build_runtime(source)
    is_file = isinstance(config.camera_index, str)
    detector = MotionDetector(area_threshold_ratio=motion_threshold)
    try:
        capture = cv2.VideoCapture(config.camera_index)
    except Exception:
        print_error("OpenCV could not initialize camera capture.")
        raise typer.Exit(code=1)
    if not capture or not capture.isOpened():
        if capture:
            capture.release()
        print_error("Camera unavailable. Cannot start watch.")
        raise typer.Exit(code=1)
    start_delivery()
    console.print("[cyan]Watching camera feed. Press Ctrl+C to stop.[/cyan]")
    last_event_at: float | None = None
    frames = 0
    try:
        while max_frames is None or frames < max_frames:
            ok, frame = capture.read()
            if not ok:
                if is_file:
                    console.print("[cyan]End of video file.[/cyan]")
                else:
                    print_error("Camera frame read failed. Stopping watch.")
                break
            frames += 1
            try:
                result = detector.detect(frame)
                now = time.monotonic()
                in_cooldown = last_event_at is not None and now - last_event_at < cooldown_seconds
                if result.detected and not in_cooldown:
                    last_event_at = now
                    snapshot_path = save_frame(frame, config.snapshots_dir)
                    store.add_event(
                        event_type="motion_detected",
                        confidence=result.confidence,
                        snapshot_path=str(snapshot_path),
                        metadata=result.metadata,
                    )
                    publish_event("project3000.motion.detected", {
                        "camera_id": str(config.camera_index),
                        "confidence": result.confidence,
                        "snapshot_path": str(snapshot_path),
                        "metadata": result.metadata,
                    })
                    print_motion_alert(result.confidence, str(snapshot_path))
            except Exception:
                print_error("Frame processing failed; continuing watch loop.")
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        console.print("[cyan]Watch stopped.[/cyan]")
    except Exception:
        print_error("Watch failed unexpectedly.")
        raise typer.Exit(code=1)
    finally:
        capture.release()
        shutdown_delivery()


@app.command()
def events(
    limit: int = typer.Option(20, "--limit", min=1, max=1000),
    as_json: bool = typer.Option(False, "--json", help="Emit events as JSON lines."),
) -> None:
    """List recent motion events."""
    _, store = _build_runtime()
    found = store.list_events(limit=limit)
    if as_json:
        for event in found:
            typer.echo(json.dumps(asdict(event)))
        return
    print_events(found)


if __name__ == "__main__":
    app()
