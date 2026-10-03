# Bounded OBEOS event delivery

Operational publication uses a local SQLite queue and a single background sender. Configure `OBEOS_EVENT_URL` with the existing OBEOS canonical event endpoint. `OBEOS_DELIVERY_DB` can override the component's default queue path. With no endpoint, delivery is disabled and the component remains standalone.

An accepted enqueue means durable local acceptance, not completed remote delivery. The queue retains the same canonical event ID across retries and restart. It holds at most 1,000 envelopes, each at most 64 KiB; saturation rejects new messages and increments a visible counter. Exponential retry is bounded. Startup resumes pending delivery before a new event is produced. Shutdown has a bounded grace period and leaves undelivered rows for the next start.

The component's status or health response exposes pending count, errors and rejected events. Remote OBEOS ingestion deduplicates envelopes and commits an event-store outbox before dispatching to its consumer queue. Spatial providers publish coalesced batches, not animation frames.

The small transport implementation is intentionally vendored in both 3000 and Nightwatch so each repository remains independently installable. OBEOS's regression suite verifies these copies remain identical. A future shared package can replace this boundary without changing canonical envelopes.

## Receiver compatibility and evidence

Use the `/events/v1/publish` endpoint from OBEOS's integration-stabilization branch (PR #7). The legacy `/events/publish` endpoint on the audited main revision is not an interchangeable receiver. Configure the full endpoint explicitly; the child does not discover, expose or launch a receiver.

M1 adds `evidence_id`, `evidence_ref` (a host-local file URI), `local_event_id` and stable `camera_id` inside the payload. `correlation_id` is the evidence ID. Media bytes stay on the capture host. A successful HTTP delivery does not prove another machine can retrieve that evidence; authenticated remote serving is a later milestone.

`3000 health --json` reads the watcher's atomic heartbeat without starting another camera or sender. It contains the live watcher's last delivery status and rejected-enqueue count. A new `3000 status` process only probes the device; it cannot report another process's in-memory counters. Stopped, missing or stale heartbeat is never healthy. Snapshot-only runs record local events but do not claim an active watcher heartbeat.

The local event ledger and transport queue remain separate transactions. The ledger survives enqueue rejection, but recovery of a rejected enqueue is operator work; there is no automatic ledger-to-outbox replay yet. The outbox itself retries accepted rows across restart with unchanged event IDs.
