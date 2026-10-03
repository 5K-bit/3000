import pytest


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch, tmp_path):
    """Tests must never use operator cameras, persistent data or configured receivers."""
    from three_thousand import obeos_events
    obeos_events.shutdown_delivery()
    monkeypatch.delenv("OBEOS_EVENT_URL", raising=False)
    monkeypatch.setenv("OBEOS_DELIVERY_DB", str(tmp_path / "delivery.sqlite3"))
    monkeypatch.setenv("PROJECT3000_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PROJECT3000_CAMERA_SOURCE", "0")
    monkeypatch.setenv("PROJECT3000_CAMERA_ID", "test-camera")
    yield
    obeos_events.shutdown_delivery()
