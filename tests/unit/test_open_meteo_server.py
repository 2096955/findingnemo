"""Tests for the Open-Meteo Marine MCP server."""

import sys
import os
import pytest
import respx
import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from mcp_servers.open_meteo import server as open_meteo_module

get_marine_conditions = open_meteo_module.get_marine_conditions.fn


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MARINE_RESPONSE = {
    "latitude": 34.0,
    "longitude": -119.0,
    "hourly": {
        "time": [
            "2026-03-17T00:00",
            "2026-03-17T01:00",
            "2026-03-17T02:00",
        ],
        "wave_height": [1.5, 1.6, 1.4],
        "wave_direction": [270, 275, 268],
        "wave_period": [8.0, 8.2, 7.9],
        "swell_wave_height": [1.2, 1.3, 1.1],
        "swell_wave_direction": [260, 262, 258],
        "swell_wave_period": [12.0, 12.1, 11.8],
        "ocean_current_velocity": [0.15, 0.18, 0.12],
        "ocean_current_direction": [180, 185, 175],
    },
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_marine_conditions_success():
    with respx.mock:
        respx.get("https://marine-api.open-meteo.com/v1/marine").mock(
            return_value=httpx.Response(200, json=MARINE_RESPONSE)
        )

        result = await get_marine_conditions(34.0, -119.0, forecast_days=1)

    assert result["success"] is True
    assert result["latitude"] == 34.0
    assert result["longitude"] == -119.0
    assert result["returned_count"] == 3

    first = result["hourly"][0]
    assert first["time"] == "2026-03-17T00:00"
    assert first["wave_height_m"] == 1.5
    assert first["wave_direction_deg"] == 270
    assert first["swell_wave_height_m"] == 1.2
    assert first["ocean_current_velocity_ms"] == 0.15


@pytest.mark.asyncio
async def test_get_marine_conditions_api_error():
    """Non-retryable HTTP error returns a structured error dict."""
    with respx.mock:
        respx.get("https://marine-api.open-meteo.com/v1/marine").mock(
            return_value=httpx.Response(400, json={"reason": "Bad request"})
        )

        result = await get_marine_conditions(34.0, -119.0)

    assert "error" in result
    assert result["hourly"] == []


@pytest.mark.asyncio
async def test_get_marine_conditions_invalid_latitude():
    result = await get_marine_conditions(95.0, -119.0)
    assert "error" in result
    assert "Latitude" in result["error"]


@pytest.mark.asyncio
async def test_get_marine_conditions_invalid_longitude():
    result = await get_marine_conditions(34.0, 200.0)
    assert "error" in result
    assert "Longitude" in result["error"]


@pytest.mark.asyncio
async def test_get_marine_conditions_forecast_days_clamped():
    with respx.mock:
        route = respx.get("https://marine-api.open-meteo.com/v1/marine").mock(
            return_value=httpx.Response(200, json=MARINE_RESPONSE)
        )

        result = await get_marine_conditions(34.0, -119.0, forecast_days=99)

    assert result["success"] is True
    assert result["forecast_days"] == 16  # Clamped to max
