import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_register_user_success():
    payload = {
        "username": "surveyor_john",
        "email": "john@geosurvey.com",
        "password": "securepassword123",
        "full_name": "John Doe",
    }
    res = client.post("/api/auth/register", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert "access_token" in data
    assert data["user"]["username"] == "surveyor_john"
    assert data["user"]["email"] == "john@geosurvey.com"


def test_register_duplicate_username():
    payload = {
        "username": "surveyor_john",
        "email": "other_john@geosurvey.com",
        "password": "securepassword123",
    }
    res = client.post("/api/auth/register", json=payload)
    assert res.status_code == 400
    assert "already taken" in res.json()["detail"]


def test_login_success():
    payload = {
        "username_or_email": "surveyor_john",
        "password": "securepassword123",
    }
    res = client.post("/api/auth/login", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    token = data["access_token"]

    # Test /api/auth/me with Bearer token
    me_res = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me_res.status_code == 200
    assert me_res.json()["username"] == "surveyor_john"


def test_login_invalid_password():
    payload = {
        "username_or_email": "surveyor_john",
        "password": "wrongpassword",
    }
    res = client.post("/api/auth/login", json=payload)
    assert res.status_code == 401


def test_get_me_unauthorized():
    res = client.get("/api/auth/me")
    assert res.status_code == 401
