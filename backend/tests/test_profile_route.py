from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=False)
def clean_admin_prefs():
    from app.db.engine import db_session
    from app.db.repo_auth import AuthRepository
    auth = AuthRepository()
    user = auth.get_user_by_username("mock")
    if user:
        with db_session() as conn:
            conn.execute("DELETE FROM user_preferences WHERE user_id = ?", (user.id,))
    yield
    if user:
        with db_session() as conn:
            conn.execute("DELETE FROM user_preferences WHERE user_id = ?", (user.id,))


def _auth_header():
    resp = client.post("/auth/login", json={"username": "mock", "password": "mock"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_get_profile(clean_admin_prefs):
    headers = _auth_header()
    resp = client.get("/profile", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "username" in data
    assert "email" in data
    assert "notify_enabled" in data
    assert "notify_types" in data


def test_patch_profile_email(clean_admin_prefs):
    headers = _auth_header()
    resp = client.patch("/profile", json={"email": "admin@example.com"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "admin@example.com"


def test_patch_profile_notifications(clean_admin_prefs):
    headers = _auth_header()
    resp = client.patch(
        "/profile",
        json={"notify_enabled": True, "notify_types": ["news_match"]},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["notify_enabled"] is True
    assert resp.json()["notify_types"] == ["news_match"]
