# Observability

Structured JSON logging (stdlib `logging` + a custom formatter, no new dependency) to stdout —
the format most log aggregators parse natively without extra config on their end.

## What's Instrumented

- **Request-level:** every request gets a `request_id` (returned via the `X-Request-ID`
  response header, for correlating a client-reported issue back to a specific log line) and one
  `request_handled` log line with `method`, `path`, `status_code`, `duration_ms`. Auto-leveled:
  INFO for 2xx/3xx, WARNING for 4xx, ERROR for 5xx.
- **Business events:** `appointment_booked`, `booking_conflict`, `appointment_cancelled`,
  `appointment_rescheduled`, `reschedule_conflict` — logged from `services/booking.py` with the
  relevant IDs, since these are the events someone debugging a "why didn't my booking go
  through" report actually needs.
- **Auth failures:** logged at WARNING (`auth_token_malformed`, `auth_signature_invalid`) —
  deliberately never logs the token or signature itself, only the claimed `patient_id` where
  available, so log access doesn't become a second attack surface.
- `LOG_LEVEL` env var controls verbosity (default `INFO`); `sqlalchemy.engine`'s per-statement
  logging is suppressed unless `LOG_LEVEL=DEBUG`, since it's extremely noisy otherwise.


## What's Deliberately Not Here (Yet), and What I'd Add First

- **Error tracking (e.g. Sentry).** Right now a 500 produces a log line, not an alert. First
  thing I'd wire up — the gap between "an error happened" and "someone finds out" is the most
  costly one in a small system nobody's actively watching dashboards for.
- **Metrics/dashboards (e.g. Prometheus + Grafana, or a hosted equivalent).** The `duration_ms`
  field on every request log is a start, but it's not queryable as a p50/p95/p99 without an
  actual metrics backend. For a booking system specifically, I'd also want a business metric —
  booking conflict rate over time — since a sudden spike in `booking_conflict` logs is a much
  earlier signal of a popular-doctor/hot-slot problem than anyone noticing complaints.
- **Distributed tracing.** Not relevant yet at one service + one database, but the `request_id`
  already threaded through every log line is the seam a real tracing header (`traceparent`)
  would slot into if this grows into multiple services.
- **Log-based alerting on the auth-failure logs.** A burst of `auth_signature_invalid` for
  different claimed `patient_id` values in a short window is a credential-stuffing signal worth
  paging on; right now it's only visible if someone goes looking.