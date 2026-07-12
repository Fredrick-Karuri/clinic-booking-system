"""
app/tests/test_health.py

Trivial but worth having explicitly: the health check endpoint used
by deployment platforms and CI smoke tests.
"""

import httpx
import pytest
from httpx import ASGITransport

from app.main import app

pytestmark = pytest.mark.asyncio


async def test_health_check():
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}