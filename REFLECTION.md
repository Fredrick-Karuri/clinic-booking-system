# AI Reflection

## 1. What did you use AI for across the four sections?

I maintain a set of personal skills — reusable prompt/process specs that define what "good"
looks like for a given kind of work (an engineering skill, a debugging skill, a documentation
skill, etc.). The engineering skill in particular enforces a strict project kickoff order:

```
1. Design Document   →   defines WHAT and WHY. Locks scope.
2. Tickets           →   defines HOW and WHEN. Breaks scope into work.
3. Code              →   executes the plan.
```

No code until both the design doc and tickets exist and are confirmed. Across all four
sections, AI was used within that structure rather than as an ad-hoc code generator:

- **Section 1:** drafted the initial system design doc structure and decision table against
  the engineering skill's format, which I then reviewed and approved before any code existed.
- **Section 2:** generated the FastAPI scaffold, models, services, and routes ticket by ticket;
  wrote the initial test suite alongside each piece.
- **Section 3:** wrote the Dockerfile, docker-compose.yml, and GitHub Actions workflow; walked
  through debugging the real deployment issues (driver mismatch, port mismatch, internal vs.
  public DB hostname) as they came up live.
- **Section 4:** this reflection itself, drafted from the session log and then reviewed.

## 2. Give one example where an AI suggestion improved your work. What did you prompt it with?

I originally preferred scoping AI working sessions per ticket — one ticket, one session, on
the theory that smaller scope means tighter control. AI suggested scoping per *epic* instead
(a group of related tickets completed in one continuous session), and this measurably improved
output quality within each session — more consistent context across related pieces of a
feature, fewer contradictions between files that were supposed to agree with each other.

I prompted it with the job-to-be-done straight from the assessment PDF combined with my
engineering skill, specifically the kickoff-order rule above — the skill's insistence on
design → tickets → code before any code gets written is what made per-epic scoping viable in
the first place, since the epic's tickets were already fully defined and mutually consistent
before implementation started.

## 3. Give one example where AI output was wrong or incomplete and how you caught it.

**Missing type imports causing a circular-import fix attempt.** In `app/models/appointment.py`
and `app/models/doctor.py`, Pylance flagged missing type imports for the relationship
annotations between the two models. Prompting AI for a fix produced a second, worse problem:
a genuine circular import between the two model files, since each imports the other's type for
its `relationship()` annotation. We resolved this properly using `TYPE_CHECKING` — importing
the cross-referenced type only under `if TYPE_CHECKING:` and quoting the annotation, which
satisfies the type checker without creating a runtime circular import. The first AI fix
attempt didn't catch this on its own; it took a follow-up round specifically pointing at the
circular import to get to the `TYPE_CHECKING` pattern.

## 4. Name two decisions you made without AI. Why did you trust your own judgment there?

**Decoupling the booking service for single responsibility.** The first working version of the
booking logic lived in one `services/booking.py` combining the exception hierarchy, business
validation, and persistence/locking mechanics. It worked and was fully tested, but the smell
was strong enough that I didn't need AI to flag it — from experience, when one file is doing
validation, orchestration, and raw SQL/locking all at once, that's the textbook sign it's doing
more than one job. I made the call to decouple into `app/exceptions.py` (business rules only),
an abstract `AppointmentRepository` (the atomicity + conflict-signaling contract any backing
store must satisfy), a concrete `PostgresAppointmentRepository` (owning `SELECT ... FOR UPDATE`,
commit/rollback, `IntegrityError` translation), and a `BookingService` with zero SQL and zero
session handling. I still used AI to actually perform the refactor once I'd decided on it, but
detecting the smell and deciding it was worth fixing was mine.

**Choosing Make for developer-speed shorthands.** Adding `make token`, `make psql`, `make seed`,
etc. wasn't an AI suggestion — it came from experience that a clear, named "job to be done"
(`make token` instead of remembering a multi-line Python one-liner) builds a mental model that
lets a developer ship and work faster, especially useful returning to a project cold after time
away. This is a workflow-ergonomics call, not a correctness one, so it's the kind of judgment
that comes from having felt the friction of *not* having it on past projects rather than
something to defer to AI.