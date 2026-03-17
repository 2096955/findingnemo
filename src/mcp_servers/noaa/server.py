"""NOAA Weather & NDBC Buoy MCP server.

Provides marine forecast and buoy observation tools via NOAA Weather API
and NDBC real-time data feeds.

API: https://api.weather.gov (free, requires User-Agent header)
NDBC: https://www.ndbc.noaa.gov/data/realtime2/{station}.txt
"""

import os
import sys
import logging

from fastmcp import FastMCP

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from mcp_servers._http import (
    resilient_get,
    CircuitOpenError,
    RetryExhaustedError,
    raise_or_return_error,
)
from mcp_servers._security import sanitize_query

log = logging.getLogger(__name__)

mcp = FastMCP("noaa")

WEATHER_API_BASE = "https://api.weather.gov"
NDBC_BASE = "https://www.ndbc.noaa.gov/data/realtime2"

USER_AGENT = "WhaleAgent/1.0 (whale-vessel-collision-avoidance)"


def _weather_headers() -> dict:
    """Return headers required by the NOAA Weather API."""
    return {
        "User-Agent": USER_AGENT,
        "Accept": "application/geo+json",
    }


@mcp.tool()
async def get_marine_forecast(
    grid_office: str, grid_x: int, grid_y: int
) -> dict:
    """Get NOAA marine weather forecast for a specific grid point.

    Args:
        grid_office: NWS grid office code (e.g. 'SEW', 'LOX', 'OKX').
        grid_x: Grid X coordinate.
        grid_y: Grid Y coordinate.

    Returns forecast periods with wind, wave, and weather details.
    """
    safe_office = sanitize_query(grid_office, max_len=10)
    if not safe_office:
        return {"error": "Empty grid_office after sanitization", "periods": []}

    url = f"{WEATHER_API_BASE}/gridpoints/{safe_office}/{grid_x},{grid_y}/forecast"

    try:
        response = await resilient_get(url, headers=_weather_headers())
    except (CircuitOpenError, RetryExhaustedError) as exc:
        return raise_or_return_error(exc, "noaa", "get_marine_forecast", periods=[])

    if response.status_code != 200:
        return {
            "error": f"NOAA API returned {response.status_code}",
            "periods": [],
        }

    data = response.json()
    properties = data.get("properties", {})
    raw_periods = properties.get("periods", [])

    periods = []
    for p in raw_periods[:14]:  # Up to 7 days (day + night)
        periods.append({
            "name": p.get("name", ""),
            "start_time": p.get("startTime", ""),
            "end_time": p.get("endTime", ""),
            "temperature": p.get("temperature"),
            "temperature_unit": p.get("temperatureUnit", ""),
            "wind_speed": p.get("windSpeed", ""),
            "wind_direction": p.get("windDirection", ""),
            "short_forecast": p.get("shortForecast", ""),
            "detailed_forecast": p.get("detailedForecast", ""),
        })

    return {
        "success": True,
        "grid_office": safe_office,
        "grid_x": grid_x,
        "grid_y": grid_y,
        "returned_count": len(periods),
        "periods": periods,
    }


@mcp.tool()
async def get_buoy_data(station_id: str) -> dict:
    """Get real-time buoy observations from NDBC.

    Args:
        station_id: NDBC station identifier (e.g. '46029', '44013').

    Returns latest observation with wave height, water temperature,
    wind speed/direction, and atmospheric pressure.
    """
    safe_station = sanitize_query(station_id, max_len=20)
    if not safe_station:
        return {"error": "Empty station_id after sanitization", "observation": {}}

    url = f"{NDBC_BASE}/{safe_station}.txt"

    try:
        response = await resilient_get(
            url, headers={"User-Agent": USER_AGENT}
        )
    except (CircuitOpenError, RetryExhaustedError) as exc:
        return raise_or_return_error(exc, "noaa", "get_buoy_data", observation={})

    if response.status_code != 200:
        return {
            "error": f"NDBC returned {response.status_code}",
            "observation": {},
        }

    text = response.text
    lines = text.strip().split("\n")
    if len(lines) < 3:
        return {"error": "Insufficient data from NDBC", "observation": {}}

    # Line 0: header names, Line 1: units, Line 2+: data rows
    headers_line = lines[0].split()
    data_line = lines[2].split()

    def _get(name: str) -> str:
        try:
            idx = headers_line.index(name)
            val = data_line[idx]
            return val if val != "MM" else None
        except (ValueError, IndexError):
            return None

    observation = {
        "station_id": safe_station,
        "year": _get("#YY") or _get("YY"),
        "month": _get("MM"),
        "day": _get("DD"),
        "hour": _get("hh"),
        "minute": _get("mm"),
        "wind_direction_deg": _get("WDIR"),
        "wind_speed_mps": _get("WSPD"),
        "gust_speed_mps": _get("GST"),
        "wave_height_m": _get("WVHT"),
        "dominant_wave_period_s": _get("DPD"),
        "average_wave_period_s": _get("APD"),
        "mean_wave_direction_deg": _get("MWD"),
        "atmospheric_pressure_hpa": _get("PRES"),
        "air_temperature_c": _get("ATMP"),
        "water_temperature_c": _get("WTMP"),
        "dewpoint_c": _get("DEWP"),
        "visibility_nm": _get("VIS"),
    }

    return {
        "success": True,
        "observation": observation,
    }


if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=9001)
