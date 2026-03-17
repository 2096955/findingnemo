"""Open-Meteo Marine MCP server.

Provides marine weather and ocean condition data via the Open-Meteo
Marine API (free, no API key required).

API: https://marine-api.open-meteo.com/v1/marine
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

log = logging.getLogger(__name__)

mcp = FastMCP("open_meteo")

MARINE_API_URL = "https://marine-api.open-meteo.com/v1/marine"


@mcp.tool()
async def get_marine_conditions(
    latitude: float, longitude: float, forecast_days: int = 3
) -> dict:
    """Get marine weather conditions for a location.

    Args:
        latitude: Latitude of the location (-90 to 90).
        longitude: Longitude of the location (-180 to 180).
        forecast_days: Number of forecast days (1-16, default 3).

    Returns hourly marine data including wave height, swell period,
    ocean current velocity, and sea surface temperature.
    """
    if not (-90 <= latitude <= 90):
        return {"error": "Latitude must be between -90 and 90", "hourly": []}
    if not (-180 <= longitude <= 180):
        return {"error": "Longitude must be between -180 and 180", "hourly": []}

    forecast_days = max(1, min(16, forecast_days))

    params = {
        "latitude": str(latitude),
        "longitude": str(longitude),
        "hourly": ",".join([
            "wave_height",
            "wave_direction",
            "wave_period",
            "swell_wave_height",
            "swell_wave_direction",
            "swell_wave_period",
            "ocean_current_velocity",
            "ocean_current_direction",
        ]),
        "forecast_days": str(forecast_days),
    }

    try:
        response = await resilient_get(MARINE_API_URL, params=params)
    except (CircuitOpenError, RetryExhaustedError) as exc:
        return raise_or_return_error(
            exc, "open_meteo", "get_marine_conditions", hourly=[]
        )

    if response.status_code != 200:
        return {
            "error": f"Open-Meteo API returned {response.status_code}",
            "hourly": [],
        }

    data = response.json()
    hourly_raw = data.get("hourly", {})
    times = hourly_raw.get("time", [])

    hourly = []
    for i, t in enumerate(times):
        hourly.append({
            "time": t,
            "wave_height_m": _safe_idx(hourly_raw.get("wave_height"), i),
            "wave_direction_deg": _safe_idx(hourly_raw.get("wave_direction"), i),
            "wave_period_s": _safe_idx(hourly_raw.get("wave_period"), i),
            "swell_wave_height_m": _safe_idx(
                hourly_raw.get("swell_wave_height"), i
            ),
            "swell_wave_direction_deg": _safe_idx(
                hourly_raw.get("swell_wave_direction"), i
            ),
            "swell_wave_period_s": _safe_idx(
                hourly_raw.get("swell_wave_period"), i
            ),
            "ocean_current_velocity_ms": _safe_idx(
                hourly_raw.get("ocean_current_velocity"), i
            ),
            "ocean_current_direction_deg": _safe_idx(
                hourly_raw.get("ocean_current_direction"), i
            ),
        })

    return {
        "success": True,
        "latitude": latitude,
        "longitude": longitude,
        "forecast_days": forecast_days,
        "returned_count": len(hourly),
        "hourly": hourly,
    }


def _safe_idx(lst: list | None, idx: int):
    """Safely index into a list that may be None."""
    if lst is None or idx >= len(lst):
        return None
    return lst[idx]


if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=9004)
