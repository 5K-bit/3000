import json

import cv2
import numpy as np
import pytest
from typer.testing import CliRunner

from three_thousand import cli
from three_thousand.core.camera import parse_source

runner = CliRunner()


@pytest.fixture
def motion_video(tmp_path):
    """Static scene, then a bright block moves across it."""
    path = tmp_path / "clip.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (160, 120))
    if not writer.isOpened():
        pytest.skip("no video writer available")
    for i in range(30):
        frame = np.zeros((120, 160, 3), dtype=np.uint8)
        if i >= 10:
            x = (i - 10) * 6
            frame[30:90, x : x + 50] = 255
        writer.write(frame)
    writer.release()
    return path


@pytest.fixture(autouse=True)
def isolated_cwd(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)


def test_parse_source() -> None:
    assert parse_source("0") == 0
    assert parse_source("clip.avi") == "clip.avi"


def test_watch_video_records_events_with_cooldown(motion_video) -> None:
    result = runner.invoke(
        cli.app,
        ["watch", "--source", str(motion_video), "--interval-seconds", "0", "--cooldown-seconds", "60"],
    )
    assert result.exit_code == 0, result.stdout
    assert "Motion detected" in result.stdout
    listed = runner.invoke(cli.app, ["events", "--json"])
    rows = [json.loads(line) for line in listed.stdout.splitlines()]
    assert len(rows) == 1  # cooldown collapses the burst into one event
    assert rows[0]["event_type"] == "motion_detected"


def test_watch_without_cooldown_records_more(motion_video) -> None:
    runner.invoke(cli.app, ["watch", "--source", str(motion_video), "--interval-seconds", "0", "--cooldown-seconds", "0"])
    rows = runner.invoke(cli.app, ["events", "--json"]).stdout.splitlines()
    assert len(rows) > 1


def test_snapshot_from_video_records_event(motion_video) -> None:
    result = runner.invoke(cli.app, ["snapshot", "--source", str(motion_video)])
    assert result.exit_code == 0, result.stdout
    rows = [json.loads(l) for l in runner.invoke(cli.app, ["events", "--json"]).stdout.splitlines()]
    assert rows[0]["event_type"] == "snapshot_created"


def test_status_exit_codes(motion_video) -> None:
    assert runner.invoke(cli.app, ["status", "--source", str(motion_video)]).exit_code == 0
    assert runner.invoke(cli.app, ["status", "--source", "missing.avi"]).exit_code == 1


def test_watch_missing_source_fails_cleanly() -> None:
    result = runner.invoke(cli.app, ["watch", "--source", "missing.avi"])
    assert result.exit_code == 1
