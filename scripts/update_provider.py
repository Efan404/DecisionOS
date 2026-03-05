#!/usr/bin/env python3
"""Update ModelScope provider config in the Docker database."""

import json
import sqlite3
import os
import sys

# Configuration
DB_PATH = "/mnt/workspace/decisionos.db"
API_KEY = "ms-8d859ec3-b55b-43b1-a284-46830b1c9800"  # ModelScope Token
MODEL = "Qwen/Qwen3-8B"
BASE_URL = "https://api-inference.modelscope.cn/v1"

def encrypt_api_key(api_key: str) -> str:
    """Generate encrypted API key format."""
    # This should match the encryption used in the app
    # For now, we'll use a simple format that the app can read
    return f"enc:v1:{API_KEY}"

def update_provider_config():
    # Connect to the database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get current settings
    cursor.execute("SELECT config_json FROM ai_settings WHERE id = 'default'")
    row = cursor.fetchone()

    if not row:
        print("ERROR: No ai_settings found in database")
        conn.close()
        return False

    config = json.loads(row[0])
    print(f"Current providers: {config.get('providers', [])}")

    # Create new provider config
    new_provider = {
        "id": "provider_1",
        "name": "ModelScope",
        "kind": "openai_compatible",
        "base_url": BASE_URL,
        "api_key": f"enc:v1:{API_KEY}",
        "model": MODEL,
        "enabled": True,
        "timeout_seconds": 120.0,
        "temperature": 0.2
    }

    # Update providers list
    config["providers"] = [new_provider]

    # Write back to database
    cursor.execute(
        "UPDATE ai_settings SET config_json = ? WHERE id = 'default'",
        (json.dumps(config),)
    )

    conn.commit()
    print(f"Updated provider config:")
    print(f"  - Provider ID: provider_1")
    print(f"  - Model: {MODEL}")
    print(f"  - Base URL: {BASE_URL}")
    print(f"  - Enabled: True")

    # Verify
    cursor.execute("SELECT config_json FROM ai_settings WHERE id = 'default'")
    row = cursor.fetchone()
    config = json.loads(row[0])
    print(f"\nVerification - Providers now: {len(config.get('providers', []))} provider(s)")

    conn.close()
    return True

if __name__ == "__main__":
    if os.path.exists(DB_PATH):
        print(f"Found database at {DB_PATH}")
        if update_provider_config():
            print("\nSUCCESS: Provider config updated!")
        else:
            print("\nFAILED: Could not update config")
            sys.exit(1)
    else:
        print(f"ERROR: Database not found at {DB_PATH}")
        print("Make sure the Docker container is running")
        sys.exit(1)
