"""
app/api/routes/appointments.py

POST /appointments — CLINIC-007. Cancel/reschedule/patient-listing
endpoints are added in later tickets (CLINIC-009, 010, 011).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_patient_id
from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.schemas.appointment import AppointmentCreate, AppointmentOut
from app.services.booking import (
    BookingRequest,
    DoctorNotFoundError,
    SlotAlreadyBookedError,
    SlotInPastError,
    SlotNotOnGridError,
    SlotOutsideWorkingHoursError,
    SlotTooSoonError,
    book_appointment,
)

router = APIRouter(prefix="/appointments", tags=["appointments"])


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
    except (SlotOutsideWorkingHoursError, SlotNotOnGridError, SlotInPastError, SlotTooSoonError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SlotAlreadyBookedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return AppointmentOut.model_validate(appointment)