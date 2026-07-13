# Testing

```bash
make test
```

Runs `PYTHONPATH=. pytest --cov --cov-report=term-missing` — the explicit `PYTHONPATH=.` isn't
strictly required by pytest's default import-mode given this package layout, but makes the
command work the same way regardless of invocation context (different cwd, IDE runner, etc.)
rather than relying on an implicit pytest behavior.

**52/52 tests passing, 98% coverage** on `app/`, stable across repeated runs.

Everything runs against a **real Postgres instance**, not SQLite or mocks — the concurrency
guarantees under test (`SELECT ... FOR UPDATE`, the partial unique constraint) are Postgres-
specific behavior a lighter-weight substitute can't faithfully reproduce.

## The Two Tests That Matter Most

- `test_concurrent_booking_same_slot_only_one_succeeds` — 10 simultaneous booking requests at
  the same slot, exactly 1 succeeds.
- `test_concurrent_reschedule_same_new_slot_only_one_succeeds` — two patients reschedule into
  the same new slot simultaneously; exactly 1 succeeds, the loser's original appointment is
  confirmed still intact.

## Getting an Accurate Coverage Number Took Two Real Fixes

**Event loop / connection pool mismatch.** `pytest.ini` originally used a session-scoped
event loop while DB fixtures were function-scoped, causing `InterfaceError`/`RuntimeError`
failures as connections got torn down on a loop that outlived them. Fixed by using
function-scoped loops (`asyncio_default_fixture_loop_scope = function`) *and* adding an
autouse fixture that overrides the app's `get_db_session` dependency to use each test's own
engine — without that override, the app's module-level singleton engine (bound to whatever
loop happened to create it first) would conflict with per-test loops the moment more than one
async test ran.

**Coverage under-reporting by ~40 points.** SQLAlchemy's async extension uses greenlet-based
context switching, and FastAPI runs sync dependency functions in a threadpool — coverage.py's
default tracer follows neither. `.coveragerc` now sets `concurrency = greenlet, thread`; before
this, `app/api/deps.py` and the repository's `IntegrityError`-handling branch looked completely
untested despite being exercised by every test that hit them.

## Uncovered Lines, and Why

The remaining ~2% of uncovered lines are documented, not silently ignored:

- Two branches unreachable via the API (the doctor FK has `ondelete=CASCADE`, so an
  appointment can never point at a deleted doctor).
- The repository's `IntegrityError` backstop path in `reschedule()` — hit inconsistently
  across runs depending on task-scheduling timing under the concurrency test, a genuinely
  racy line, confirmed by running coverage three times in a row and seeing it flip.
- The real `get_db_session` implementation — never exercised by the test suite by design,
  since tests override it to use their own engine (it does run in every actual request in
  the deployed app).
- Two cosmetic `__repr__` methods.

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