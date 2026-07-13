"""
app/api/deps.py

Minimal auth dependency. Resolves a bearer token to a patient_id.
This is deliberately not a full identity system (see design doc,
Non-Goals) — it exists to close the specific hole this exercise cares
about: a caller must not be able to book/cancel/reschedule on behalf
of a patient_id it doesn't control.

Token scheme: HMAC-signed opaque token issued out-of-band (e.g. at
patient registration, outside this API's scope). Format:
"<patient_id>.<signature>", where signature = HMAC-SHA256(patient_id,
secret). This is sufficient to prove possession of a per-patient
secret without implementing full session/identity infrastructure.
"""

import hashlib
import hmac
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.core.logging_config import get_logger
from app.repositories.appointment.base import AppointmentRepository
from app.repositories.appointment.postgres import PostgresAppointmentRepository
from app.services.booking import BookingService

logger = get_logger("app.auth")

bearer_scheme = HTTPBearer(auto_error=False)


def issue_token(patient_id: uuid.UUID) -> str:
    """Issue a signed token for a given patient_id (used by seed/test fixtures)."""
    settings = get_settings()
    signature = hmac.new(
        settings.auth_token_seed.encode(), str(patient_id).encode(), hashlib.sha256
    ).hexdigest()
    return f"{patient_id}.{signature}"


def _verify_token(token: str) -> uuid.UUID:
    settings = get_settings()
    try:
        patient_id_str, signature = token.rsplit(".", 1)
        patient_id = uuid.UUID(patient_id_str)
    except (ValueError, AttributeError) as exc:
        logger.warning("auth_token_malformed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token."
        ) from exc

    expected_signature = hmac.new(
        settings.auth_token_seed.encode(), patient_id_str.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        logger.warning("auth_signature_invalid", extra={"claimed_patient_id": patient_id_str})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token."
        )

    return patient_id


async def get_current_patient_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db_session),  # noqa: ARG001 — reserved for future patient lookup
) -> uuid.UUID:
    """
    Resolve the requesting patient's id from the bearer token.
    Raises 401 if the token is missing or invalid. The returned
    patient_id is the only source of truth for "who is making this
    request" — request bodies must never be trusted for patient_id.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _verify_token(credentials.credentials)


def get_appointment_repository(db: AsyncSession = Depends(get_db_session)) -> AppointmentRepository:
    """The Open/Closed seam: swapping the backing store means providing a
    different AppointmentRepository implementation here — nothing else
    (routes, service, business rules) needs to change."""
    return PostgresAppointmentRepository(db)


def get_booking_service(
    repository: AppointmentRepository = Depends(get_appointment_repository),
    settings: Settings = Depends(get_settings),
) -> BookingService:
    return BookingService(
        repository=repository,
        slot_duration_minutes=settings.slot_duration_minutes,
        booking_lead_time_minutes=settings.booking_lead_time_minutes,
    )