# Clinic Booking API

A REST API for a small clinic (5 doctors) to let patients view availability, book, cancel, and
reschedule 30-minute appointment slots — built for the Savannah Informatics backend assessment.

**Stack:** FastAPI · PostgreSQL · SQLAlchemy 2.0 (async) · Alembic · pytest · GitHub Actions · Railway

- **Deployed URL:** `<fill in after Railway deploy — see Deployment section>`
- **Repository:** `<fill in your GitHub/GitLab URL>`

---

## Table of Contents

1. [System Design](#1-system-design)
2. [Running Locally](#2-running-locally)
3. [API Reference](#3-api-reference)
4. [Testing](#4-testing)
5. [CI/CD & Deployment](#5-cicd--deployment)
6. [AI Reflection](#6-ai-reflection)

---

## 1. System Design

### Problem

Patients need to see a doctor's free 30-minute slots on a given day, book one, and cancel or
reschedule later. Once booked, a slot must not be bookable by anyone else — including under
concurrent requests, which is the primary failure mode a naive implementation hits.

### Key Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| Slot representation | Computed on the fly from doctor working hours + a fixed 30-min grid, never stored | No sync problem if working hours change; availability is always derived from the `appointments` table, the actual source of truth |
| Concurrency control | DB partial unique index on `(doctor_id, slot_time) WHERE status='booked'`, plus `SELECT ... FOR UPDATE` for the common case | The constraint is the real invariant — correct even if application logic has a bug. The row lock catches the common case (a slot someone already holds) before it ever reaches the DB constraint |
| Cancellation | Soft delete (`status`, `cancellation_reason`) | Preserves history for audit/reporting, standard for a system expected to grow |
| Reschedule | Single transaction: validate + lock new slot, only then cancel the old appointment and create the new one | A failed reschedule must never lose the patient's original booking |
| Timezone handling | All datetimes stored and compared in UTC (`TIMESTAMPTZ`) | Avoids DST ambiguity; correct today and if the clinic adds doctors in other timezones later |
| Auth | Minimal bearer-token scheme: token → `patient_id`, never trusted from the request body | Closes the "book on behalf of anyone" hole with minimal scope. **Not** a full identity system — see Non-Goals |

### Data Model

**Doctor:** `id, full_name, work_start, work_end, created_at`. Deliberately no email/phone —
nothing PII-bearing is exposed on any patient-facing endpoint.

**Appointment:** `id, doctor_id, patient_id, slot_time, status (booked|cancelled),
cancellation_reason, created_at, updated_at`, with the partial unique index described above.

### Non-Goals (explicit, out of scope for this exercise)

- Full identity/auth system (OAuth, roles, sessions) — a minimal token scheme stands in
- Payments, insurance, notifications/reminders
- Doctor-editable working hours via API (seeded/admin-set only)
- Recurring appointments, waitlists, multi-clinic support (data model allows it later, not built now)
- Bulk "doctor cancels the whole day" operation

### A Concurrency Bug Found During Development

Worth documenting honestly: the first implementation of the booking transaction wrapped the
insert in a context manager that never actually issued a `COMMIT`. A concurrency test firing 10
simultaneous requests at the same slot showed **10 successes** — every request silently rolled
back and the next one slipped through serially, so the DB constraint never got a chance to do its
job. Fixed by making each service call own an explicit `commit()`/`rollback()`. Re-run with the
same 10-concurrent-request test: exactly 1 success, 9 conflicts, verified against a real Postgres
instance (not mocked). The same fix was needed in the reschedule path for the same reason.

---

## 2. Running Locally

### Option A — Docker Compose (recommended)

```bash
cp .env.example .env
make up          # builds the app image, starts Postgres + the API
make migrate      # in a second terminal, once the DB is healthy
make seed
```

API will be at `http://localhost:8000`, docs at `http://localhost:8000/docs`.

> **Note:** Docker itself could not be executed in the environment this was built in, so
> `make up` has not been run end-to-end against a live Docker daemon. The Dockerfile and
> `docker-compose.yml` follow the standard pattern and were reviewed for correctness, but please
> run `make up` once yourself to confirm before relying on it — flagging this rather than
> claiming untested things work.

### Option B — Local Python + local Postgres

```bash
python3 -m venv .venv && source .venv/bin/activate
make install                      # installs requirements.txt
cp .env.example .env              # edit DATABASE_URL to point at your local Postgres
make migrate
make seed
make run                          # http://localhost:8000
```

This path **was** run and verified end-to-end multiple times during development, including
against a from-scratch virtualenv built strictly from `requirements.txt` (see Testing below).

### Auth for local testing

There's no registration endpoint (out of scope). To get a valid bearer token for a given
`patient_id`, issue one with the same signing scheme the API uses:

```python
from app.api.deps import issue_token
import uuid
print(issue_token(uuid.uuid4()))
```

---

## 3. API Reference

| Method | Path | Description | Auth |
|---|---|---|---|
| GET | `/health` | Liveness check | none |
| GET | `/doctors/{id}/availability?date=YYYY-MM-DD` | Free 30-min slots for a doctor on a date | none |
| POST | `/appointments` | Book a slot. Body: `{doctor_id, slot_time}` | bearer token |
| PATCH | `/appointments/{id}/cancel` | Cancel. Body: `{reason}` | bearer token, owner only |
| PATCH | `/appointments/{id}/reschedule` | Move to a new slot. Body: `{new_slot_time}` | bearer token, owner only |
| GET | `/patients/{id}/appointments` | Upcoming appointments, sorted ascending (bonus) | bearer token, owner only |

Status codes: `201` created, `200` success, `400` validation failure, `401` missing/invalid
token, `403` not the resource owner, `404` doctor/appointment not found, `409` slot conflict or
already-cancelled, `422` malformed request.

Interactive docs at `/docs` (Swagger UI) once running.

---

## 4. Testing

```bash
make test
```

**51/51 tests passing, 98% coverage** on `app/` (measured with `concurrency = greenlet` in
`.coveragerc` — SQLAlchemy's async extension uses greenlet-based context switching that
coverage.py's default tracer doesn't follow, which under-reported route-level coverage by ~40
points before this was configured correctly).

Everything runs against a **real Postgres instance**, not SQLite or mocks — the concurrency
guarantees under test (`SELECT ... FOR UPDATE`, the partial unique constraint) are Postgres-
specific behavior a lighter-weight substitute can't faithfully reproduce.

Two tests matter most:

- `test_concurrent_booking_same_slot_only_one_succeeds` — 10 simultaneous booking requests at
  the same slot, exactly 1 succeeds.
- `test_concurrent_reschedule_same_new_slot_only_one_succeeds` — two patients reschedule into
  the same new slot simultaneously; exactly 1 succeeds, the loser's original appointment is
  confirmed still intact.

The remaining 2% of uncovered lines are documented in the coverage run, not silently ignored:
two branches unreachable via the API (the doctor-FK has `ondelete=CASCADE`, so an appointment
can never point at a deleted doctor), one concurrency backstop not worth force-triggering
deterministically, and two cosmetic `__repr__` methods.

---

## 5. CI/CD & Deployment

### CI (GitHub Actions, `.github/workflows/ci.yml`)

- Triggers on every pull request into `main`, and on push to `main`.
- Spins up a real Postgres 16 service container (not SQLite).
- Installs `requirements.txt`, runs `alembic upgrade head`, then `pytest --cov`.
- A failing test blocks the PR from being merged (with branch protection enabled on `main` in
  the repo settings).

### Deployment (Railway)

Railway's standard model is **native GitHub autodeploy**, configured in Railway's dashboard —
not a deploy step inside the GitHub Actions workflow. Steps to set this up:

1. Create a new Railway project, choose "Deploy from GitHub repo", select this repository.
2. Add a Postgres plugin to the project (Railway provisions `DATABASE_URL` automatically —
   override/rename to match the `DATABASE_URL` env var this app expects, using the
   `postgresql+asyncpg://` scheme).
3. Set the remaining env vars from `.env.example` (`AUTH_TOKEN_SEED` at minimum — use a real
   secret, not the dev default).
4. In Service Settings → Source, confirm the trigger branch is `main`. Every push to `main`
   (i.e. every merged PR) now triggers an automatic build + deploy.
5. Railway builds from the `Dockerfile` in this repo, which runs `alembic upgrade head` before
   starting `uvicorn` — migrations apply automatically on each deploy.

**This step has not been executed** — the sandbox this was built in has no network access to
Railway and no Railway account. Once you've connected the repo and deployed, fill in the
`Deployed URL` field at the top of this README.

---

## 6. AI Reflection

*(Drafted based on the actual development session — please read through and adjust anything
that doesn't match your own experience before submitting; this should be in your voice.)*

**1. What did you use AI for across the four sections?**

- Section 1: drafted the initial system design doc structure and decision table, which I then
  reviewed and approved.
- Section 2: generated the FastAPI scaffold, models, services, and routes; wrote the initial
  test suite alongside each piece.
- Section 3: wrote the Dockerfile, docker-compose.yml, and GitHub Actions workflow.
- Section 4: this reflection itself, drafted from the session log and then reviewed.

**2. Give one example where an AI suggestion improved your work. What did you prompt it with?**

After the ticket breakdown was approved, I said "continue" through each ticket. When building
the booking service (CLINIC-006), the AI proactively wrote a concurrency test firing 10
simultaneous requests at the same slot *before* moving on to the next ticket, rather than just
trusting the code looked correct — this is what surfaced the transaction-commit bug described
below. Without that test being written and run as part of the ticket's own "done when" criteria,
the bug would likely have shipped.

**3. Give one example where AI output was wrong or incomplete and how you caught it.**

The first version of `book_appointment` wrapped the insert in `async with db.begin_nested() if
db.in_transaction() else db.begin():` but never called `commit()` after it. This looked
plausible — the DB partial unique constraint was documented as the "real" safety net — but the
concurrency test run against real Postgres showed **10/10 requests succeeding**, which is
obviously wrong for a single 30-minute slot. Investigating showed each transaction was silently
rolling back on session close (no commit), letting the next one through serially — the exact
opposite of the guarantee being tested for. The fix was an explicit `commit()`/`rollback()` in
each service call; the same class of bug also existed in a fixture that touched an
already-expired ORM attribute after a rollback (`MissingGreenlet` errors), and in a coverage
measurement gap (SQLAlchemy's async engine uses greenlet-based context switching that
coverage.py's default tracer doesn't follow, making the route layer look ~40 points less tested
than it actually was until `concurrency = greenlet` was set in `.coveragerc`). All three were
caught by actually running things against a real Postgres instance rather than trusting the code
by inspection.

**4. Name two decisions you made without AI. Why did you trust your own judgment there?**

- Choosing FastAPI over Django REST Framework — a stack preference informed by what the role's
  concurrency-heavy scenario calls for, not something to defer.
- Deciding that "doctor not found during reschedule" is acceptable as a low-coverage defensive
  branch rather than something to force-test, since the FK's `ON DELETE CASCADE` makes it
  unreachable via the API in practice — a judgment call about where test effort is well spent
  versus where it would just be padding a coverage number.