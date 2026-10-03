from __future__ import annotations

import json
from dataclasses import asdict

import typer

from three_thousand.core.camera import capture_frame, is_camera_available, save_frame
from three_thousand.core.config import AppConfig
from three_thousand.core.evidence import record_observation
from three_thousand.core.health import read_health
from three_thousand.core.runtime import WatchRuntime
from three_thousand.obeos_events import enqueue_event as publish_event, shutdown_delivery, start_delivery
from three_thousand.storage.sqlite_store import SQLiteStore
from three_thousand.ui.console import console, print_error, print_events, print_motion_alert, print_snapshot_saved, print_status

app = typer.Typer(help="3000 local-first camera sentinel.", no_args_is_help=True)


def _config() -> AppConfig:
    try:
        return AppConfig.from_env()
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


def _build_runtime() -> tuple[AppConfig, SQLiteStore]:
    config = _config()
    config.ensure_paths()
    store = SQLiteStore(config.database_path)
    store.initialize()
    return config, store


@app.command()
def status() -> None:
    """Probe the configured camera; use health to inspect an active watcher."""
    config = _config()
    try:
        available = is_camera_available(config.camera_index)
    except Exception:
        available = False
    print_status(available)


@app.command()
def health(json_output: bool = typer.Option(False, "--json")) -> None:
    """Read persisted runtime Health Contract v1 without opening the camera."""
    record = read_health(_config().health_path)
    if json_output:
        typer.echo(json.dumps(record))
    else:
        console.print(record)
    if record["status"] != "ok":
        raise typer.Exit(code=1)


@app.command()
def snapshot(min_free_mb: float = typer.Option(100, "--min-free-mb", min=0)) -> None:
    """Capture a frame, persist its local event, then enqueue an OBEOS reference."""
    config, store = _build_runtime()
    try:
        frame = capture_frame(config.camera_index)
        if frame is None:
            print_error("Unable to capture frame. Is a camera available?")
            raise typer.Exit(code=1)
        payload = record_observation(
            config, store, frame, event_type="snapshot_created", confidence=1.0,
            min_free_mb=min_free_mb, saver=save_frame,
        )
        accepted = publish_event("project3000.snapshot.created", payload,
                                 correlation_id=payload["evidence_id"])
        import os
        if not accepted and os.getenv("OBEOS_EVENT_URL", "").strip():
            print_error("Snapshot saved locally, but OBEOS enqueue failed.")
        print_snapshot_saved(payload["snapshot_path"])
    except typer.Exit:
        raise
    except Exception as exc:
        print_error(f"Snapshot failed ({type(exc).__name__}).")
        raise typer.Exit(code=1) from exc
    finally:
        shutdown_delivery()


@app.command()
def watch(
    interval_seconds: float = typer.Option(0.2, "--interval-seconds", min=0.05, max=10),
    motion_threshold: float = typer.Option(0.02, "--motion-threshold", min=0.000001, max=1),
    cooldown_seconds: float = typer.Option(5, "--cooldown-seconds", min=0),
    min_free_mb: float = typer.Option(100, "--min-free-mb", min=0),
    duration_seconds: float | None = typer.Option(None, "--duration-seconds", min=0.1),
) -> None:
    """Watch with reconnect/backoff; Ctrl+C stops and releases the camera."""
    config, store = _build_runtime()
    runtime = WatchRuntime(
        config, store, interval_seconds=interval_seconds, motion_threshold=motion_threshold,
        cooldown_seconds=cooldown_seconds, min_free_mb=min_free_mb, on_motion=print_motion_alert,
    )
    try:
        start_delivery()
        console.print("[cyan]Watching camera feed. Press Ctrl+C to stop.[/cyan]")
        runtime.run(duration_seconds=duration_seconds)
    except KeyboardInterrupt:
        console.print("[cyan]Watch stopped.[/cyan]")
    except Exception as exc:
        print_error(f"Watch failed ({type(exc).__name__}).")
        raise typer.Exit(code=1) from exc
    finally:
        shutdown_delivery()


@app.command()
def events(
    limit: int = typer.Option(20, "--limit", min=1, max=1000),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """List local observations, including snapshots and their evidence metadata."""
    _, store = _build_runtime()
    rows = store.list_events(limit=limit)
    if json_output:
        output = []
        for row in rows:
            item = asdict(row)
            item["metadata"] = json.loads(item.pop("metadata_json"))
            output.append(item)
        typer.echo(json.dumps(output))
    else:
        print_events(rows)


if __name__ == "__main__":
    app()
