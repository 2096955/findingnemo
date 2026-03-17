"""Tests for the Whale Alert MCP server."""

import sys
import os
import pytest
import respx
import httpx
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from mcp_servers.whale_alert import server as whale_alert_module

get_whale_sightings = whale_alert_module.get_whale_sightings.fn


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SIGHTINGS_RESPONSE = {
    "events": [
        {
            "id": "evt-001",
            "type": "sighting",
            "species": "blue whale",
            "latitude": 34.05,
            "longitude": -119.50,
            "number": 2,
            "eventdate": "2026-03-17T06:30:00Z",
            "description": "Two blue whales spotted heading north",
            "source": "citizen_report",
        },
        {
            "id": "evt-002",
            "type": "sighting",
            "species": "humpback whale",
            "latitude": 34.10,
            "longitude": -119.45,
            "number": 1,
            "eventdate": "2026-03-16T14:00:00Z",
            "description": "Single humpback whale near shipping lane",
            "source": "vessel_report",
        },
    ]
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_whale_sightings_success():
    with patch.object(whale_alert_module, "WHALE_ALERT_API_KEY", "test-key-123"):
        with respx.mock:
            respx.get("https://www.whalealert.org/api/v1/events").mock(
                return_value=httpx.Response(200, json=SIGHTINGS_RESPONSE)
            )

            result = await get_whale_sightings(34.0, -119.5, radius_km=50)

    assert result["success"] is True
    assert result["returned_count"] == 2
    assert result["center_latitude"] == 34.0
    assert result["center_longitude"] == -119.5
    assert result["radius_km"] == 50

    first = result["sightings"][0]
    assert first["species"] == "blue whale"
    assert first["number_sighted"] == 2
    assert first["source"] == "citizen_report"


@pytest.mark.asyncio
async def test_get_whale_sightings_no_api_key():
    with patch.object(whale_alert_module, "WHALE_ALERT_API_KEY", ""):
        result = await get_whale_sightings(34.0, -119.5)

    assert "error" in result
    assert "WHALE_ALERT_API_KEY" in result["error"]
    assert result["sightings"] == []


@pytest.mark.asyncio
async def test_get_whale_sightings_api_error():
    with patch.object(whale_alert_module, "WHALE_ALERT_API_KEY", "test-key-123"):
        with respx.mock:
            respx.get("https://www.whalealert.org/api/v1/events").mock(
                return_value=httpx.Response(403, json={"error": "Forbidden"})
            )

            result = await get_whale_sightings(34.0, -119.5)

    assert "error" in result
    assert result["sightings"] == []


@pytest.mark.asyncio
async def test_get_whale_sightings_invalid_latitude():
    with patch.object(whale_alert_module, "WHALE_ALERT_API_KEY", "test-key-123"):
        result = await get_whale_sightings(100.0, -119.5)

    assert "error" in result
    assert "Latitude" in result["error"]


@pytest.mark.asyncio
async def test_get_whale_sightings_radius_clamped():
    with patch.object(whale_alert_module, "WHALE_ALERT_API_KEY", "test-key-123"):
        with respx.mock:
            respx.get("https://www.whalealert.org/api/v1/events").mock(
                return_value=httpx.Response(200, json={"events": []})
            )

            result = await get_whale_sightings(34.0, -119.5, radius_km=9999)

    assert result["success"] is True
    assert result["radius_km"] == 500.0  # Clamped to max
