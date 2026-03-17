"""Tests for the NOAA Weather & NDBC Buoy MCP server."""

import sys
import os
import pytest
import respx
import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from mcp_servers.noaa import server as noaa_module

get_marine_forecast = noaa_module.get_marine_forecast.fn
get_buoy_data = noaa_module.get_buoy_data.fn


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FORECAST_RESPONSE = {
    "properties": {
        "periods": [
            {
                "name": "Today",
                "startTime": "2026-03-17T06:00:00-07:00",
                "endTime": "2026-03-17T18:00:00-07:00",
                "temperature": 58,
                "temperatureUnit": "F",
                "windSpeed": "15 mph",
                "windDirection": "NW",
                "shortForecast": "Partly Cloudy",
                "detailedForecast": "Partly cloudy with NW winds around 15 mph.",
            },
            {
                "name": "Tonight",
                "startTime": "2026-03-17T18:00:00-07:00",
                "endTime": "2026-03-18T06:00:00-07:00",
                "temperature": 45,
                "temperatureUnit": "F",
                "windSpeed": "10 mph",
                "windDirection": "W",
                "shortForecast": "Mostly Clear",
                "detailedForecast": "Mostly clear skies overnight.",
            },
        ]
    }
}

BUOY_TEXT = """#YY  MM DD hh mm WDIR WSPD GST  WVHT   DPD   APD MWD   PRES  ATMP  WTMP  DEWP  VIS PTDY  TIDE
#yr  mo dy hr mn deg m/s  m/s     m   sec   sec deg    hPa  degC  degC  degC  nmi  hPa    ft
2026 03 17 08 00 280  5.2  7.1   1.8  10.0   6.5 270 1015.2  12.3  14.5  10.1   MM   MM    MM
2026 03 17 07 00 275  4.8  6.5   1.7   9.8   6.3 268 1015.5  12.0  14.3  10.0   MM   MM    MM
"""


# ---------------------------------------------------------------------------
# Tests: get_marine_forecast
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_marine_forecast_success():
    with respx.mock:
        respx.get(
            "https://api.weather.gov/gridpoints/SEW/100,50/forecast"
        ).mock(return_value=httpx.Response(200, json=FORECAST_RESPONSE))

        result = await get_marine_forecast("SEW", 100, 50)

    assert result["success"] is True
    assert result["grid_office"] == "SEW"
    assert result["returned_count"] == 2
    assert result["periods"][0]["name"] == "Today"
    assert result["periods"][0]["temperature"] == 58
    assert result["periods"][1]["short_forecast"] == "Mostly Clear"


@pytest.mark.asyncio
async def test_get_marine_forecast_api_error():
    with respx.mock:
        respx.get(
            "https://api.weather.gov/gridpoints/BAD/0,0/forecast"
        ).mock(return_value=httpx.Response(404, json={"detail": "Not found"}))

        result = await get_marine_forecast("BAD", 0, 0)

    assert "error" in result
    assert result["periods"] == []


@pytest.mark.asyncio
async def test_get_marine_forecast_empty_office():
    result = await get_marine_forecast("", 0, 0)
    assert "error" in result
    assert result["periods"] == []


# ---------------------------------------------------------------------------
# Tests: get_buoy_data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_buoy_data_success():
    with respx.mock:
        respx.get(
            "https://www.ndbc.noaa.gov/data/realtime2/46029.txt"
        ).mock(return_value=httpx.Response(200, text=BUOY_TEXT))

        result = await get_buoy_data("46029")

    assert result["success"] is True
    obs = result["observation"]
    assert obs["station_id"] == "46029"
    assert obs["wave_height_m"] == "1.8"
    assert obs["water_temperature_c"] == "14.5"
    assert obs["wind_speed_mps"] == "5.2"
    assert obs["wind_direction_deg"] == "280"
    assert obs["atmospheric_pressure_hpa"] == "1015.2"


@pytest.mark.asyncio
async def test_get_buoy_data_station_not_found():
    with respx.mock:
        respx.get(
            "https://www.ndbc.noaa.gov/data/realtime2/99999.txt"
        ).mock(return_value=httpx.Response(404))

        result = await get_buoy_data("99999")

    assert "error" in result
    assert result["observation"] == {}


@pytest.mark.asyncio
async def test_get_buoy_data_empty_station():
    result = await get_buoy_data("")
    assert "error" in result
    assert result["observation"] == {}
