import json
from datetime import datetime, timedelta, timezone

from typer.testing import CliRunner

from three_thousand.cli import app
from three_thousand.core.config import AppConfig
from three_thousand.core.health import health_record, read_health, write_health


def test_health_missing_is_unknown_and_does_not_create_data(tmp_path):
    path = tmp_path / "missing" / "health.json"
    assert read_health(path)["status"] == "unknown"
    assert not path.parent.exists()


def test_stale_health_never_reports_healthy(tmp_path):
    path = tmp_path / "health.json"
    record = health_record("ok", details={"runtime_state": "watching"})
    record["checked_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    write_health(path, record)
    assert read_health(path)["status"] == "down"
    assert "runtime_heartbeat_stale" in read_health(path)["warnings"]


def test_health_cli_emits_json_without_camera_access(monkeypatch):
    from three_thousand import cli
    monkeypatch.setattr(cli, "is_camera_available", lambda _: (_ for _ in ()).throw(AssertionError()))
    path = AppConfig.from_env().health_path
    write_health(path, health_record("ok", details={"camera_id": "test-camera"}))
    result = CliRunner().invoke(app, ["health", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "ok"
    assert len(list(path.parent.iterdir())) == 1


def test_corrupt_health_cli_is_structured_failure():
    path = AppConfig.from_env().health_path
    path.parent.mkdir(parents=True)
    path.write_text('{"status": "ok"}')
    result = CliRunner().invoke(app, ["health", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["status"] == "unknown"
