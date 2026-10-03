import json
from collections import deque
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from three_thousand.core import evidence
from three_thousand.core.config import AppConfig, parse_source
from three_thousand.core.health import read_health
from three_thousand.core.runtime import WatchRuntime
from three_thousand.storage.sqlite_store import SQLiteStore


class Clock:
    def __init__(self):
        self.now = 0.0
        self.waits = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.now += seconds


class Capture:
    def __init__(self, frames, opened=True):
        self.frames = deque(frames)
        self.opened = opened
        self.released = False

    def isOpened(self):
        return self.opened

    def read(self):
        if not self.frames:
            raise KeyboardInterrupt
        frame = self.frames.popleft()
        if isinstance(frame, Exception):
            raise frame
        return frame is not None, frame

    def release(self):
        self.released = True


def make_runtime(tmp_path, captures, **kwargs):
    config = AppConfig(data_dir=tmp_path, camera_id="front-door")
    config.ensure_paths()
    store = SQLiteStore(config.database_path)
    store.initialize()
    clock = Clock()
    sources = iter(captures)
    sent = []
    def publish(kind, payload, **metadata):
        sent.append((kind, payload, metadata))
        return True
    runtime = WatchRuntime(config, store, capture_factory=lambda _: next(sources),
                           clock=clock, sleep=clock.sleep, publish=publish, **kwargs)
    return runtime, store, sent, clock


def frames():
    black = np.zeros((120, 120, 3), np.uint8)
    white = np.full_like(black, 255)
    return black, white


def test_disconnect_recovery_records_decodable_evidence_and_resets_baseline(tmp_path):
    black, white = frames()
    first = Capture([black, None])
    second = Capture([white, black])
    runtime, store, sent, _ = make_runtime(tmp_path, [first, second])
    states = []
    original = runtime._health
    def observe(state):
        original(state)
        states.append(read_health(runtime.config.health_path))
    runtime._health = observe
    with pytest.raises(KeyboardInterrupt):
        runtime.run()
    assert first.released and second.released
    assert runtime.reconnects == 1
    # The first white frame after reconnect must establish a new baseline, not trigger.
    assert len(store.list_events()) == len(sent) == 1
    kind, payload, metadata = sent[0]
    event = store.list_events()[0]
    assert kind == "project3000.motion.detected"
    assert cv2.imread(event.snapshot_path) is not None
    assert payload["local_event_id"] == event.id
    assert metadata["correlation_id"] == payload["evidence_id"]
    assert json.loads(event.metadata_json)["evidence_id"] == payload["evidence_id"]
    assert payload["camera_id"] == "front-door"
    assert payload["evidence_ref"].startswith("file://")
    assert any(s["details"]["runtime_state"] == "reconnecting" and s["status"] == "degraded" for s in states)
    assert states[-2]["status"] == "ok"
    assert states[-1]["status"] == "down"


def test_unavailable_camera_uses_capped_backoff_and_honors_duration(tmp_path):
    captures = [Capture([], opened=False) for _ in range(10)]
    runtime, _, _, clock = make_runtime(tmp_path, captures)
    runtime.run(duration_seconds=30)
    assert clock.now == 30
    assert clock.waits == [1, 2, 4, 8, 10, 5]
    assert all(c.released for c in captures[:6])


def test_read_exception_recovers_without_leaking_source(tmp_path):
    black, white = frames()
    runtime, store, _, _ = make_runtime(tmp_path, [Capture([OSError('rtsp://user:secret@host')]), Capture([black, white])])
    with pytest.raises(KeyboardInterrupt):
        runtime.run()
    assert len(store.list_events()) == 1
    assert "secret" not in runtime.config.health_path.read_text()


def test_motion_cooldown_bounds_snapshot_growth(tmp_path):
    black, white = frames()
    runtime, store, _, _ = make_runtime(tmp_path, [Capture([black, white] * 40)], cooldown_seconds=5)
    with pytest.raises(KeyboardInterrupt):
        runtime.run()
    assert 3 <= len(store.list_events()) <= 4


def test_disk_guard_preserves_no_false_evidence(tmp_path, monkeypatch):
    black, white = frames()
    runtime, store, sent, _ = make_runtime(tmp_path, [Capture([black, white])])
    monkeypatch.setattr(evidence.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
    with pytest.raises(KeyboardInterrupt):
        runtime.run()
    assert not store.list_events() and not sent
    assert not list(runtime.config.snapshots_dir.glob("*.jpg"))
    assert "frame_processing_failed:OSError" in read_health(runtime.config.health_path)["warnings"]


def test_rejected_enqueue_keeps_local_evidence_and_degrades_health(tmp_path, monkeypatch):
    black, white = frames()
    runtime, store, _, _ = make_runtime(tmp_path, [Capture([black, white])])
    monkeypatch.setenv("OBEOS_EVENT_URL", "http://127.0.0.1:9/events/v1/publish")
    runtime.publish = lambda *args, **kwargs: False
    with pytest.raises(KeyboardInterrupt):
        runtime.run()
    assert len(store.list_events()) == 1
    assert runtime.delivery_rejected == 1
    assert "event_enqueue_rejected" in read_health(runtime.config.health_path)["warnings"]


def test_failed_database_write_removes_unacknowledged_snapshot(tmp_path, monkeypatch):
    black, _ = frames()
    runtime, store, _, _ = make_runtime(tmp_path, [])
    def fail(**kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(store, "add_event", fail)
    with pytest.raises(OSError):
        evidence.record_observation(runtime.config, store, black, event_type="snapshot_created", confidence=1)
    assert not list(runtime.config.snapshots_dir.iterdir())


@pytest.mark.parametrize("value,expected", [("0", 0), ("12", 12), ("rtsp://user:pass@camera/live", "rtsp://user:pass@camera/live")])
def test_camera_source_config(value, expected):
    assert parse_source(value) == expected


@pytest.mark.parametrize("value", ["-1", "file:///tmp/image", "rtsp://", "secret-value"])
def test_invalid_camera_source_is_rejected_without_echo(value):
    with pytest.raises(ValueError) as exc:
        parse_source(value)
    assert value not in str(exc.value)
