"""
app/tests/test_appointments_endpoint.py

HTTP-level tests for the appointments routes,
run against the real app + real Postgres via httpx's ASGI transport.
These exist specifically to cover the status-code-mapping branches in
the route handlers themselves (route -> HTTPException), which the
service-layer tests in test_booking.py / test_cancel_reschedule.py
don't exercise.
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


async def test_post_appointments_no_token_401():
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/appointments", json={"doctor_id": str(uuid.uuid4()), "slot_time": _future_slot(3, 10)}
        )
    assert response.status_code == 401


async def test_post_appointments_unknown_doctor_404():
    token = issue_token(uuid.uuid4())
    headers = {"Authorization": f"Bearer {token}"}
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/appointments",
            json={"doctor_id": str(uuid.uuid4()), "slot_time": _future_slot(3, 10)},
            headers=headers,
        )
    assert response.status_code == 404


async def test_post_appointments_outside_hours_400(test_doctor):
    token = issue_token(uuid.uuid4())
    headers = {"Authorization": f"Bearer {token}"}
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/appointments",
            json={"doctor_id": str(test_doctor.id), "slot_time": _future_slot(3, 20)},
            headers=headers,
        )
    assert response.status_code == 400


async def test_post_appointments_conflict_409(test_doctor):
    token = issue_token(uuid.uuid4())
    headers = {"Authorization": f"Bearer {token}"}
    slot = _future_slot(3, 10)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/appointments", json={"doctor_id": str(test_doctor.id), "slot_time": slot}, headers=headers
        )
        assert first.status_code == 201
        second = await client.post(
            "/appointments", json={"doctor_id": str(test_doctor.id), "slot_time": slot}, headers=headers
        )
    assert second.status_code == 409


async def test_cancel_route_not_found_404():
    token = issue_token(uuid.uuid4())
    headers = {"Authorization": f"Bearer {token}"}
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            f"/appointments/{uuid.uuid4()}/cancel", json={"reason": "test"}, headers=headers
        )
    assert response.status_code == 404


async def test_cancel_route_forbidden_403(test_doctor):
    owner_token = issue_token(uuid.uuid4())
    other_token = issue_token(uuid.uuid4())
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        booking = await client.post(
            "/appointments",
            json={"doctor_id": str(test_doctor.id), "slot_time": _future_slot(3, 10)},
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        appointment_id = booking.json()["id"]
        response = await client.patch(
            f"/appointments/{appointment_id}/cancel",
            json={"reason": "not mine"},
            headers={"Authorization": f"Bearer {other_token}"},
        )
    assert response.status_code == 403


async def test_cancel_route_already_cancelled_409(test_doctor):
    token = issue_token(uuid.uuid4())
    headers = {"Authorization": f"Bearer {token}"}
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        booking = await client.post(
            "/appointments",
            json={"doctor_id": str(test_doctor.id), "slot_time": _future_slot(3, 10)},
            headers=headers,
        )
        appointment_id = booking.json()["id"]
        first_cancel = await client.patch(
            f"/appointments/{appointment_id}/cancel", json={"reason": "first"}, headers=headers
        )
        assert first_cancel.status_code == 200
        second_cancel = await client.patch(
            f"/appointments/{appointment_id}/cancel", json={"reason": "second"}, headers=headers
        )
    assert second_cancel.status_code == 409


async def test_reschedule_route_success_200(test_doctor):
    token = issue_token(uuid.uuid4())
    headers = {"Authorization": f"Bearer {token}"}
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        booking = await client.post(
            "/appointments",
            json={"doctor_id": str(test_doctor.id), "slot_time": _future_slot(3, 10)},
            headers=headers,
        )
        appointment_id = booking.json()["id"]
        response = await client.patch(
            f"/appointments/{appointment_id}/reschedule",
            json={"new_slot_time": _future_slot(3, 11)},
            headers=headers,
        )
    assert response.status_code == 200
    assert response.json()["slot_time"].startswith(_future_slot(3, 11)[:16])


async def test_reschedule_route_forbidden_403(test_doctor):
    owner_token = issue_token(uuid.uuid4())
    other_token = issue_token(uuid.uuid4())
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        booking = await client.post(
            "/appointments",
            json={"doctor_id": str(test_doctor.id), "slot_time": _future_slot(3, 10)},
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        appointment_id = booking.json()["id"]
        response = await client.patch(
            f"/appointments/{appointment_id}/reschedule",
            json={"new_slot_time": _future_slot(3, 11)},
            headers={"Authorization": f"Bearer {other_token}"},
        )
    assert response.status_code == 403


async def test_reschedule_route_validation_error_400(test_doctor):
    token = issue_token(uuid.uuid4())
    headers = {"Authorization": f"Bearer {token}"}
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        booking = await client.post(
            "/appointments",
            json={"doctor_id": str(test_doctor.id), "slot_time": _future_slot(3, 10)},
            headers=headers,
        )
        appointment_id = booking.json()["id"]
        response = await client.patch(
            f"/appointments/{appointment_id}/reschedule",
            json={"new_slot_time": _future_slot(3, 20)},  # outside 09:00-17:00
            headers=headers,
        )
    assert response.status_code == 400
    token_a = issue_token(uuid.uuid4())
    token_b = issue_token(uuid.uuid4())
    slot_a = _future_slot(3, 9)
    contested = _future_slot(3, 13)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        appt_a = await client.post(
            "/appointments",
            json={"doctor_id": str(test_doctor.id), "slot_time": slot_a},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        await client.post(
            "/appointments",
            json={"doctor_id": str(test_doctor.id), "slot_time": contested},
            headers={"Authorization": f"Bearer {token_b}"},
        )
        response = await client.patch(
            f"/appointments/{appt_a.json()['id']}/reschedule",
            json={"new_slot_time": contested},
            headers={"Authorization": f"Bearer {token_a}"},
        )
    assert response.status_code == 409