# scripts/generate_mock_sql.py
# V0 - Initial implementation
#
# Standalone helper script — NOT a test file, no pytest involvement.
#
# Purpose:
#   Runs each entry in config/mock_responses.json through the full pipeline
#   and prints the resulting SQL so you can paste it back into the JSON file
#   as the "final_sql" field.
#
# Usage (run from project root):
#   python scripts/generate_mock_sql.py
#
# Output format:
#   [1] give me topaccount name for customer ASA
#       app_id : ABC_app (explicit)
#       SQL    : SELECT TOP 10000 ...
#
#   [2] give planname assoicated with packagekey 091222 in ABC
#       app_id : auto-detected
#       SQL    : SELECT TOP 10000 ...
#
# If an entry fails (e.g. APP_NOT_DETERMINED, NO_RELEVANT_TABLES):
#   [3] give all clients in ABC
#       app_id : auto-detected
#       ERROR  : NO_RELEVANT_TABLES — No relevant tables found ...
#
# After running:
#   Copy each SQL value into config/mock_responses.json as "final_sql".
#   Entries that show ERROR need fixing before they can be used in Part B tests.
#
# How it works:
#   - Uses create_app() + FastAPI TestClient — same code path as the real API
#   - Overrides app.state.llm_provider with MockLLMProvider() in JSON file mode
#     so it auto-matches each user_input from mock_responses.json
#   - Passes app_id explicitly in the request body when the entry has one
#   - Uses CLIENT_API_KEY from .env (same key the /v1/query endpoint expects)
#
# Why TestClient instead of wiring the pipeline manually:
#   - One line to boot the full app — no manual settings/schema/logger setup
#   - Guaranteed to produce the same SQL as the live endpoint
#   - If any pipeline stage changes, the script automatically reflects it

import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so src/ imports resolve correctly
# when the script is run from the project root with:
#   python scripts/generate_mock_sql.py
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from dotenv import load_dotenv

# Load .env so CLIENT_API_KEY and ENV are available
load_dotenv(PROJECT_ROOT / ".env")

from src.api.app import create_app
from src.llm.mock_provider import MockLLMProvider

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MOCK_RESPONSES_PATH = PROJECT_ROOT / "config" / "mock_responses.json"

# CLIENT_API_KEY is used by /v1/query (user-facing endpoint)
CLIENT_API_KEY = os.environ.get("CLIENT_API_KEY", "test-client-key-12345")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # --- Load mock_responses.json ---
    if not MOCK_RESPONSES_PATH.exists():
        print(f"ERROR: mock_responses.json not found at {MOCK_RESPONSES_PATH}")
        sys.exit(1)

    entries = json.loads(MOCK_RESPONSES_PATH.read_text(encoding="utf-8"))

    if not entries:
        print("ERROR: mock_responses.json is empty — nothing to run.")
        sys.exit(1)

    print(f"\nRunning {len(entries)} entries from mock_responses.json\n")
    print("=" * 70)

    # --- Boot the app once — reuse for all entries ---
    app = create_app(schema_dir="schemas")

    with TestClient(app, raise_server_exceptions=False) as client:
        # Override LLM provider with JSON file mode mock — auto-matches user_input
        # Must be set INSIDE the `with` block — lifespan runs on open and would
        # overwrite any override set before the block.
        client.app.state.llm_provider = MockLLMProvider()

        for idx, entry in enumerate(entries, start=1):
            user_input = entry.get("user_input", "")
            explicit_app_id = entry.get("app_id")  # None if not present in entry

            # --- Build request body ---
            body = {
                "nl_query": user_input,
                "user_id":  "generate-script",
            }
            if explicit_app_id:
                body["app_id"] = explicit_app_id

            app_id_note = (
                f"{explicit_app_id} (explicit)"
                if explicit_app_id
                else "auto-detected"
            )

            # --- POST to /v1/query ---
            response = client.post(
                "/v1/query",
                json=body,
                headers={"X-API-Key": CLIENT_API_KEY},
            )

            print(f"\n[{idx}] {user_input}")
            print(f"      app_id : {app_id_note}")

            if response.status_code != 200:
                print(
                    f"      HTTP   : {response.status_code} — "
                    f"{response.text[:120]}"
                )
                continue

            data = response.json()

            if data.get("status") == "success":
                sql = data.get("data", {}).get("sql", "")
                print(f"      STATUS : success")
                print(f"      SQL    :\n")
                # Print each SQL line indented for readability
                for line in sql.splitlines():
                    print(f"        {line}")
            else:
                errors = data.get("errors", [])
                if errors:
                    err = errors[0]
                    print(
                        f"      STATUS : failed\n"
                        f"      ERROR  : {err.get('code')} — "
                        f"{err.get('message', '')[:100]}"
                    )
                else:
                    print(f"      STATUS : failed (no error detail)")

    print("\n" + "=" * 70)
    print("\nDone. Copy each SQL block into mock_responses.json as \"final_sql\".")
    print(
        "Entries showing ERROR need investigation before "
        "they can be used in Part B E2E tests.\n"
    )


if __name__ == "__main__":
    main()
