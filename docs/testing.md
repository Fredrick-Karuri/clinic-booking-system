# Testing

```bash
make test
```

Runs `PYTHONPATH=. pytest --cov --cov-report=term-missing` — the explicit `PYTHONPATH=.` isn't
strictly required by pytest's default import-mode given this package layout, but makes the
command work the same way regardless of invocation context (different cwd, IDE runner, etc.)
rather than relying on an implicit pytest behavior.

**52/52 tests passing, 95% coverage** on `app/`, stable across repeated runs.

Everything runs against a **real Postgres instance** — the concurrency
guarantees under test (`SELECT ... FOR UPDATE`, the partial unique constraint) are Postgres-
specific behavior a lighter-weight substitute can't faithfully reproduce.

## The Two Tests That Matter Most

- `test_concurrent_booking_same_slot_only_one_succeeds` — 10 simultaneous booking requests at
  the same slot, exactly 1 succeeds.
- `test_concurrent_reschedule_same_new_slot_only_one_succeeds` — two patients reschedule into
  the same new slot simultaneously; exactly 1 succeeds, the loser's original appointment is
  confirmed still intact.


Coverage is tracked with `concurrency = greenlet, thread` set in `.coveragerc`, since
SQLAlchemy's async extension (greenlet-based) and FastAPI's threadpool-run sync dependencies
aren't followed by coverage.py's default tracer — see [REFLECTION.md](../REFLECTION.md) for the
story of catching and fixing this.

## Test Files

| File | Covers |
|---|---|
| `tests/test_availability.py` | Slot computation logic (pure function, no DB) |
| `tests/test_booking.py` | Booking validation + the core concurrency test |
| `tests/test_cancel_reschedule.py` | Cancel/reschedule service logic + concurrency |
| `tests/test_concurrency.py` | Additional concurrent-request scenarios |
| `tests/test_appointments_endpoint.py` | HTTP-level status code mapping for appointment routes |
| `tests/test_doctors_endpoint.py` | Availability endpoint, including error cases |
| `tests/test_patients_endpoint.py` | Bonus listing endpoint, ownership enforcement |
| `tests/test_auth.py` | Token issuance/verification |
| `tests/test_logging_config.py` | Structured JSON log formatting |
| `tests/test_health.py` | Liveness check |