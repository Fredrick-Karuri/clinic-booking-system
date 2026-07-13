# Architecture & System Design

## Problem Statement

A small clinic with 5 doctors currently books appointments manually. Patients need a
self-service way to see a doctor's free slots on a given day, book one, and cancel or
reschedule later. Once a slot is booked it must be unavailable to everyone else — including
under concurrent requests, which is the primary failure mode manual/naive implementations
hit. The clinic wants to start small but grow, so the design should not paint the system into
a corner (e.g. assuming a single clinic location, or a fixed doctor count).

## Goals

- Patients can view a doctor's real, working-hours-aware availability for a given day.
- Booking a slot is race-safe: two simultaneous requests for the same slot cannot both succeed.
- Patients can cancel and reschedule; slot state stays consistent through both operations.
- Validation errors are meaningful and mapped to correct HTTP status codes.
- The system is structured so multi-location or multi-clinic growth doesn't require a rewrite.

## Non-Goals (Explicit Out of Scope)

- Full identity/auth system (OAuth, roles, MFA) — a minimal bearer-token auth model is used
  instead, enough to demonstrate that booking-on-behalf-of-others is prevented.
- Payments, insurance, or billing.
- SMS/email notifications and reminders.
- Doctor-side UI for setting working hours dynamically (working hours are seeded/admin-set,
  not user-editable via API in this iteration).
- Recurring/series appointments, waitlists, multi-clinic support (data model allows it later,
  not built now).
- Bulk "doctor cancels the whole day" operation.
- Multi-timezone patient-facing display (server stores and returns UTC; timezone conversion
  is a frontend concern, out of scope for this API).

## Proposed Solution

A REST API with two core entities — `Doctor` and `Appointment` — where "slots" are **not**
stored as rows. A slot is a derived concept: computed from a doctor's `work_start`/`work_end`
and a fixed 30-minute grid, then cross-referenced against existing non-cancelled appointments
for that doctor on that day. This keeps the data model small and avoids a slot-table
synchronization problem if working hours ever change.

The single hard invariant the whole system is built around is: **no two non-cancelled
appointments may exist for the same `(doctor_id, slot_time)`.** This is enforced at the
database level with a partial unique constraint, not just in application logic, because
application-level check-then-insert is inherently racy under concurrent load.

## Key Decisions

| Decision | Chosen | Rejected | Why |
|---|---|---|---|
| Slot representation | Computed on the fly from working hours + fixed 30-min grid | A materialized `Slot` table | No sync problem if working hours change; availability is always derived from the `appointments` table, the actual source of truth. A materialized table needs regeneration logic whenever working hours change, and adds a second source of truth to keep consistent |
| Concurrency control | DB partial unique index on `(doctor_id, slot_time) WHERE status='booked'`, plus `SELECT ... FOR UPDATE` for the common case | Check-then-insert with no lock/constraint; optimistic retry alone | The constraint is the real invariant — correct even if application logic has a bug. The row lock catches the common case (a slot someone already holds) before it ever reaches the DB constraint. Check-then-insert is the exact race condition pattern that causes double-booking |
| Cancellation | Soft delete (`status`, `cancellation_reason`) | Hard delete | Preserves history for audit/reporting, standard for a system expected to grow. Hard delete loses history and complicates "prevent double-cancel" validation |
| Reschedule | Single transaction: validate + lock new slot, only then cancel the old appointment and create the new one | Two separate API calls (cancel then book) | A failed reschedule must never lose the patient's original booking. Two separate calls aren't atomic and expose exactly the partial-failure window a reviewer would probe for |
| Timezone handling | All datetimes stored and compared in UTC (`TIMESTAMPTZ`) | Naive local time | Avoids DST ambiguity; correct today and if the clinic adds doctors in other timezones later. Naive local time is ambiguous under DST and breaks immediately with multiple timezones |
| Auth | Minimal bearer-token scheme: token → `patient_id`, never trusted from the request body | Full OAuth2/identity provider | Closes the "book on behalf of anyone" hole with minimal scope. Full OAuth is out of scope for a 3–5 day exercise; noted as a real gap for production — see Non-Goals |
| Framework | FastAPI, async SQLAlchemy 2.0 | Django REST Framework | Async fits a booking API's I/O-bound profile; Pydantic gives strong request/response validation and clean 422 error bodies for free; explicit control over locking/transactions rather than ORM magic hiding the concurrency-critical path |
| Layering | Repository pattern: `AppointmentRepository` (abstract) / `PostgresAppointmentRepository` (concrete), a thin `BookingService` for orchestration, `app/exceptions.py` for the error hierarchy | Business logic + persistence + exceptions in one `services/booking.py` file | Real single-responsibility, not just file-per-module: the service has no SQL/session handling, the repository has no business rules. Swapping the backing store means writing a new repository, not touching business logic |

## A Refactor Worth Documenting: Separating Concerns in the Booking Logic

