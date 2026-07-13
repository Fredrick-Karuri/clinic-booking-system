# AI Reflection

*(Drafted based on the actual development session — reviewed and adjusted to match my own
experience.)*

## 1. What did you use AI for across the four sections?

- **Section 1:** drafted the initial system design doc structure and decision table, which I
  then reviewed and approved.
- **Section 2:** generated the FastAPI scaffold, models, services, and routes; wrote the
  initial test suite alongside each piece.
- **Section 3:** wrote the Dockerfile, docker-compose.yml, and GitHub Actions workflow; walked
  through debugging the real deployment issues (driver mismatch, port mismatch, internal vs.
  public DB hostname) as they came up live.
- **Section 4:** this reflection itself, drafted from the session log and then reviewed.

## 2. Give one example where an AI suggestion improved your work. What did you prompt it with?

After the ticket breakdown was approved, I said "continue" through each ticket. When building
the booking service (CLINIC-006), the AI proactively wrote a concurrency test firing 10
simultaneous requests at the same slot *before* moving on to the next ticket, rather than just
trusting the code looked correct — this is what surfaced the transaction-commit bug described
below. Without that test being written and run as part of the ticket's own "done when" criteria,
the bug would likely have shipped.

## 3. Give one example where AI output was wrong or incomplete and how you caught it.

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
caught by actually running things against a real Postgres instance rather than trusting the
code by inspection.

## 4. Name two decisions you made without AI. Why did you trust your own judgment there?

- Choosing FastAPI over Django REST Framework — a stack preference informed by what the role's
  concurrency-heavy scenario calls for, not something to defer.
- Deciding that "doctor not found during reschedule" is acceptable as a low-coverage defensive
  branch rather than something to force-test, since the FK's `ON DELETE CASCADE` makes it
  unreachable via the API in practice — a judgment call about where test effort is well spent
  versus where it would just be padding a coverage number.