"""
tests/test_validate_target_date.py

Unit tests for app.services.availability.validate_target_date — a pure
function, no DB required. See docs/architecture.md's decision table
for why past dates are treated as a 400 rather than a 200 + [].
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.exceptions import PastDateError
from app.services.availability import validate_target_date


def test_today_is_valid():
    now = datetime(2026, 7, 14, 9, 0, tzinfo=timezone.utc)
    target = date(2026, 7, 14)
    # Should not raise.
    validate_target_date(target, now)


def test_future_date_is_valid():
    now = datetime(2026, 7, 14, 9, 0, tzinfo=timezone.utc)
    target = date(2026, 7, 15)
    # Should not raise.
    validate_target_date(target, now)


def test_yesterday_raises_past_date_error():
    now = datetime(2026, 7, 14, 9, 0, tzinfo=timezone.utc)
    target = date(2026, 7, 13)
    with pytest.raises(PastDateError):
        validate_target_date(target, now)


def test_far_past_date_raises_past_date_error():
    now = datetime(2026, 7, 14, 9, 0, tzinfo=timezone.utc)
    target = date(2020, 1, 1)
    with pytest.raises(PastDateError):
        validate_target_date(target, now)


def test_error_message_includes_the_date():
    now = datetime(2026, 7, 14, 9, 0, tzinfo=timezone.utc)
    target = date(2026, 7, 1)
    with pytest.raises(PastDateError, match="2026-07-01"):
        validate_target_date(target, now)


def test_today_valid_regardless_of_time_of_day():
    """A late-in-the-day 'now' shouldn't push today's date into being
    treated as past — the check is date-only, not datetime-precise
    (the lead-time filter in compute_available_slots is what handles
    excluding already-passed slots later today)."""
    now = datetime(2026, 7, 14, 23, 59, tzinfo=timezone.utc)
    target = date(2026, 7, 14)
    validate_target_date(target, now)


def test_boundary_just_after_midnight_next_day_is_valid():
    now = datetime(2026, 7, 14, 0, 0, 1, tzinfo=timezone.utc)
    target = date(2026, 7, 14)
    validate_target_date(target, now)