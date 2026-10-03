from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


def parse_source(value: str) -> int | str:
    value = value.strip()
    if value.isdecimal():
        return int(value)
    try:
        parsed = urlsplit(value)
        if parsed.scheme in {"rtsp", "rtsps", "http", "https"} and parsed.hostname:
            return value
    except ValueError:
        pass
    # Never echo the source: it may contain credentials.
    raise ValueError("Camera source must be a non-negative index or RTSP/HTTP(S) URL.")


@dataclass(slots=True)
class AppConfig:
    data_dir: Path = Path("data")
    snapshots_subdir: str = "snapshots"
    database_name: str = "events.sqlite3"
    camera_index: int | str = 0
    camera_id: str = "camera-0"
    motion_area_threshold: float = 0.02

    @classmethod
    def from_env(cls) -> AppConfig:
        camera_id = os.getenv("PROJECT3000_CAMERA_ID", "camera-0")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", camera_id):
            raise ValueError("Camera ID must be 1–64 letters, numbers, dots, underscores or hyphens.")
        return cls(
            data_dir=Path(os.getenv("PROJECT3000_DATA_DIR", "data")).expanduser().resolve(),
            camera_index=parse_source(os.getenv("PROJECT3000_CAMERA_SOURCE", "0")),
            camera_id=camera_id,
        )

    @property
    def snapshots_dir(self) -> Path:
        return self.data_dir / self.snapshots_subdir

    @property
    def database_path(self) -> Path:
        return self.data_dir / self.database_name

    @property
    def health_path(self) -> Path:
        return self.data_dir / "runtime-health.json"

    def ensure_paths(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
