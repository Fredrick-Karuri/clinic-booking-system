"""
app/tests/test_patients_endpoint.py

End-to-end HTTP tests for GET /patients/{id}/appointments,
run against the real app + real Postgres via httpx's ASGI transport.
Covers sort order, the future-only filter, and the ownership check.
"""

import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from httpx import ASGITransport

from app.api.deps import issue_token
from app.main import app

pytestmark = pytest.mark.asyncio


def _future_slot(days: int, hour: int) -> str:
    target = datetime.now(timezone.utc) + timedelta(days=days)
    return target.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


async def test_list_appointments_sorted_and_scoped_to_owner(test_doctor):
    patient_id = uuid.uuid4()
    token = issue_token(patient_id)
    headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Book two future slots out of chronological order.
        await client.post(
            "/appointments",
            json={"doctor_id": str(test_doctor.id), "slot_time": _future_slot(days=4, hour=14)},
            headers=headers,
        )
        await client.post(
            "/appointments",
            json={"doctor_id": str(test_doctor.id), "slot_time": _future_slot(days=4, hour=11)},
            headers=headers,
        )

        response = await client.get(f"/patients/{patient_id}/appointments", headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        # Must come back sorted ascending by slot_time, not insertion order.
        assert body[0]["slot_time"] < body[1]["slot_time"]
        assert all(appt["patient_id"] == str(patient_id) for appt in body)


async def test_list_appointments_forbidden_for_other_patient(test_doctor):
    patient_id = uuid.uuid4()
    other_patient_id = uuid.uuid4()
    token = issue_token(patient_id)
    headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/patients/{other_patient_id}/appointments", headers=headers)
        assert response.status_code == 403


async def test_list_appointments_excludes_cancelled(test_doctor):
    patient_id = uuid.uuid4()
    token = issue_token(patient_id)
    headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        book_response = await client.post(
            "/appointments",
            json={"doctor_id": str(test_doctor.id), "slot_time": _future_slot(days=4, hour=9)},
            headers=headers,
        )
        appointment_id = book_response.json()["id"]

        await client.patch(
            f"/appointments/{appointment_id}/cancel", json={"reason": "test"}, headers=headers
        )

        response = await client.get(f"/patients/{patient_id}/appointments", headers=headers)
        assert response.status_code == 200
        assert response.json() == []