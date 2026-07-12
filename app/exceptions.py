"""
app/exceptions.py

Business-level exceptions for the booking domain. Raised by
app.services.booking_service and caught by the API routes (see
app/api/routes/appointments.py) to map onto HTTP status codes.

Deliberately separate from app.repositories.appointment_repository's
RepositoryError/SlotConflictError: those are persistence/concurrency
concerns a repository implementation raises; these are business rules
the service layer raises after translating (or on its own, for rules
that never touch persistence, like working-hours validation).
"""


class BookingError(Exception):
    """Base class for booking validation/conflict errors."""


class SlotOutsideWorkingHoursError(BookingError):
    pass


class SlotNotOnGridError(BookingError):
    pass


class SlotInPastError(BookingError):
    pass


class SlotTooSoonError(BookingError):
    pass


class SlotAlreadyBookedError(BookingError):
    pass


class DoctorNotFoundError(BookingError):
    pass


class AppointmentNotFoundError(BookingError):
    pass


class AppointmentAlreadyCancelledError(BookingError):
    pass


class NotAppointmentOwnerError(BookingError):
    pass