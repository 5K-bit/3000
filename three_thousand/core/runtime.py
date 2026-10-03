"""Single-camera synchronous capture: bounded memory, recoverable disconnections."""
from __future__ import annotations

import os
import time
from typing import Callable

from three_thousand.core.camera import open_capture
from three_thousand.core.config import AppConfig
from three_thousand.core.events import utc_timestamp
from three_thousand.core.evidence import record_observation
from three_thousand.core.health import health_record, write_health
from three_thousand.core.motion import MotionDetector
from three_thousand.obeos_events import delivery_status, enqueue_event
from three_thousand.storage.sqlite_store import SQLiteStore


class WatchRuntime:
    def __init__(
        self, config: AppConfig, store: SQLiteStore, *, interval_seconds=0.2,
        motion_threshold=0.02, cooldown_seconds=5.0, min_free_mb=100,
        capture_factory: Callable = open_capture, publish: Callable = enqueue_event,
        on_motion: Callable | None = None, clock: Callable = time.monotonic,
        sleep: Callable = time.sleep,
    ):
        self.config, self.store = config, store
        self.interval = interval_seconds
        self.cooldown = cooldown_seconds
        self.min_free_mb = min_free_mb
        self.capture_factory, self.publish = capture_factory, publish
        self.on_motion = on_motion
        self.clock, self.sleep = clock, sleep
        self.detector = MotionDetector(motion_threshold)
        self.frames = self.reconnects = self.observations = self.delivery_rejected = 0
        self.last_frame_at = None
        self.last_error = None
        self.last_attempt = float("-inf")

    def _health(self, state: str) -> None:
        delivery = delivery_status()
        warnings = []
        if self.last_error:
            warnings.append(self.last_error)
        if self.delivery_rejected:
            warnings.append("event_enqueue_rejected")
        if delivery.get("state") in {"degraded", "offline"}:
            warnings.append("event_delivery_degraded")
        status = "down" if state == "stopped" else "degraded" if warnings or state != "watching" else "ok"
        write_health(self.config.health_path, health_record(status, warnings=warnings, details={
            "camera_id": self.config.camera_id, "runtime_state": state,
            "pid": os.getpid(), "frames": self.frames, "reconnects": self.reconnects,
            "observations": self.observations, "last_frame_at": self.last_frame_at,
            "event_delivery": delivery, "delivery_rejected": self.delivery_rejected,
        }))

    def run(self, *, duration_seconds: float | None = None) -> None:
        capture = None
        deadline = None if duration_seconds is None else self.clock() + duration_seconds
        backoff = 1.0

        def pause(seconds):
            # Keep health fresh even while reconnect backoff exceeds the stale threshold.
            if deadline is not None:
                seconds = min(seconds, max(0.0, deadline - self.clock()))
            self.sleep(seconds)

        def release():
            nonlocal capture
            if capture is not None:
                try:
                    capture.release()
                except Exception:
                    pass
                capture = None

        try:
            self._health("starting")
            while deadline is None or self.clock() < deadline:
                try:
                    if capture is None:
                        capture = self.capture_factory(self.config.camera_index)
                    if capture is None or not capture.isOpened():
                        raise OSError("camera_unavailable")
                    ok, frame = capture.read()
                    if not ok or frame is None or frame.size == 0:
                        raise OSError("camera_read_failed")
                except Exception:
                    release()
                    self.detector.reset()
                    self.reconnects += 1
                    self.last_error = "camera_unavailable_or_read_failed"
                    self._health("reconnecting")
                    pause(backoff)
                    backoff = min(10.0, backoff * 2)
                    continue
                backoff = 1.0
                self.frames += 1
                self.last_frame_at = utc_timestamp()
                try:
                    result = self.detector.detect(frame)
                    if result.detected and self.clock() - self.last_attempt >= self.cooldown:
                        # Rate-limit failed writes too, avoiding a disk-full retry storm.
                        self.last_attempt = self.clock()
                        payload = record_observation(
                            self.config, self.store, frame, event_type="motion_detected",
                            confidence=result.confidence, metadata=result.metadata,
                            min_free_mb=self.min_free_mb,
                        )
                        self.observations += 1
                        self.last_error = None
                        accepted = self.publish("project3000.motion.detected", payload,
                                                correlation_id=payload["evidence_id"])
                        if not accepted and os.getenv("OBEOS_EVENT_URL", "").strip():
                            self.delivery_rejected += 1
                        if self.on_motion:
                            self.on_motion(result.confidence, payload["snapshot_path"])
                    elif self.last_error == "camera_unavailable_or_read_failed":
                        self.last_error = None
                except Exception as exc:
                    # Error classes, never raw backend errors/credential-bearing source URLs.
                    self.last_error = f"frame_processing_failed:{type(exc).__name__}"
                self._health("watching")
                pause(self.interval)
        finally:
            release()
            self._health("stopped")
