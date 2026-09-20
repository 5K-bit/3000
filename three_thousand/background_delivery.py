"""Bounded durable background delivery. Kept identical across standalone component adapters."""

from __future__ import annotations
import json
from pathlib import Path
import sqlite3
import threading
import time
from urllib.request import Request, urlopen


class BackgroundDelivery:
    def __init__(self, path: Path, *, capacity=1000, sender=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.capacity = capacity
        self.sender = sender or self._send
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._con = sqlite3.connect(str(path), check_same_thread=False, timeout=0.05)
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.execute(
            "CREATE TABLE IF NOT EXISTS delivery(id TEXT PRIMARY KEY,endpoint TEXT,payload TEXT,attempts INTEGER DEFAULT 0,next REAL DEFAULT 0,error TEXT)"
        )
        self._con.commit()
        self.rejected = 0
        self.last_error = None
        self._thread = threading.Thread(
            target=self._run, name="obeos-event-delivery", daemon=True
        )
        self._thread.start()

    def enqueue(self, endpoint, envelope):
        if self._stop.is_set():
            return False
        payload = json.dumps(envelope, separators=(",", ":"), default=str)
        if len(payload.encode()) > 65536:
            self.rejected += 1
            self.last_error = "payload_too_large"
            return False
        try:
            with self._lock, self._con:
                if (
                    self._stop.is_set()
                    or self._con.execute("SELECT COUNT(*) FROM delivery").fetchone()[0]
                    >= self.capacity
                ):
                    self.rejected += 1
                    self.last_error = "queue_full"
                    return False
                self._con.execute(
                    "INSERT OR IGNORE INTO delivery(id,endpoint,payload) VALUES(?,?,?)",
                    (envelope["event_id"], endpoint, payload),
                )
        except sqlite3.Error as exc:
            self.rejected += 1
            self.last_error = type(exc).__name__
            return False
        self._wake.set()
        return True

    @staticmethod
    def _send(endpoint, payload):
        request = Request(
            endpoint,
            data=payload.encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=1.5) as response:
            if not 200 <= response.status < 300:
                raise OSError("delivery_rejected")

    def _run(self):
        try:
            while not self._stop.is_set():
                with self._lock:
                    row = self._con.execute(
                        "SELECT id,endpoint,payload,attempts FROM delivery WHERE next<=? ORDER BY rowid LIMIT 1",
                        (time.time(),),
                    ).fetchone()
                if not row:
                    self._wake.wait(0.5)
                    self._wake.clear()
                    continue
                ident, endpoint, payload, attempts = row
                try:
                    self.sender(endpoint, payload)
                    with self._lock, self._con:
                        self._con.execute("DELETE FROM delivery WHERE id=?", (ident,))
                    self.last_error = None
                except Exception as exc:
                    self.last_error = type(exc).__name__
                    with self._lock, self._con:
                        self._con.execute(
                            "UPDATE delivery SET attempts=?,next=?,error=? WHERE id=?",
                            (
                                attempts + 1,
                                time.time() + min(300, 2 ** min(attempts, 8)),
                                self.last_error,
                                ident,
                            ),
                        )
        except Exception as exc:
            self.last_error = type(exc).__name__
            self._stop.set()
        finally:
            with self._lock:
                self._con.close()

    def status(self):
        with self._lock:
            if self._stop.is_set() and not self._thread.is_alive():
                return {
                    "state": "offline" if self.last_error else "stopped",
                    "persistent_queue": str(self.path),
                    "rejected": self.rejected,
                    "last_error": self.last_error,
                }
            count = self._con.execute("SELECT COUNT(*) FROM delivery").fetchone()[0]
        return {
            "state": "degraded" if self.last_error else "online",
            "pending": count,
            "capacity": self.capacity,
            "rejected": self.rejected,
            "last_error": self.last_error,
        }

    def close(self, timeout=2):
        if self._stop.is_set():
            self._thread.join(timeout=2)
            return
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if self._stop.is_set():
                    break
                if not self._con.execute("SELECT 1 FROM delivery LIMIT 1").fetchone():
                    break
            self._wake.set()
            time.sleep(0.02)
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout=2)