The first working version of the booking logic lived in a single `services/booking.py`
combining the exception hierarchy, business validation, and persistence/locking mechanics —
it worked and was fully tested, but mixed three responsibilities that should be independently
testable and independently replaceable. Refactored into `app/exceptions.py` (business rules
only), `app/repositories/appointment/base.py` (an abstract interface defining the
atomicity + conflict-signaling contract any backing store must satisfy),
`app/repositories/appointment/postgres.py` (the Postgres implementation owning
`SELECT ... FOR UPDATE`, commit/rollback, `IntegrityError` translation), and
`app/services/booking.py`'s `BookingService` (zero SQL, zero session handling — only
validation and orchestration, injected with a repository via FastAPI's `Depends()`).

This is real Open/Closed, not aspirational: a new backend means implementing
`AppointmentRepository`, not touching `BookingService`. One honest caveat — the concurrency
guarantees this system depends on (row locking + a partial unique constraint) are fairly
Postgres-specific, so swapping databases wouldn't preserve those exact guarantees for free. The
separation is still worth it for readability and testability even where "swap the database" is
more theoretical than likely here.

## Architecture / Component Overview

```
app/
├── main.py                  # FastAPI app instantiation, router registration
├── core/
│   ├── config.py             # Settings (env-driven: DB URL, etc.)
│   ├── database.py           # Async engine/session setup
│   ├── logging_config.py     # Structured JSON logging (see docs/observability.md)
│   └── middleware.py         # Request-logging middleware
├── models/
│   ├── doctor.py              # Doctor ORM model
│   └── appointment.py         # Appointment ORM model
├── schemas/
│   ├── doctor.py              # Pydantic request/response schemas
│   └── appointment.py
├── exceptions.py              # Business-level exception hierarchy
├── repositories/
│   └── appointment/
│       ├── base.py             # Abstract AppointmentRepository contract
│       └── postgres.py         # Postgres implementation (locking, IntegrityError translation)
├── services/
│   ├── availability.py        # Slot computation logic (pure, testable)
│   └── booking.py             # BookingService — validation + orchestration only
├── api/
│   ├── deps.py                 # Auth dependency, DB session dependency
│   └── routes/
│       ├── doctors.py           # GET /doctors/{id}/availability
│       ├── appointments.py      # POST/PATCH appointment endpoints
│       └── patients.py          # GET /patients/{id}/appointments (bonus)
├── scripts/seed.py             # Sample doctor seeding
└── alembic/                    # DB migrations

tests/                          # See docs/testing.md
```

The availability/slot-computation logic is deliberately isolated in `services/availability.py`
as a pure function of (working hours, existing appointments, target date) so it can be unit
tested without spinning up the DB or the API layer.

## Data Model

**Doctor**

| Field | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| full_name | str | |
| work_start | time | e.g. 09:00 |
| work_end | time | e.g. 17:00 |
| created_at | timestamptz | |

Deliberately no `email`/`phone` exposed via any patient-facing endpoint.

**Appointment**

| Field | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| doctor_id | UUID (FK → Doctor, `ON DELETE CASCADE`) | |
| patient_id | UUID | taken from auth context, never from request body |
| slot_time | timestamptz | start of the 30-min slot, UTC |
| status | enum: `booked` \| `cancelled` | |
| cancellation_reason | str, nullable | required when status = cancelled |
| created_at | timestamptz | |
| updated_at | timestamptz | |

**DB constraint:** partial unique index `uq_doctor_slot_when_booked` on
`(doctor_id, slot_time) WHERE status = 'booked'`.

## A Concurrency Bug Found During Development

Worth documenting honestly: the first implementation of the booking transaction wrapped the
insert in a context manager that never actually issued a `COMMIT`. A concurrency test firing 10
simultaneous requests at the same slot showed **10 successes** — every request silently rolled
back and the next one slipped through serially, so the DB constraint never got a chance to do its
job. Fixed by making each service call own an explicit `commit()`/`rollback()`. Re-run with the
same 10-concurrent-request test: exactly 1 success, 9 conflicts, verified against a real Postgres
instance (not mocked). The same fix was needed in the reschedule path for the same reason.

## Risks & Open Questions

| Risk / Question | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Working hours change after appointments already booked outside new hours | Medium | Medium | Out of scope for this iteration; a production system would need a migration/notification flow, not silent invalidation |
| High concurrent load beyond a single doctor's slot (thundering herd on popular days) | Low, given clinic size | Low | Row-level locking scoped to a single `(doctor_id, slot_time)` row keeps contention narrow; revisit if patient volume grows significantly |
| Clock skew between app server and DB when checking "not in the past" | Low | Medium | All "now" comparisons done via DB server time (`NOW()`), not app server time |

## Out of Scope (Parking Lot)

- Doctor-cancels-entire-day bulk operation (would cascade-cancel affected appointments with
  patient notification — needs a notification system first).
- Multi-clinic/multi-location support (data model already keyed to allow it later via a
  `Clinic` entity, but not built now).
- Waitlists for fully-booked days.