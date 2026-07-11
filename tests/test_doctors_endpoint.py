"""
app/tests/test_doctors_endpoint.py

HTTP-level tests for GET /doctors/{id}/availability,
covering the route's own 404/422 branches.
"""

import uuid

import httpx
import pytest
from httpx import ASGITransport

from app.main import app

pytestmark = pytest.mark.asyncio


async def test_availability_unknown_doctor_404():
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/doctors/{uuid.uuid4()}/availability?date=2026-08-20")
    assert response.status_code == 404


async def test_availability_malformed_date_422(test_doctor):
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/doctors/{test_doctor.id}/availability?date=not-a-date")
    assert response.status_code == 422


async def test_availability_valid_returns_slots(test_doctor):
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/doctors/{test_doctor.id}/availability?date=2026-08-20")
    assert response.status_code == 200
    body = response.json()
    assert body["doctor_id"] == str(test_doctor.id)
    assert len(body["available_slots"]) > 0