from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import uuid

import cv2
import numpy as np


def _utc_suffix() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def open_capture(source: int | str):
    if isinstance(source, int):
        return cv2.VideoCapture(source)
    # Request bounded network IO; fail visibly if FFmpeg is unavailable.
    return cv2.VideoCapture(source, cv2.CAP_FFMPEG, [
        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000,
        cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000,
    ])


def is_camera_available(camera_index: int | str = 0) -> bool:
    try:
        capture = open_capture(camera_index)
    except Exception:
        return False

    try:
        if not capture or not capture.isOpened():
            return False
        ok, _ = capture.read()
        return bool(ok)
    except Exception:
        return False
    finally:
        if capture:
            capture.release()


def capture_frame(camera_index: int | str = 0) -> np.ndarray | None:
    try:
        capture = open_capture(camera_index)
    except Exception:
        return None

    try:
        if not capture or not capture.isOpened():
            return None
        ok, frame = capture.read()
        if not ok:
            return None
        return frame
    except Exception:
        return None
    finally:
        if capture:
            capture.release()


def save_frame(frame: np.ndarray, snapshots_dir: Path) -> Path:
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshots_dir / f"{_utc_suffix()}_{uuid.uuid4().hex}.jpg"
    temporary = snapshot_path.with_name(f".{snapshot_path.stem}.tmp.jpg")
    try:
        if not cv2.imwrite(str(temporary), frame):
            raise RuntimeError("Failed to write snapshot image to disk.")
        temporary.replace(snapshot_path)
        return snapshot_path
    finally:
        temporary.unlink(missing_ok=True)
