# Bounded OBEOS event delivery

Operational publication uses a local SQLite queue and a single background sender. Configure `OBEOS_EVENT_URL` with the existing OBEOS canonical event endpoint. `OBEOS_DELIVERY_DB` can override the component's default queue path. With no endpoint, delivery is disabled and the component remains standalone.

An accepted enqueue means durable local acceptance, not completed remote delivery. The queue retains the same canonical event ID across retries and restart. It holds at most 1,000 envelopes, each at most 64 KiB; saturation rejects new messages and increments a visible counter. Exponential retry is bounded. Startup resumes pending delivery before a new event is produced. Shutdown has a bounded grace period and leaves undelivered rows for the next start.

The component's status or health response exposes pending count, errors and rejected events. Remote OBEOS ingestion deduplicates envelopes and commits an event-store outbox before dispatching to its consumer queue. Spatial providers publish coalesced batches, not animation frames.

The small transport implementation is intentionally vendored in both 3000 and Nightwatch so each repository remains independently installable. OBEOS's regression suite verifies these copies remain identical. A future shared package can replace this boundary without changing canonical envelopes.
