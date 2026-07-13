# Clinic Booking API

A REST API for a small clinic (5 doctors) to let patients view availability, book, cancel, and
reschedule 30-minute appointment slots.

- **Deployed URL:** https://clinic-booking.up.railway.app/
- **Repository:** https://github.com/Fredrick-Karuri/clinic-booking-system
- **Interactive API docs (Swagger):** https://clinic-booking.up.railway.app/docs

## Why

Clinics booking appointments manually (or with a naive check-then-insert API) run into the same
failure mode: two patients can both get a "confirmed" slot when requests arrive close together.
This project exists to solve that specific problem correctly — race-safe booking backed by a
real database constraint, not just an application-level check — while keeping the rest of the
system (availability, cancellation, rescheduling) simple and well-tested.

## Who It's For

Reviewers assessing backend engineering craft: system design reasoning, concurrency-safe API
implementation, test discipline, and a real CI/CD + cloud deployment — not just a working demo.

## Experience Promise

Once running (locally or via the deployed URL), a patient can:
- See a doctor's real, working-hours-aware free slots for any day
- Book a slot — with the guarantee that under concurrent requests, exactly one booking wins
- Cancel or reschedule an existing appointment, with old/new slot state kept consistent
- List their own upcoming appointments (bonus endpoint)

## Quick Start

```bash
git clone https://github.com/Fredrick-Karuri/clinic-booking-system
cd clinic-booking-system
cp .env.example .env
make up        # builds the app image, starts Postgres + the API via Docker Compose
make migrate    # in a second terminal, once the DB is healthy
make seed       # populates 5 sample doctors
```

API is now at `http://localhost:8000`, interactive docs at `http://localhost:8000/docs`.

For the local Python (non-Docker) path, generating auth tokens, and inspecting the database
directly, see [docs/getting-started.md](docs/getting-started.md).

---

## Deeper Docs

| Doc | Covers |
|---|---|
| [docs/architecture.md](docs/architecture.md) | System design, data model, key decisions, non-goals |
| [docs/api.md](docs/api.md) | Endpoint reference, status codes, auth |
| [docs/testing.md](docs/testing.md) | Test strategy, coverage, the concurrency bugs found along the way |
| [docs/observability.md](docs/observability.md) | Structured logging, what's instrumented, what's deliberately not (yet) |
| [docs/deployment.md](docs/deployment.md) | CI/CD pipeline, Railway deployment, the gotchas hit getting there |
| [REFLECTION.md](REFLECTION.md) | AI usage reflection |