"""
app/repositories/appointment/base.py

Abstract repository interface for Doctor/Appointment persistence.
This is the seam a concrete implementation (Postgres today) plugs
into — app.services.booking_service depends only on this interface,
never on SQLAlchemy or any specific database.

Two things are part of the CONTRACT, not left to each implementation
to decide:

1. create_booked_appointment and reschedule MUST be atomic — no
   caller-visible partial state.
2. Both MUST raise SlotConflictError (not a business exception — see
   app.exceptions — the service layer translates it) if the target
   slot is unavailable, and MUST leave any existing data untouched
   when they do (reschedule in particular: a failed reschedule must
   never lose the caller's original appointment).

How a given implementation achieves those guarantees (row locking,
constraints, optimistic retry, etc.) is its own concern.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.models import Appointment, Doctor


class RepositoryError(Exception):
    """Base class for repository-level errors — persistence/concurrency
    concerns, distinct from the business-rule errors in app.exceptions."""


class SlotConflictError(RepositoryError):
    """The requested (doctor_id, slot_time) is already held by a booked appointment."""


class AppointmentRepository(ABC):
    @abstractmethod
    async def get_doctor(self, doctor_id: UUID) -> Doctor | None: ...

    @abstractmethod
    async def get_appointment(self, appointment_id: UUID) -> Appointment | None: ...

    @abstractmethod
    async def create_booked_appointment(
        self, doctor_id: UUID, patient_id: UUID, slot_time: datetime
    ) -> Appointment:
        """Atomically create a BOOKED appointment. Raises SlotConflictError if the slot is taken."""

    @abstractmethod
    async def save_cancellation(self, appointment: Appointment, reason: str) -> Appointment:
        """Persist `appointment` as cancelled with the given reason."""

    @abstractmethod
    async def reschedule(self, appointment: Appointment, new_slot_time: datetime) -> Appointment:
        """
        Atomically cancel `appointment` and create a new booked
        appointment for the same doctor/patient at new_slot_time.
        Raises SlotConflictError if new_slot_time is taken —
        `appointment` must be left untouched (still booked at its
        original slot) in that case.
        """
