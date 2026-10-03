"""Transport tests use only loopback or injected senders; no running OBEOS required."""
import json
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from three_thousand import obeos_events
from three_thousand.background_delivery import BackgroundDelivery


def envelope(ident="stable-id"):
    return {"contract_version": "1.0", "event_id": ident,
            "event_type": "project3000.motion.detected", "source": "project3000",
            "timestamp": "2026-10-03T12:00:00+00:00", "correlation_id": "evidence-id",
            "parent_event_id": None, "payload": {"evidence_ref": "file:///data/snapshot.jpg"}}


def test_failed_delivery_survives_restart_with_same_event_id(tmp_path):
    path = tmp_path / "outbox.sqlite3"
    attempted = threading.Event()
    def unavailable(endpoint, payload):
        attempted.set()
        raise OSError("receiver offline")
    first = BackgroundDelivery(path, sender=unavailable)
    try:
        assert first.enqueue("http://127.0.0.1:9/events/v1/publish", envelope())
        assert attempted.wait(3)
    finally:
        first.close(timeout=0)
    with sqlite3.connect(path) as db:
        saved = json.loads(db.execute("SELECT payload FROM delivery").fetchone()[0])
        assert saved["event_id"] == "stable-id"
    received = threading.Event()
    delivered = []
    def restored(endpoint, payload):
        delivered.append(json.loads(payload))
        received.set()
    second = BackgroundDelivery(path, sender=restored)
    try:
        assert received.wait(4), "Restart must resume backlog without a new enqueue"
    finally:
        second.close()
    assert delivered == [saved]
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM delivery").fetchone()[0] == 0


def test_queue_capacity_and_payload_limits_are_visible(tmp_path):
    def offline(*args):
        raise OSError("offline")
    queue = BackgroundDelivery(tmp_path / "queue.sqlite3", capacity=1, sender=offline)
    try:
        assert queue.enqueue("http://127.0.0.1:9", envelope())
        assert not queue.enqueue("http://127.0.0.1:9", envelope("second"))
        oversized = envelope("large")
        oversized["payload"] = {"text": "x" * 65536}
        assert not queue.enqueue("http://127.0.0.1:9", oversized)
        assert queue.status()["pending"] == 1
        assert queue.status()["rejected"] == 2
    finally:
        queue.close(timeout=0)


def test_publisher_posts_canonical_reference_to_local_receiver(tmp_path, monkeypatch):
    received = threading.Event()
    captured = []
    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            captured.append((self.path, payload))
            self.send_response(201)
            self.end_headers()
            received.set()
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("OBEOS_EVENT_URL", f"http://127.0.0.1:{server.server_port}/events/v1/publish")
    try:
        assert obeos_events.enqueue_event("project3000.motion.detected", {
            "camera_id": "front-door", "local_event_id": 1,
            "evidence_id": "evidence-123", "evidence_ref": "file:///data/snapshot.jpg",
        }, correlation_id="evidence-123")
        assert received.wait(3)
        obeos_events.shutdown_delivery()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    path, event = captured[0]
    assert path == "/events/v1/publish"
    assert event["contract_version"] == "1.0"
    assert event["source"] == "project3000"
    assert event["event_type"] == "project3000.motion.detected"
    assert event["correlation_id"] == "evidence-123"
    assert event["payload"]["evidence_ref"] == "file:///data/snapshot.jpg"
    assert set(event) == {"contract_version", "event_id", "event_type", "source", "timestamp", "correlation_id", "parent_event_id", "payload"}


def test_unconfigured_delivery_is_local_only():
    assert not obeos_events.enqueue_event("project3000.motion.detected", {})
    assert obeos_events.delivery_status()["state"] == "disabled"
