import os
import pytest

def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONOS_CHROMA_PATH", "")
    monkeypatch.setenv("DECISIONOS_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("DECISIONOS_AUTH_DISABLED", "1")
    from app.core.settings import get_settings
    get_settings.cache_clear()
    from app.db.bootstrap import initialize_database
    initialize_database()
    from fastapi.testclient import TestClient
    from app.main import create_app
    return TestClient(create_app())

def test_get_search_settings_returns_empty_providers(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    resp = client.get("/settings/search")
    assert resp.status_code == 200
    data = resp.json()
    assert "providers" in data
    assert isinstance(data["providers"], list)
    assert data["providers"] == []

def test_patch_search_settings_saves_hn_provider(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    payload = {
        "providers": [{
            "id": "hn1",
            "name": "HN Algolia",
            "kind": "hn_algolia",
            "enabled": True,
            "max_results": 5,
            "timeout_seconds": 10.0,
        }]
    }
    resp = client.patch("/settings/search", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["providers"]) == 1
    assert data["providers"][0]["id"] == "hn1"
    assert data["providers"][0]["kind"] == "hn_algolia"

def test_patch_search_settings_masks_api_key(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    payload = {
        "providers": [{
            "id": "exa1",
            "name": "Exa",
            "kind": "exa",
            "api_key": "sk-test-supersecretkey123",
            "enabled": True,
            "max_results": 5,
            "timeout_seconds": 15.0,
        }]
    }
    resp = client.patch("/settings/search", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    returned_key = data["providers"][0].get("api_key")
    # Should be masked, not the raw key
    assert returned_key != "sk-test-supersecretkey123"
    assert "****" in (returned_key or "")
