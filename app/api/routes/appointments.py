"""
app/api/routes/appointments.py

POST /appointments, PATCH .../cancel, PATCH .../reschedule.
Patient-listing endpoint lives in patients.py.

Routes only translate between HTTP and the BookingService — no
business logic, no persistence, lives here.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_booking_service, get_current_patient_id
from app.exceptions import (
    AppointmentAlreadyCancelledError,
    AppointmentNotFoundError,
    DoctorNotFoundError,
    NotAppointmentOwnerError,
    SlotAlreadyBookedError,
    SlotInPastError,
    SlotNotOnGridError,
    SlotOutsideWorkingHoursError,
    SlotTooSoonError,
)
from app.schemas.appointment import (
    AppointmentCancelRequest,
    AppointmentCreate,
    AppointmentOut,
    AppointmentRescheduleRequest,
)
from app.services.booking import BookingRequest, BookingService

router = APIRouter(prefix="/appointments", tags=["appointments"])

_VALIDATION_ERRORS = (SlotOutsideWorkingHoursError, SlotNotOnGridError, SlotInPastError, SlotTooSoonError)


@router.post("", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    payload: AppointmentCreate,
    patient_id=Depends(get_current_patient_id),
    booking_service: BookingService = Depends(get_booking_service),
) -> AppointmentOut:
    try:
        appointment = await booking_service.book_appointment(
            BookingRequest(doctor_id=payload.doctor_id, patient_id=patient_id, slot_time=payload.slot_time)
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
    booking_service: BookingService = Depends(get_booking_service),
) -> AppointmentOut:
    try:
        appointment = await booking_service.cancel_appointment(appointment_id, patient_id, payload.reason)
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
    booking_service: BookingService = Depends(get_booking_service),
) -> AppointmentOut:
    try:
        new_appointment = await booking_service.reschedule_appointment(
            appointment_id, patient_id, payload.new_slot_time
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
