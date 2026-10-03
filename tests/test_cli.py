from pathlib import Path

import numpy as np
from typer.testing import CliRunner

from three_thousand import cli


runner = CliRunner()


def test_status_handles_unavailable_camera(monkeypatch) -> None:
    monkeypatch.setattr(cli, "is_camera_available", lambda _idx: False)
    result = runner.invoke(cli.app, ["status"])
    assert result.exit_code == 0
    assert "unavailable" in result.stdout.lower()


def test_snapshot_command_uses_capture_and_save(monkeypatch, tmp_path) -> None:
    fake_frame = np.zeros((8, 8, 3), dtype=np.uint8)
    expected_path = tmp_path / "snapshot.jpg"

    monkeypatch.setattr(cli, "capture_frame", lambda _idx: fake_frame)
    monkeypatch.setattr(cli, "save_frame", lambda _frame, _dir: Path(expected_path))

    result = runner.invoke(cli.app, ["snapshot"])
    assert result.exit_code == 0
    assert str(expected_path) in result.stdout


def test_snapshot_command_exits_when_frame_missing(monkeypatch) -> None:
    monkeypatch.setattr(cli, "capture_frame", lambda _idx: None)
    result = runner.invoke(cli.app, ["snapshot"])
    assert result.exit_code == 1


def test_snapshot_persists_traceable_event_and_events_json(monkeypatch):
    import json
    import cv2
    monkeypatch.setattr(cli, "capture_frame", lambda _: np.zeros((20, 20, 3), dtype=np.uint8))
    result = runner.invoke(cli.app, ["snapshot"])
    assert result.exit_code == 0
    result = runner.invoke(cli.app, ["events", "--json"])
    assert result.exit_code == 0
    events = json.loads(result.stdout)
    assert len(events) == 1
    assert events[0]["event_type"] == "snapshot_created"
    assert events[0]["metadata"]["camera_id"] == "test-camera"
    assert events[0]["metadata"]["evidence_id"]
    assert cv2.imread(events[0]["snapshot_path"]) is not None


def test_watch_releases_camera_and_writes_stopped_health(monkeypatch):
    import json
    from three_thousand.core.config import AppConfig
    original = cli.WatchRuntime
    class FakeCapture:
        released = False
        def isOpened(self):
            return True
        def read(self):
            raise KeyboardInterrupt
        def release(self):
            self.released = True
    capture = FakeCapture()
    monkeypatch.setattr(cli, "WatchRuntime", lambda *a, **kw: original(*a, **kw, capture_factory=lambda _: capture))
    result = runner.invoke(cli.app, ["watch"])
    assert result.exit_code == 0
    assert capture.released
    assert json.loads(AppConfig.from_env().health_path.read_text())["status"] == "down"
