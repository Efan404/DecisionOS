from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest

from tests.test_api_ideas_and_agents import _AsgiTestClient
from tests._test_env import ensure_required_seed_env


class AISettingsApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        ensure_required_seed_env()
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmpdir.name, "decisionos-ai-settings-test.db")
        os.environ["DECISIONOS_DB_PATH"] = self.db_path
        os.environ["DECISIONOS_AUTH_DISABLED"] = "1"

        from app.core.settings import get_settings
        from app.main import create_app

        get_settings.cache_clear()
        self.client = _AsgiTestClient(create_app())

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_get_default_ai_settings(self) -> None:
        status, payload = self.client.request_json("GET", "/settings/ai")
        self.assertEqual(status, 200)
        assert payload is not None
        self.assertEqual(payload["id"], "default")
        self.assertEqual(payload["providers"], [])
        # routing field must no longer exist
        self.assertNotIn("routing", payload)

    def test_patch_single_enabled_provider_round_trip(self) -> None:
        patch_status, patch_payload = self.client.request_json(
            "PATCH",
            "/settings/ai",
            {
                "providers": [
                    {
                        "id": "openai_main",
                        "name": "OpenAI Main",
                        "kind": "openai_compatible",
                        "base_url": "https://api.openai.com/v1",
                        "api_key": "sk-local-test",
                        "model": "gpt-4o-mini",
                        "enabled": True,
                        "timeout_seconds": 20,
                        "temperature": 0.2,
                    },
                ]
            },
        )
        self.assertEqual(patch_status, 200)
        assert patch_payload is not None
        self.assertEqual(len(patch_payload["providers"]), 1)
        self.assertTrue(patch_payload["providers"][0]["enabled"])

        # GET must return masked key (first 4 + **** + last 4)
        get_status, get_payload = self.client.request_json("GET", "/settings/ai")
        self.assertEqual(get_status, 200)
        assert get_payload is not None
        self.assertEqual(get_payload["providers"][0]["api_key"], "sk-l****test")

        # api_key must be encrypted on disk
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT config_json FROM ai_settings WHERE id = ?",
                ("default",),
            ).fetchone()
            assert row is not None
            raw_config = str(row[0])
            self.assertNotIn("sk-local-test", raw_config)
            self.assertIn("enc:v1:", raw_config)

    def test_patch_two_enabled_providers_returns_422(self) -> None:
        status, _payload = self.client.request_json(
            "PATCH",
            "/settings/ai",
            {
                "providers": [
                    {
                        "id": "provider_a",
                        "name": "Provider A",
                        "kind": "openai_compatible",
                        "base_url": "https://api.openai.com/v1",
                        "enabled": True,
                        "timeout_seconds": 20,
                        "temperature": 0.2,
                    },
                    {
                        "id": "provider_b",
                        "name": "Provider B",
                        "kind": "openai_compatible",
                        "base_url": "http://127.0.0.1:8080/generate",
                        "enabled": True,
                        "timeout_seconds": 20,
                        "temperature": 0.2,
                    },
                ]
            },
        )
        self.assertEqual(status, 422)

    def test_patch_two_providers_one_disabled_is_ok(self) -> None:
        status, payload = self.client.request_json(
            "PATCH",
            "/settings/ai",
            {
                "providers": [
                    {
                        "id": "provider_a",
                        "name": "Provider A",
                        "kind": "openai_compatible",
                        "base_url": "https://api.openai.com/v1",
                        "enabled": True,
                        "timeout_seconds": 20,
                        "temperature": 0.2,
                    },
                    {
                        "id": "provider_b",
                        "name": "Provider B",
                        "kind": "openai_compatible",
                        "base_url": "http://127.0.0.1:8080/generate",
                        "enabled": False,
                        "timeout_seconds": 20,
                        "temperature": 0.2,
                    },
                ]
            },
        )
        self.assertEqual(status, 200)
        assert payload is not None
        self.assertEqual(len(payload["providers"]), 2)

    def test_test_provider_endpoint_returns_failure_for_unreachable_provider(self) -> None:
        status, payload = self.client.request_json(
            "POST",
            "/settings/ai/test",
            {
                "provider": {
                    "id": "unreachable_local",
                    "name": "Unreachable Local",
                    "kind": "openai_compatible",
                    "base_url": "http://127.0.0.1:65533/generate",
                    "enabled": True,
                    "timeout_seconds": 1,
                    "temperature": 0.2,
                }
            },
        )
        self.assertEqual(status, 200)
        assert payload is not None
        self.assertEqual(payload["ok"], False)
        self.assertGreaterEqual(payload["latency_ms"], 0)


if __name__ == "__main__":
    unittest.main()
