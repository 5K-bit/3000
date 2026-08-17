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
    req = Request(endpoint, data=json.dumps(envelope, default=str).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=1.5) as response:
            return 200 <= int(response.status) < 300
    except (OSError, URLError, ValueError):
        return False
