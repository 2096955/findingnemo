"""Route Calculator — computes waypoint-based routes avoiding high-risk zones.

Uses great-circle (haversine) calculations with waypoint deviation around
risk zones for the PoC.
"""

import math
import logging
from typing import Optional

from google.adk.tools import ToolContext
from google.genai import types as adk_types

from solace_agent_mesh.agent.tools.dynamic_tool import DynamicTool

log = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0
KM_PER_NM = 1.852


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Compute great-circle distance in km between two points."""
    r1, r2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(r1) * math.cos(r2) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _haversine_nm(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Compute great-circle distance in nautical miles."""
    return _haversine_km(lat1, lng1, lat2, lng2) / KM_PER_NM


def _intermediate_point(lat1: float, lng1: float, lat2: float, lng2: float, fraction: float) -> tuple[float, float]:
    """Compute an intermediate point along the great-circle path."""
    r1, r2 = math.radians(lat1), math.radians(lat2)
    l1, l2 = math.radians(lng1), math.radians(lng2)
    d = 2 * math.asin(math.sqrt(
        math.sin((r2 - r1) / 2) ** 2 + math.cos(r1) * math.cos(r2) * math.sin((l2 - l1) / 2) ** 2
    ))
    if d < 1e-10:
        return lat1, lng1
    a = math.sin((1 - fraction) * d) / math.sin(d)
    b = math.sin(fraction * d) / math.sin(d)
    x = a * math.cos(r1) * math.cos(l1) + b * math.cos(r2) * math.cos(l2)
    y = a * math.cos(r1) * math.sin(l1) + b * math.cos(r2) * math.sin(l2)
    z = a * math.sin(r1) + b * math.sin(r2)
    lat = math.degrees(math.atan2(z, math.sqrt(x ** 2 + y ** 2)))
    lng = math.degrees(math.atan2(y, x))
    return lat, lng


def _point_in_risk_zone(lat: float, lng: float, zone: dict) -> bool:
    """Check if a point falls within a risk zone radius."""
    dist = _haversine_km(lat, lng, zone["lat"], zone["lng"])
    return dist < zone.get("radius_km", 50)


def _offset_waypoint(lat: float, lng: float, zone: dict, bearing_deg: float) -> tuple[float, float]:
    """Offset a waypoint perpendicular to route to avoid a risk zone."""
    offset_km = zone.get("radius_km", 50) * 1.2  # 20% margin
    # Compute perpendicular bearing (route bearing + 90 degrees)
    perp_bearing = math.radians(bearing_deg + 90)
    lat_r = math.radians(lat)
    lng_r = math.radians(lng)
    d = offset_km / EARTH_RADIUS_KM

    new_lat = math.asin(
        math.sin(lat_r) * math.cos(d) + math.cos(lat_r) * math.sin(d) * math.cos(perp_bearing)
    )
    new_lng = lng_r + math.atan2(
        math.sin(perp_bearing) * math.sin(d) * math.cos(lat_r),
        math.cos(d) - math.sin(lat_r) * math.sin(new_lat),
    )
    return math.degrees(new_lat), math.degrees(new_lng)


