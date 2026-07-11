"""
app/api/routes/appointments.py

POST /appointments (CLINIC-007), PATCH .../cancel (CLINIC-009),
PATCH .../reschedule (CLINIC-010). Patient-listing endpoint is added
in CLINIC-011.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_patient_id
from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.schemas.appointment import (
    AppointmentCancelRequest,
    AppointmentCreate,
    AppointmentOut,
    AppointmentRescheduleRequest,
)
from app.services.booking import (
    AppointmentAlreadyCancelledError,
    AppointmentNotFoundError,
    BookingRequest,
    DoctorNotFoundError,
    NotAppointmentOwnerError,
    SlotAlreadyBookedError,
    SlotInPastError,
    SlotNotOnGridError,
    SlotOutsideWorkingHoursError,
    SlotTooSoonError,
    book_appointment,
    cancel_appointment,
    reschedule_appointment,
)

router = APIRouter(prefix="/appointments", tags=["appointments"])

_VALIDATION_ERRORS = (SlotOutsideWorkingHoursError, SlotNotOnGridError, SlotInPastError, SlotTooSoonError)


@router.post("", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    payload: AppointmentCreate,
    patient_id=Depends(get_current_patient_id),
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> AppointmentOut:
    try:
        appointment = await book_appointment(
            db,
            BookingRequest(doctor_id=payload.doctor_id, patient_id=patient_id, slot_time=payload.slot_time),
            slot_duration_minutes=settings.slot_duration_minutes,
            booking_lead_time_minutes=settings.booking_lead_time_minutes,
        )
    except DoctorNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except _VALIDATION_ERRORS as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SlotAlreadyBookedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return AppointmentOut.model_validate(appointment)


@router.patch("/{appointment_id}/cancel", response_model=AppointmentOut)
async def cancel_appointment_route(
    appointment_id: uuid.UUID,
    payload: AppointmentCancelRequest,
    patient_id=Depends(get_current_patient_id),
    db: AsyncSession = Depends(get_db_session),
) -> AppointmentOut:
    try:
        appointment = await cancel_appointment(db, appointment_id, patient_id, payload.reason)
    except AppointmentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except NotAppointmentOwnerError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except AppointmentAlreadyCancelledError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return AppointmentOut.model_validate(appointment)


@router.patch("/{appointment_id}/reschedule", response_model=AppointmentOut)
async def reschedule_appointment_route(
    appointment_id: uuid.UUID,
    payload: AppointmentRescheduleRequest,
    patient_id=Depends(get_current_patient_id),
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> AppointmentOut:
    try:
        new_appointment = await reschedule_appointment(
            db,
            appointment_id,
            patient_id,
            payload.new_slot_time,
            slot_duration_minutes=settings.slot_duration_minutes,
            booking_lead_time_minutes=settings.booking_lead_time_minutes,
        )
    except (AppointmentNotFoundError, DoctorNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except NotAppointmentOwnerError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except _VALIDATION_ERRORS as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except (AppointmentAlreadyCancelledError, SlotAlreadyBookedError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return AppointmentOut.model_validate(new_appointment)