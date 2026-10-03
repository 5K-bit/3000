"""Persist an image before acknowledging its local event or publishing a reference."""
from __future__ import annotations

import shutil
import uuid
from typing import Any, Callable

from three_thousand.core.camera import save_frame
from three_thousand.core.config import AppConfig
from three_thousand.storage.sqlite_store import SQLiteStore


def record_observation(
    config: AppConfig, store: SQLiteStore, frame, *, event_type: str,
    confidence: float, metadata: dict[str, Any] | None = None,
    min_free_mb: float = 100, saver: Callable = save_frame,
) -> dict[str, Any]:
    if shutil.disk_usage(config.data_dir).free < min_free_mb * 1024 * 1024:
        raise OSError("insufficient_disk_space")
    evidence_id = str(uuid.uuid4())
    path = saver(frame, config.snapshots_dir).resolve()
    details = dict(metadata or {})
    details.update({"camera_id": config.camera_id, "evidence_id": evidence_id, "evidence_ref": path.as_uri()})
    try:
        local_id = store.add_event(
            event_type=event_type, confidence=confidence,
            snapshot_path=str(path), metadata=details,
        )
    except Exception:
        # No acknowledged event should point at a failed database transaction.
        path.unlink(missing_ok=True)
        raise
    return {
        "camera_id": config.camera_id, "local_event_id": local_id,
        "evidence_id": evidence_id, "evidence_ref": path.as_uri(),
        "confidence": confidence, "snapshot_path": str(path), "metadata": details,
    }
