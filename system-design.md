# Clinic Booking System — Design Document

**Author:** Fredrick Karuri
**Date:** 2026-07-10
**Status:** Draft
**Stack:** FastAPI, PostgreSQL, SQLAlchemy 2.0 (async), Alembic, pytest, GitHub Actions, Railway

---

## Problem Statement

A small clinic with 5 doctors currently books appointments manually. Patients need a
self-service way to see a doctor's free slots on a given day, book one, and cancel or
reschedule later. Once a slot is booked it must be unavailable to everyone else — including
under concurrent requests, which is the primary failure mode manual/naive implementations
hit. The clinic wants to start small but grow, so the design should not paint the system into
a corner (e.g. assuming a single clinic location, or a fixed doctor count).

---

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
- Recurring/series appointments.
- Multi-timezone patient-facing display (server stores and returns UTC; timezone conversion
  is a frontend concern, out of scope for this API).

---

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

### Key Design Decisions

| Decision | Option Chosen | Reason | Alternatives Rejected |
|---|---|---|---|
| Slot representation | Computed on the fly from working hours + fixed 30-min grid | No sync problem if working hours change; fewer rows; availability is always derived from ground truth (appointments table) | A materialized `Slot` table — rejected: needs regeneration logic whenever working hours change, and adds a second source of truth to keep consistent with `Appointment` |
| Concurrency control | DB partial unique constraint on `(doctor_id, slot_time)` WHERE `cancelled = false`, plus `SELECT ... FOR UPDATE` inside a transaction on the booking path | Constraint is the actual source of truth — correct even if application code has a bug. Row lock avoids a wasted round trip on the common case (slot already taken) before hitting the constraint | Check-then-insert with no lock/constraint — this is the exact race condition pattern that causes double-booking; relying on optimistic retry alone — adds complexity without being more correct than a DB constraint |
| Cancellation semantics | Soft delete (`cancelled_at`, `cancellation_reason` fields) rather than row deletion | Preserves audit history/trail, which a clinic will want (disputes, no-show tracking, growth into reporting) | Hard delete — rejected: loses history, complicates "prevent double-cancel" validation |
| Reschedule | Single atomic transaction: validate new slot, mark old appointment cancelled with reason `"rescheduled"`, create new appointment row, all inside one DB transaction with row locking on the target slot | Prevents "lose the original slot, then fail to get the new one" — the two operations must succeed or fail together | Two separate API calls (cancel then book) — rejected: not atomic, exposes exactly the partial-failure window the reviewer notes call out |
| Timezone handling | All datetimes stored and compared in UTC (`TIMESTAMPTZ` in Postgres) | Avoids DST/local-time ambiguity in slot comparisons; single clinic today, multi-location tomorrow will each have their own local time regardless | Storing naive local time — rejected: ambiguous under DST, breaks the moment the clinic has doctors in more than one timezone |
| Auth | Minimal bearer-token auth; a patient can only book/cancel/reschedule appointments tied to their own `patient_id`, extracted from the token, never trusted from the request body | Directly closes the "book on behalf of anyone" hole called out as critical in similar systems, with minimal scope added | Full OAuth2/identity provider — out of scope for a 3–5 day exercise; noted as a real gap for production |
| Framework | FastAPI, async SQLAlchemy 2.0 | Async fits a booking API's I/O-bound profile; Pydantic gives strong request/response validation and clean 422 error bodies for free; explicit control over locking/transactions (no ORM magic hiding the concurrency-critical path) | Django REST Framework — also viable, but FastAPI keeps the concurrency-critical code path more explicit for this exercise |

---

## Architecture / Component Overview

