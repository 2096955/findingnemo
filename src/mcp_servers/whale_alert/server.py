"""Whale Alert MCP server.

Provides whale sighting reports from the Whale Alert API to help
agents assess real-time whale presence in shipping corridors.

API: https://www.whalealert.org/api/v1/events (requires WHALE_ALERT_API_KEY)
"""

import os
import sys
import logging
import time

from fastmcp import FastMCP

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from mcp_servers._http import (
    resilient_get,
    CircuitOpenError,
    RetryExhaustedError,
    raise_or_return_error,
)

log = logging.getLogger(__name__)

mcp = FastMCP("whale_alert")

WHALE_ALERT_BASE = "https://www.whalealert.org/api/v1/events"
WHALE_ALERT_API_KEY = os.environ.get("WHALE_ALERT_API_KEY", "")


@mcp.tool()
async def get_whale_sightings(
    latitude: float,
    longitude: float,
    radius_km: float = 100.0,
    hours_back: int = 72,
) -> dict:
    """Get recent whale sighting reports near a location.

    Args:
        latitude: Center latitude (-90 to 90).
        longitude: Center longitude (-180 to 180).
        radius_km: Search radius in kilometers (default 100).
        hours_back: How many hours to look back (default 72, max 720).

    Returns list of whale sighting events with species, location,
    timestamp, and reported details.
    """
    if not WHALE_ALERT_API_KEY:
        return {
            "error": "WHALE_ALERT_API_KEY environment variable not set",
            "sightings": [],
        }

    if not (-90 <= latitude <= 90):
        return {"error": "Latitude must be between -90 and 90", "sightings": []}
    if not (-180 <= longitude <= 180):
        return {"error": "Longitude must be between -180 and 180", "sightings": []}

    hours_back = max(1, min(720, hours_back))
    radius_km = max(1.0, min(500.0, radius_km))

    since_ts = int(time.time()) - (hours_back * 3600)

    params = {
        "lat": str(latitude),
        "lng": str(longitude),
        "radius": str(radius_km),
        "since": str(since_ts),
        "api_key": WHALE_ALERT_API_KEY,
    }

    try:
        response = await resilient_get(WHALE_ALERT_BASE, params=params)
    except (CircuitOpenError, RetryExhaustedError) as exc:
        return raise_or_return_error(
            exc, "whale_alert", "get_whale_sightings", sightings=[]
        )

    if response.status_code != 200:
        return {
            "error": f"Whale Alert API returned {response.status_code}",
            "sightings": [],
        }

    data = response.json()
    events = data.get("events", [])

    sightings = []
    for event in events:
        sightings.append({
            "id": event.get("id"),
            "type": event.get("type", ""),
            "species": event.get("species", "unknown"),
            "latitude": event.get("latitude"),
            "longitude": event.get("longitude"),
            "number_sighted": event.get("number"),
            "timestamp": event.get("eventdate", ""),
            "description": event.get("description", ""),
            "source": event.get("source", ""),
        })

    return {
        "success": True,
        "center_latitude": latitude,
        "center_longitude": longitude,
        "radius_km": radius_km,
        "hours_back": hours_back,
        "returned_count": len(sightings),
        "sightings": sightings,
    }


if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=9002)
