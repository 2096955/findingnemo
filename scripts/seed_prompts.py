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
import traceback
import urllib.request
import urllib.error
from pathlib import Path


GATEWAY_PORT = os.environ.get("FASTAPI_PORT", os.environ.get("PORT", "8080"))
# Use 127.0.0.1 instead of localhost — avoids DNS resolution issues in gVisor
GATEWAY_URL = f"http://127.0.0.1:{GATEWAY_PORT}"
SEED_FILE = Path(__file__).parent.parent / "data" / "seed_prompts.json"
MAX_WAIT_SECONDS = 180
INITIAL_DELAY = 10  # Give SAM time to start before polling


def log(msg: str) -> None:
    """Print with flush to ensure output appears in container logs."""
    print(f"[seed_prompts] {msg}", flush=True)


def wait_for_gateway() -> bool:
    """Poll the gateway until the prompts endpoint responds or we time out."""
    log(f"Waiting up to {MAX_WAIT_SECONDS}s for gateway at {GATEWAY_URL}")
    log(f"Sleeping {INITIAL_DELAY}s before first poll...")
    time.sleep(INITIAL_DELAY)

    deadline = time.monotonic() + MAX_WAIT_SECONDS
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        try:
            with urllib.request.urlopen(
                f"{GATEWAY_URL}/api/v1/prompts/groups/all", timeout=5
            ) as r:
                if r.status == 200:
                    log(f"Gateway ready after {attempt} attempts")
                    return True
        except urllib.error.URLError as e:
            if attempt <= 3 or attempt % 10 == 0:
                log(f"  attempt {attempt}: {e.reason}")
        except Exception as e:
            if attempt <= 3 or attempt % 10 == 0:
                log(f"  attempt {attempt}: {type(e).__name__}: {e}")
        time.sleep(2)

    log(f"Gateway not ready after {MAX_WAIT_SECONDS}s ({attempt} attempts)")
    return False


def get_existing_names() -> set:
    """Return set of existing prompt group names."""
    try:
        with urllib.request.urlopen(
            f"{GATEWAY_URL}/api/v1/prompts/groups/all", timeout=5
        ) as r:
            data = json.loads(r.read())
            groups = data if isinstance(data, list) else data.get("groups", [])
            return {g.get("name", "") for g in groups}
    except Exception as e:
        log(f"Warning: could not fetch existing prompts: {e}")
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
        body = ""
        try:
            body = e.read().decode()[:200]
        except Exception:
            pass
        log(f"HTTP {e.code} creating '{prompt['name']}': {body}")
        return False
    except Exception as e:
        log(f"Error creating '{prompt['name']}': {e}")
        return False


def main():
    log("Starting...")
    log(f"GATEWAY_URL={GATEWAY_URL}")
    log(f"SEED_FILE={SEED_FILE}")
    log(f"SEED_FILE exists={SEED_FILE.exists()}")

    if not SEED_FILE.exists():
        log(f"Seed file not found — skipping")
        return

    if not wait_for_gateway():
        log("Gateway not ready — skipping seed")
        return

    prompts = json.loads(SEED_FILE.read_text())
    log(f"Loaded {len(prompts)} prompts from seed file")

    existing = get_existing_names()
    log(f"Found {len(existing)} existing prompt(s)")

    created = 0
    skipped = 0
    failed = 0
    for prompt in prompts:
        name = prompt.get("name", "")
        if name in existing:
            log(f"  SKIP  {name}")
            skipped += 1
        else:
            if create_prompt(prompt):
                log(f"  OK    {name}")
                created += 1
            else:
                log(f"  FAIL  {name}")
                failed += 1

    log(f"Done — created {created}, skipped {skipped}, failed {failed}")

    # Verify by re-fetching
    final = get_existing_names()
    log(f"Verification: {len(final)} prompts now in gateway")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log(f"FATAL unhandled exception:\n{traceback.format_exc()}")
        sys.exit(1)
