#!/usr/bin/env python3
"""
Seed default prompt templates into the Whale Agent webui gateway.

Runs on every container startup (prompts are stored in ephemeral SQLite).
If a prompt group with the same name already exists, it is skipped.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path


GATEWAY_PORT = os.environ.get("FASTAPI_PORT", os.environ.get("PORT", "8080"))
GATEWAY_URL = f"http://localhost:{GATEWAY_PORT}"
SEED_FILE = Path(__file__).parent.parent / "data" / "seed_prompts.json"
MAX_WAIT_SECONDS = 180


def wait_for_gateway() -> bool:
    """Poll the gateway until it responds or we time out."""
    deadline = time.monotonic() + MAX_WAIT_SECONDS
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{GATEWAY_URL}/api/v1/prompts/groups/all", timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(2)
    return False


def get_existing_names() -> set:
    """Return set of existing prompt group names."""
    try:
        with urllib.request.urlopen(f"{GATEWAY_URL}/api/v1/prompts/groups/all", timeout=5) as r:
            data = json.loads(r.read())
            groups = data if isinstance(data, list) else data.get("groups", [])
            return {g.get("name", "") for g in groups}
    except Exception as e:
        print(f"[seed_prompts] Warning: could not fetch existing prompts: {e}")
        return set()


def create_prompt(prompt: dict) -> bool:
    """POST a single prompt group. Returns True on success."""
    payload = json.dumps(prompt).encode()
    req = urllib.request.Request(
        f"{GATEWAY_URL}/api/v1/prompts/groups",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status in (200, 201)
    except urllib.error.HTTPError as e:
        print(f"[seed_prompts] HTTP {e.code} creating '{prompt['name']}': {e.read().decode()[:200]}")
        return False
    except Exception as e:
        print(f"[seed_prompts] Error creating '{prompt['name']}': {e}")
        return False


def main():
    print("[seed_prompts] Waiting for gateway to be ready...")
    if not wait_for_gateway():
        print("[seed_prompts] Gateway not ready after timeout — skipping seed")
        sys.exit(0)

    if not SEED_FILE.exists():
        print(f"[seed_prompts] Seed file not found: {SEED_FILE} — skipping")
        sys.exit(0)

    prompts = json.loads(SEED_FILE.read_text())
    existing = get_existing_names()
    print(f"[seed_prompts] Found {len(existing)} existing prompt(s)")

    created = 0
    skipped = 0
    for prompt in prompts:
        name = prompt.get("name", "")
        if name in existing:
            print(f"[seed_prompts]   SKIP  {name}")
            skipped += 1
        else:
            if create_prompt(prompt):
                print(f"[seed_prompts]   OK    {name}")
                created += 1
            else:
                print(f"[seed_prompts]   FAIL  {name}")

    print(f"[seed_prompts] Done — created {created}, skipped {skipped}")


if __name__ == "__main__":
    main()
