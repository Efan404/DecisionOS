from __future__ import annotations

import os
os.environ.setdefault("DECISIONOS_SEED_ADMIN_USERNAME", "admin")
os.environ.setdefault("DECISIONOS_SEED_ADMIN_PASSWORD", "AIHackathon20250225!")

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def _auth_header():
    resp = client.post("/auth/login", json={"username": "admin", "password": "AIHackathon20250225!"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_get_profile():
    headers = _auth_header()
    resp = client.get("/profile", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "username" in data
    assert "email" in data
    assert "notify_enabled" in data
    assert "notify_types" in data


def test_patch_profile_email():
    headers = _auth_header()
    resp = client.patch("/profile", json={"email": "admin@example.com"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "admin@example.com"


def test_patch_profile_notifications():
    headers = _auth_header()
    resp = client.patch(
        "/profile",
        json={"notify_enabled": True, "notify_types": ["news_match"]},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["notify_enabled"] is True
    assert resp.json()["notify_types"] == ["news_match"]
