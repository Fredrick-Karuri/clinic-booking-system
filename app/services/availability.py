"""
app/services/availability.py

Pure slot-computation logic. Deliberately has no DB or HTTP
dependencies — it takes plain data in and returns plain data out, so
it can be unit tested in isolation from the database and API layers.

A "slot" is never stored; it's derived from a doctor's working hours
and the fixed slot grid, then filtered against whichever slot times
are already taken.
"""

from datetime import date, datetime, time, timedelta, timezone


def generate_slot_grid(
    work_start: time,
    work_end: time,
    target_date: date,
    slot_duration_minutes: int,
) -> list[datetime]:
    """
    Return every slot start time (UTC-aware) for a doctor's working
    hours on target_date, spaced by slot_duration_minutes, not
    including a final slot that would run past work_end.
    """
    if work_start >= work_end:
        return []

    slots: list[datetime] = []
    current = datetime.combine(target_date, work_start, tzinfo=timezone.utc)
    end_boundary = datetime.combine(target_date, work_end, tzinfo=timezone.utc)
    step = timedelta(minutes=slot_duration_minutes)

    while current + step <= end_boundary:
        slots.append(current)
        current += step

    return slots


def compute_available_slots(
    work_start: time,
    work_end: time,
    target_date: date,
    taken_slot_times: set[datetime],
    slot_duration_minutes: int,
    now: datetime | None = None,
    booking_lead_time_minutes: int = 0,
) -> list[datetime]:
    """
    Return the free slot start times for a doctor on target_date.

    - taken_slot_times: slot_time values of currently BOOKED
      appointments for this doctor (already filtered to target_date
      by the caller).
    - now / booking_lead_time_minutes: if provided, slots within
      booking_lead_time_minutes of `now` are excluded (bonus
      requirement: prevent booking within 1hr of now). Pass
      booking_lead_time_minutes=0 to disable this filter.
    """
    all_slots = generate_slot_grid(work_start, work_end, target_date, slot_duration_minutes)
    free_slots = [slot for slot in all_slots if slot not in taken_slot_times]

    if now is not None and booking_lead_time_minutes > 0:
        cutoff = now + timedelta(minutes=booking_lead_time_minutes)
        free_slots = [slot for slot in free_slots if slot >= cutoff]

    return free_slots


def is_slot_on_grid(
    slot_time: datetime,
    work_start: time,
    work_end: time,
    slot_duration_minutes: int,
) -> bool:
    """
    True if slot_time falls exactly on the doctor's slot grid for its
    own date and within working hours (not past work_end - duration).
    """
    target_date = slot_time.date()
    valid_slots = generate_slot_grid(work_start, work_end, target_date, slot_duration_minutes)
    return slot_time in valid_slots