```
app/
├── main.py                  # FastAPI app instantiation, router registration
├── core/
│   ├── config.py             # Settings (env-driven: DB URL, etc.)
│   └── database.py           # Async engine/session setup
├── models/
│   ├── doctor.py              # Doctor ORM model
│   └── appointment.py         # Appointment ORM model
├── schemas/
│   ├── doctor.py              # Pydantic request/response schemas
│   └── appointment.py
├── services/
│   ├── availability.py        # Slot computation logic (pure, testable)
│   └── booking.py             # Booking/cancel/reschedule transactional logic
├── api/
│   ├── deps.py                 # Auth dependency, DB session dependency
│   └── routes/
│       ├── doctors.py           # GET /doctors/{id}/availability
│       └── appointments.py      # POST/PATCH appointment endpoints
├── tests/
│   ├── test_availability.py
│   ├── test_booking.py
│   └── test_concurrency.py     # Explicit concurrent-request test for the race condition
└── alembic/                    # DB migrations
```

The availability/slot-computation logic is deliberately isolated in `services/availability.py`
as a pure function of (working hours, existing appointments, target date) so it can be unit
tested without spinning up the DB or the API layer.

---

## Data Model

**Doctor**
| Field | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| full_name | str | |
| work_start | time | e.g. 09:00 |
| work_end | time | e.g. 17:00 |
| created_at | timestamptz | |

*(Deliberately no `email`/`phone` exposed via any patient-facing endpoint — internal-only
fields if added later.)*

**Appointment**
| Field | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| doctor_id | UUID (FK → Doctor) | |
| patient_id | UUID | taken from auth context, never from request body |
| slot_time | timestamptz | start of the 30-min slot, UTC |
| status | enum: `booked` \| `cancelled` | |
| cancellation_reason | str, nullable | required when status = cancelled |
| created_at | timestamptz | |
| updated_at | timestamptz | |

**DB constraint:** partial unique index on `(doctor_id, slot_time) WHERE status = 'booked'`.

---

## API / Interface Contracts

- `POST /appointments` — body: `{doctor_id, slot_time}` (patient_id from auth token). Validates:
  within working hours, on the 30-min grid, not in the past, not within 1hr of now (bonus),
  not already booked. Returns `201` with the appointment, or `400/409/422` with a specific
  error message.
- `GET /doctors/{id}/availability?date=YYYY-MM-DD` — returns list of free 30-min slot start
  times for that doctor on that date.
- `PATCH /appointments/{id}/cancel` — body: `{reason}`. Returns `409` if already cancelled.
- `PATCH /appointments/{id}/reschedule` — body: `{new_slot_time}`. Validates new slot exactly
  as a fresh booking would; atomic; returns `409` if the appointment is already cancelled or
  the new slot is taken.
- `GET /patients/{id}/appointments` (bonus) — upcoming appointments, sorted by `slot_time` ascending.

---

## Success Metrics

- Zero double-bookings under a concurrent-load test (N simultaneous requests for the same slot
  → exactly one `201`, the rest `409`).
- All required endpoints pass their spec'd validation cases.
- CI blocks merge on test failure; merge to `main` deploys automatically and the deployed URL
  reflects the merged code within the pipeline's run time.

---

## Risks & Open Questions

| Risk / Question | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Working hours change after appointments already booked outside new hours | Medium | Medium | Out of scope for this iteration; noted as a real gap — a production system would need a migration/notification flow, not silent invalidation |
| High concurrent load beyond a single doctor's slot (thundering herd on popular days) | Low, given clinic size | Low | Row-level locking scoped to a single `(doctor_id, slot_time)` row keeps contention narrow; revisit if patient volume grows significantly |
| Clock skew between app server and DB when checking "not in the past" | Low | Medium | All "now" comparisons done via DB server time (`NOW()`), not app server time |

---

## Out of Scope (Parking Lot)

- Doctor-cancels-entire-day bulk operation (would cascade-cancel affected appointments with
  patient notification — needs a notification system first).
- Multi-clinic/multi-location support (data model already keyed to allow it later via a
  `Clinic` entity, but not built now).
- Waitlists for fully-booked days.