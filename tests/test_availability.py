"""
app/tests/test_availability.py

Unit tests for the pure availability service. No DB, no
HTTP — plain data in, plain data out.
"""

from datetime import date, datetime, time, timezone

from app.services.availability import (
    compute_available_slots,
    generate_slot_grid,
    is_slot_on_grid,
)

WORK_START = time(9, 0)
WORK_END = time(11, 0)  # 4 slots of 30 min: 09:00, 09:30, 10:00, 10:30
TARGET_DATE = date(2026, 8, 3)  # arbitrary future Monday
SLOT_MINUTES = 30


def test_generate_slot_grid_fully_free_day():
    slots = generate_slot_grid(WORK_START, WORK_END, TARGET_DATE, SLOT_MINUTES)
    expected = [
        datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc),
        datetime(2026, 8, 3, 9, 30, tzinfo=timezone.utc),
        datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc),
        datetime(2026, 8, 3, 10, 30, tzinfo=timezone.utc),
    ]
    assert slots == expected


def test_generate_slot_grid_last_slot_does_not_run_past_work_end():
    # work_end is 11:00; the last slot (10:30-11:00) is valid, but
    # there is no 11:00 slot since that would run past work_end.
    slots = generate_slot_grid(WORK_START, WORK_END, TARGET_DATE, SLOT_MINUTES)
    assert datetime(2026, 8, 3, 11, 0, tzinfo=timezone.utc) not in slots
    assert datetime(2026, 8, 3, 10, 30, tzinfo=timezone.utc) in slots


def test_generate_slot_grid_invalid_working_hours_returns_empty():
    slots = generate_slot_grid(time(17, 0), time(9, 0), TARGET_DATE, SLOT_MINUTES)
    assert slots == []


def test_compute_available_slots_fully_free_day():
    free = compute_available_slots(
        WORK_START, WORK_END, TARGET_DATE, taken_slot_times=set(), slot_duration_minutes=SLOT_MINUTES
    )
    assert len(free) == 4


def test_compute_available_slots_fully_booked_day():
    all_slots = set(generate_slot_grid(WORK_START, WORK_END, TARGET_DATE, SLOT_MINUTES))
    free = compute_available_slots(
        WORK_START, WORK_END, TARGET_DATE, taken_slot_times=all_slots, slot_duration_minutes=SLOT_MINUTES
    )
    assert free == []


def test_compute_available_slots_partially_booked_day():
    taken = {datetime(2026, 8, 3, 9, 30, tzinfo=timezone.utc)}
    free = compute_available_slots(
        WORK_START, WORK_END, TARGET_DATE, taken_slot_times=taken, slot_duration_minutes=SLOT_MINUTES
    )
    assert datetime(2026, 8, 3, 9, 30, tzinfo=timezone.utc) not in free
    assert len(free) == 3


def test_compute_available_slots_appointment_at_last_valid_slot():
    # An appointment starting exactly at work_end - slot_duration
    # (10:30) should correctly remove just that slot.
    taken = {datetime(2026, 8, 3, 10, 30, tzinfo=timezone.utc)}
    free = compute_available_slots(
        WORK_START, WORK_END, TARGET_DATE, taken_slot_times=taken, slot_duration_minutes=SLOT_MINUTES
    )
    assert datetime(2026, 8, 3, 10, 30, tzinfo=timezone.utc) not in free
    assert len(free) == 3


def test_compute_available_slots_respects_booking_lead_time():
    # "now" is 09:15; with a 60-minute lead time, slots before 10:15
    # (09:00, 09:30, 10:00) should be excluded, leaving only 10:30.
    now = datetime(2026, 8, 3, 9, 15, tzinfo=timezone.utc)
    free = compute_available_slots(
        WORK_START,
        WORK_END,
        TARGET_DATE,
        taken_slot_times=set(),
        slot_duration_minutes=SLOT_MINUTES,
        now=now,
        booking_lead_time_minutes=60,
    )
    assert free == [datetime(2026, 8, 3, 10, 30, tzinfo=timezone.utc)]


def test_is_slot_on_grid_valid_slot():
    assert is_slot_on_grid(
        datetime(2026, 8, 3, 9, 30, tzinfo=timezone.utc), WORK_START, WORK_END, SLOT_MINUTES
    )


def test_is_slot_on_grid_off_grid_slot():
    # 09:15 is not on the 30-minute grid.
    assert not is_slot_on_grid(
        datetime(2026, 8, 3, 9, 15, tzinfo=timezone.utc), WORK_START, WORK_END, SLOT_MINUTES
    )


def test_is_slot_on_grid_outside_working_hours():
    assert not is_slot_on_grid(
        datetime(2026, 8, 3, 11, 0, tzinfo=timezone.utc), WORK_START, WORK_END, SLOT_MINUTES
    )