def _initial_bearing(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Compute initial bearing in degrees from point 1 to point 2."""
    r1, r2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lng2 - lng1)
    x = math.sin(dl) * math.cos(r2)
    y = math.cos(r1) * math.sin(r2) - math.sin(r1) * math.cos(r2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def compute_route(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    risk_zones: list[dict] | None = None,
) -> dict:
    """Compute a waypoint-based route between two points.

    Generates intermediate waypoints every ~100nm along the great-circle path.
    If a waypoint falls within a risk zone, offsets it perpendicular to the route.
    """
    risk_zones = risk_zones or []

    total_nm = _haversine_nm(origin_lat, origin_lng, dest_lat, dest_lng)
    if total_nm < 1:
        waypoints = [
            {"lat": origin_lat, "lng": origin_lng},
            {"lat": dest_lat, "lng": dest_lng},
        ]
        return _build_result(waypoints, total_nm, total_nm)

    # Generate intermediate waypoints every ~100nm
    step_nm = 100.0
    num_steps = max(2, int(total_nm / step_nm) + 1)
    bearing = _initial_bearing(origin_lat, origin_lng, dest_lat, dest_lng)

    waypoints = [{"lat": origin_lat, "lng": origin_lng}]
    for i in range(1, num_steps):
        fraction = i / num_steps
        lat, lng = _intermediate_point(origin_lat, origin_lng, dest_lat, dest_lng, fraction)

        # Check and offset for risk zones
        for zone in risk_zones:
            if _point_in_risk_zone(lat, lng, zone):
                lat, lng = _offset_waypoint(lat, lng, zone, bearing)
                log.info("Offset waypoint %d to avoid risk zone at (%.2f, %.2f)", i, zone["lat"], zone["lng"])
                break

        waypoints.append({"lat": round(lat, 6), "lng": round(lng, 6)})

    waypoints.append({"lat": dest_lat, "lng": dest_lng})

    # Calculate actual route distance
    route_distance = 0.0
    for i in range(len(waypoints) - 1):
        w1, w2 = waypoints[i], waypoints[i + 1]
        route_distance += _haversine_nm(w1["lat"], w1["lng"], w2["lat"], w2["lng"])

    return _build_result(waypoints, route_distance, total_nm)


def _build_result(waypoints: list[dict], route_distance_nm: float, direct_distance_nm: float) -> dict:
    """Build the result dict with waypoints, distance, and GeoJSON."""
    fuel_impact_pct = round(
        ((route_distance_nm / max(direct_distance_nm, 0.01)) - 1.0) * 100, 2
    )

    # Build GeoJSON FeatureCollection with LineString
    coordinates = [[wp["lng"], wp["lat"]] for wp in waypoints]
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": coordinates,
                },
                "properties": {
                    "distance_nm": round(route_distance_nm, 2),
                    "fuel_impact_pct": fuel_impact_pct,
                    "waypoint_count": len(waypoints),
                },
            }
        ],
    }

    return {
        "waypoints": waypoints,
        "total_distance_nm": round(route_distance_nm, 2),
        "direct_distance_nm": round(direct_distance_nm, 2),
        "estimated_fuel_impact_pct": fuel_impact_pct,
        "geojson": geojson,
    }


class RouteCalculatorTool(DynamicTool):
    """Computes waypoint-based routes avoiding high-risk whale zones."""

    @property
    def tool_name(self) -> str:
        return "route_calculator"

    @property
    def tool_description(self) -> str:
        return (
            "Computes waypoint-based routes between two points, avoiding "
            "high-risk whale zones. Uses great-circle calculations with "
            "perpendicular deviation around risk zones. Returns waypoints, "
            "distance in nautical miles, fuel impact, and GeoJSON."
        )

    @property
    def parameters_schema(self) -> adk_types.Schema:
        return adk_types.Schema(
            type=adk_types.Type.OBJECT,
            properties={
                "origin_lat": adk_types.Schema(
                    type=adk_types.Type.NUMBER,
                    description="Origin latitude",
                ),
                "origin_lng": adk_types.Schema(
                    type=adk_types.Type.NUMBER,
                    description="Origin longitude",
                ),
                "dest_lat": adk_types.Schema(
                    type=adk_types.Type.NUMBER,
                    description="Destination latitude",
                ),
                "dest_lng": adk_types.Schema(
                    type=adk_types.Type.NUMBER,
                    description="Destination longitude",
                ),
                "risk_zones": adk_types.Schema(
                    type=adk_types.Type.ARRAY,
                    description="List of risk zones to avoid: [{lat, lng, radius_km, risk_score}]",
                    nullable=True,
                    items=adk_types.Schema(
                        type=adk_types.Type.OBJECT,
                        properties={
                            "lat": adk_types.Schema(type=adk_types.Type.NUMBER),
                            "lng": adk_types.Schema(type=adk_types.Type.NUMBER),
                            "radius_km": adk_types.Schema(type=adk_types.Type.NUMBER),
                            "risk_score": adk_types.Schema(type=adk_types.Type.NUMBER),
                        },
                    ),
                ),
            },
            required=["origin_lat", "origin_lng", "dest_lat", "dest_lng"],
        )

    async def _run_async_impl(
        self,
        args: dict,
        tool_context: Optional[ToolContext] = None,
        credential: Optional[str] = None,
    ) -> dict:
        try:
            return compute_route(
                origin_lat=float(args["origin_lat"]),
                origin_lng=float(args["origin_lng"]),
                dest_lat=float(args["dest_lat"]),
                dest_lng=float(args["dest_lng"]),
                risk_zones=args.get("risk_zones"),
            )
        except (KeyError, ValueError, TypeError) as exc:
            return {"error": f"Invalid input: {exc}"}
