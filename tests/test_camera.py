import numpy as np

from three_thousand.core import camera


class FakeCapture:
    def __init__(self, opened: bool, frame_ok: bool = True) -> None:
        self._opened = opened
        self._frame_ok = frame_ok
        self.released = False

    def isOpened(self) -> bool:  # noqa: N802
        return self._opened

    def read(self):
        if not self._frame_ok:
            return False, None
        return True, np.zeros((10, 10, 3), dtype=np.uint8)

    def release(self) -> None:
        self.released = True


def test_camera_availability_uses_capture(monkeypatch) -> None:
    monkeypatch.setattr(camera.cv2, "VideoCapture", lambda _idx: FakeCapture(opened=True))
    assert camera.is_camera_available(0) is True


def test_capture_frame_returns_none_when_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(camera.cv2, "VideoCapture", lambda _idx: FakeCapture(opened=False))
    assert camera.capture_frame(0) is None


def test_network_capture_requests_backend_timeouts(monkeypatch):
    calls = []
    monkeypatch.setattr(camera.cv2, "VideoCapture", lambda *args: calls.append(args))
    camera.open_capture("rtsp://camera/live")
    assert calls[0][1] == camera.cv2.CAP_FFMPEG
    assert calls[0][2] == [camera.cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000, camera.cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000]


def test_failed_image_write_leaves_no_partial_evidence(tmp_path, monkeypatch):
    import pytest
    def fail(path, frame):
        from pathlib import Path
        Path(path).write_bytes(b"partial")
        return False
    monkeypatch.setattr(camera.cv2, "imwrite", fail)
    with pytest.raises(RuntimeError):
        camera.save_frame(np.zeros((10, 10, 3), dtype=np.uint8), tmp_path)
    assert not list(tmp_path.iterdir())
