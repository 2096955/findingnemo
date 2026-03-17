"""Marine Cadastre AIS mock MCP server.

Provides realistic mock AIS (Automatic Identification System) vessel
traffic data for the proof of concept. Reads from a local sample data
file instead of a real API.

Mock data: data/sample_ais_tracks.json
"""

import json
import math
import os
import sys
import logging
from pathlib import Path

from fastmcp import FastMCP

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

log = logging.getLogger(__name__)

mcp = FastMCP("marine_cadastre")

# Load sample AIS data
_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
_AIS_FILE = _DATA_DIR / "sample_ais_tracks.json"

_vessels: list[dict] = []


def _load_vessels() -> list[dict]:
    """Load vessel data from the sample JSON file."""
    global _vessels
    if _vessels:
        return _vessels
    try:
        with open(_AIS_FILE) as f:
            _vessels = json.load(f)
        log.info("Loaded %d vessel records from %s", len(_vessels), _AIS_FILE)
    except FileNotFoundError:
        log.error("AIS data file not found: %s", _AIS_FILE)
        _vessels = []
    except json.JSONDecodeError as exc:
        log.error("Invalid JSON in AIS data file: %s", exc)
        _vessels = []
    return _vessels


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in km."""
    R = 6371.0  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


@mcp.tool()
async def get_vessel_traffic(
    latitude: float, longitude: float, radius_km: float = 50
) -> dict:
    """Get vessel positions near a geographic point.

    Args:
        latitude: Center latitude (-90 to 90).
        longitude: Center longitude (-180 to 180).
        radius_km: Search radius in kilometers (default 50, max 500).

    Returns list of vessel records with MMSI, name, type, position,
    speed, and heading.
    """
    if not (-90 <= latitude <= 90):
        return {"error": "Latitude must be between -90 and 90", "vessels": []}
    if not (-180 <= longitude <= 180):
        return {"error": "Longitude must be between -180 and 180", "vessels": []}

    radius_km = max(1.0, min(500.0, radius_km))
    vessels = _load_vessels()

    nearby = []
    for v in vessels:
        vlat = v.get("latitude")
        vlon = v.get("longitude")
        if vlat is None or vlon is None:
            continue
        dist = _haversine_km(latitude, longitude, vlat, vlon)
        if dist <= radius_km:
            record = dict(v)
            record["distance_km"] = round(dist, 2)
            nearby.append(record)

    # Sort by distance
    nearby.sort(key=lambda x: x["distance_km"])

    return {
        "success": True,
        "center_latitude": latitude,
        "center_longitude": longitude,
        "radius_km": radius_km,
        "returned_count": len(nearby),
        "vessels": nearby,
    }


@mcp.tool()
async def get_shipping_lane_density(
    min_lat: float, min_lng: float, max_lat: float, max_lng: float
) -> dict:
    """Get vessel traffic density for a bounding box.

    Args:
        min_lat: Southern boundary latitude.
        min_lng: Western boundary longitude.
        max_lat: Northern boundary latitude.
        max_lng: Eastern boundary longitude.

    Returns a summary of vessel traffic density within the bounding box,
    including vessel count by type and average speed.
    """
    if min_lat >= max_lat:
        return {"error": "min_lat must be less than max_lat", "density": {}}
    if min_lng >= max_lng:
        return {"error": "min_lng must be less than max_lng", "density": {}}

    vessels = _load_vessels()

    in_box = []
    for v in vessels:
        vlat = v.get("latitude")
        vlon = v.get("longitude")
        if vlat is None or vlon is None:
            continue
        if min_lat <= vlat <= max_lat and min_lng <= vlon <= max_lng:
            in_box.append(v)

    # Calculate area in approximate sq km
    mid_lat = (min_lat + max_lat) / 2
    lat_km = (max_lat - min_lat) * 111.0
    lng_km = (max_lng - min_lng) * 111.0 * math.cos(math.radians(mid_lat))
    area_sq_km = lat_km * lng_km

    # Count by vessel type
    type_counts = {}
    total_speed = 0.0
    for v in in_box:
        vtype = v.get("vessel_type", "unknown")
        type_counts[vtype] = type_counts.get(vtype, 0) + 1
        total_speed += v.get("speed_knots", 0.0)

    avg_speed = round(total_speed / len(in_box), 1) if in_box else 0.0

    return {
        "success": True,
        "bounding_box": {
            "min_lat": min_lat,
            "min_lng": min_lng,
            "max_lat": max_lat,
            "max_lng": max_lng,
        },
        "area_sq_km": round(area_sq_km, 1),
        "density": {
            "total_vessels": len(in_box),
            "vessels_per_sq_km": round(len(in_box) / area_sq_km, 4)
            if area_sq_km > 0
            else 0,
            "average_speed_knots": avg_speed,
            "by_vessel_type": type_counts,
        },
    }


if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=9003)
