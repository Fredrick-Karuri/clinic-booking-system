"""
app/tests/test_auth.py

Unit tests for the minimal bearer-token auth scheme.
"""

import uuid

import pytest
from fastapi import HTTPException

from app.api.deps import _verify_token, issue_token


def test_issue_and_verify_round_trip():
    patient_id = uuid.uuid4()
    token = issue_token(patient_id)
    resolved = _verify_token(token)
    assert resolved == patient_id


def test_verify_rejects_tampered_patient_id():
    patient_id = uuid.uuid4()
    token = issue_token(patient_id)
    other_patient_id = uuid.uuid4()
    # Swap in a different patient_id but keep the original signature —
    # this must NOT validate.
    _, signature = token.rsplit(".", 1)
    tampered = f"{other_patient_id}.{signature}"

    with pytest.raises(HTTPException) as exc_info:
        _verify_token(tampered)
    assert exc_info.value.status_code == 401


def test_verify_rejects_garbage_token():
    with pytest.raises(HTTPException) as exc_info:
        _verify_token("not-a-real-token")
    assert exc_info.value.status_code == 401


def test_verify_rejects_malformed_uuid():
    with pytest.raises(HTTPException) as exc_info:
        _verify_token("not-a-uuid.somesignature")
    assert exc_info.value.status_code == 401