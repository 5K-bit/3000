from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


def publish_event(event_type: str, payload: dict[str, Any]) -> bool:
    endpoint = os.getenv("OBEOS_EVENT_URL", "").strip()
    if not endpoint:
        return False
    envelope = {
        "contract_version": "1.0",
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "source": "project3000",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "correlation_id": None,
        "parent_event_id": None,
        "payload": payload,
    }
    req = Request(
        endpoint,
        data=json.dumps(envelope, default=str).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=1.5) as response:
            return 200 <= int(response.status) < 300
    except (OSError, URLError, ValueError):
        return False


_delivery = None
_delivery_error = None
_delivery_lock = __import__("threading").Lock()


def start_delivery():
    """Resume a configured durable queue even before another event is produced."""
    global _delivery, _delivery_error
    endpoint = os.getenv("OBEOS_EVENT_URL", "").strip()
    if not endpoint:
        return False
    with _delivery_lock:
        if _delivery is None:
            from pathlib import Path
            from .background_delivery import BackgroundDelivery

            path = Path(
                os.getenv(
                    "OBEOS_DELIVERY_DB",
                    str(Path.home() / ".project3000" / "event-delivery.sqlite3"),
                )
            )
            try:
                _delivery = BackgroundDelivery(path)
                _delivery_error = None
            except (OSError, __import__("sqlite3").Error) as exc:
                _delivery_error = type(exc).__name__
                return None
            import atexit

            atexit.register(shutdown_delivery)
    return _delivery


def enqueue_event(
    event_type: str, payload: dict[str, Any], *, correlation_id=None
) -> bool:
    """True means durably queued, not already received by OBEOS."""
    delivery = start_delivery()
    if not delivery:
        return False
    endpoint = os.getenv("OBEOS_EVENT_URL", "").strip()
    return delivery.enqueue(
        endpoint,
        {
            "contract_version": "1.0",
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "source": "project3000",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "correlation_id": correlation_id,
            "parent_event_id": None,
            "payload": payload,
        },
    )


def delivery_status():
    return (
        _delivery.status()
        if _delivery
        else {
            "state": "offline" if _delivery_error else "disabled",
            "pending": 0,
            "last_error": _delivery_error,
        }
    )


def shutdown_delivery():
    global _delivery
    with _delivery_lock:
        if _delivery is not None:
            _delivery.close()
            _delivery = None
