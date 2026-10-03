"""Persist observable runtime health without acquiring a second camera handle."""
from __future__ import annotations

import json
import os
import socket
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from three_thousand import __version__
from three_thousand.core.events import utc_timestamp


def health_record(status: str, *, details: dict[str, Any], warnings=()) -> dict[str, Any]:
    return {
        "contract_version": "1.0", "name": "3000", "version": __version__,
        "status": status, "node": socket.gethostname(), "checked_at": utc_timestamp(),
        "dependencies": {}, "warnings": list(warnings), "details": details,
    }


def write_health(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(record), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_health(path: Path, *, stale_seconds: float = 30) -> dict[str, Any]:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(record, dict) or record.get("status") not in {"ok", "degraded", "down", "unknown"}:
            raise ValueError("invalid health record")
        if not isinstance(record.get("details"), dict) or not isinstance(record.get("warnings"), list):
            raise ValueError("invalid health record")
        checked_at = datetime.fromisoformat(record["checked_at"])
        age = (datetime.now(timezone.utc) - checked_at).total_seconds()
        if age < -5 or age > stale_seconds:
            record["status"] = "down"
            record["warnings"].append("runtime_heartbeat_stale")
        record["details"]["heartbeat_age_seconds"] = round(age, 3)
        return record
    except FileNotFoundError:
        return health_record("unknown", details={}, warnings=["runtime_not_started"])
    except (OSError, ValueError, TypeError, KeyError):
        return health_record("unknown", details={}, warnings=["runtime_health_unreadable"])
