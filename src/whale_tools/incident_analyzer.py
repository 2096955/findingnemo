"""Incident Analyzer — returns historical whale strike statistics.

Uses hardcoded data from known incident databases for the PoC.
"""

import math
import logging
from typing import Optional

from google.adk.tools import ToolContext
from google.genai import types as adk_types

from solace_agent_mesh.agent.tools.dynamic_tool import DynamicTool

log = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0

# Hardcoded historical whale strike incidents
_INCIDENTS = [
    {"year": 2023, "lat": 37.60, "lng": -122.50, "species": "blue_whale", "vessel_type": "container", "outcome": "lethal", "region": "San Francisco Bay"},
    {"year": 2022, "lat": 37.80, "lng": -122.40, "species": "humpback_whale", "vessel_type": "cargo", "outcome": "injury", "region": "San Francisco Bay"},
    {"year": 2021, "lat": 34.00, "lng": -119.50, "species": "blue_whale", "vessel_type": "tanker", "outcome": "lethal", "region": "Santa Barbara Channel"},
    {"year": 2022, "lat": 34.10, "lng": -119.80, "species": "humpback_whale", "vessel_type": "container", "outcome": "lethal", "region": "Santa Barbara Channel"},
    {"year": 2023, "lat": 33.75, "lng": -118.30, "species": "fin_whale", "vessel_type": "cruise", "outcome": "lethal", "region": "Los Angeles/Long Beach"},
    {"year": 2020, "lat": 33.90, "lng": -118.50, "species": "blue_whale", "vessel_type": "cargo", "outcome": "injury", "region": "Los Angeles/Long Beach"},
    {"year": 2019, "lat": 36.70, "lng": -122.00, "species": "humpback_whale", "vessel_type": "fishing", "outcome": "entanglement", "region": "Monterey Bay"},
    {"year": 2021, "lat": 36.80, "lng": -121.90, "species": "gray_whale", "vessel_type": "cargo", "outcome": "lethal", "region": "Monterey Bay"},
    {"year": 2023, "lat": 42.30, "lng": -70.50, "species": "right_whale", "vessel_type": "container", "outcome": "lethal", "region": "Stellwagen Bank"},
    {"year": 2022, "lat": 42.00, "lng": -70.00, "species": "right_whale", "vessel_type": "cargo", "outcome": "injury", "region": "Stellwagen Bank"},
    {"year": 2021, "lat": 41.70, "lng": -70.30, "species": "humpback_whale", "vessel_type": "fishing", "outcome": "entanglement", "region": "Cape Cod"},
    {"year": 2020, "lat": 30.50, "lng": -80.50, "species": "right_whale", "vessel_type": "cargo", "outcome": "lethal", "region": "Southeast US"},
    {"year": 2022, "lat": 30.80, "lng": -81.00, "species": "right_whale", "vessel_type": "tanker", "outcome": "lethal", "region": "Southeast US"},
    {"year": 2019, "lat": 48.30, "lng": -124.50, "species": "gray_whale", "vessel_type": "cargo", "outcome": "injury", "region": "Strait of Juan de Fuca"},
    {"year": 2023, "lat": 48.00, "lng": -122.50, "species": "humpback_whale", "vessel_type": "ferry", "outcome": "near_miss", "region": "Puget Sound"},
    {"year": 2018, "lat": 40.50, "lng": -73.90, "species": "humpback_whale", "vessel_type": "ferry", "outcome": "near_miss", "region": "New York Harbor"},
    {"year": 2020, "lat": 47.50, "lng": -122.40, "species": "gray_whale", "vessel_type": "container", "outcome": "injury", "region": "Puget Sound"},
    {"year": 2017, "lat": 34.30, "lng": -119.90, "species": "blue_whale", "vessel_type": "container", "outcome": "lethal", "region": "Santa Barbara Channel"},
    {"year": 2018, "lat": 37.70, "lng": -123.00, "species": "humpback_whale", "vessel_type": "cargo", "outcome": "injury", "region": "Gulf of the Farallones"},
    {"year": 2021, "lat": 51.00, "lng": 1.40, "species": "humpback_whale", "vessel_type": "container", "outcome": "near_miss", "region": "English Channel"},
]


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Compute great-circle distance in km."""
    r1, r2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(r1) * math.cos(r2) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def query_incidents(
    latitude: float,
    longitude: float,
    radius_km: float = 200.0,
    species: str | None = None,
    years_back: int = 10,
) -> dict:
    """Query historical whale strike incidents near a location."""
    import datetime
    current_year = datetime.datetime.now().year
    min_year = current_year - years_back

    results = []
    for incident in _INCIDENTS:
        # Year filter
        if incident["year"] < min_year:
            continue
        # Species filter
        if species and incident["species"] != species:
            continue
        # Distance filter
        dist = _haversine_km(latitude, longitude, incident["lat"], incident["lng"])
        if dist <= radius_km:
            results.append({
                **incident,
                "distance_km": round(dist, 1),
            })

    results.sort(key=lambda x: x["year"], reverse=True)

    # Summary stats
    lethal_count = sum(1 for r in results if r["outcome"] == "lethal")
    species_counts = {}
    for r in results:
        sp = r["species"]
        species_counts[sp] = species_counts.get(sp, 0) + 1

    return {
        "incidents": results,
        "total_incidents": len(results),
        "lethal_incidents": lethal_count,
        "species_breakdown": species_counts,
        "search_location": {"latitude": latitude, "longitude": longitude},
        "search_radius_km": radius_km,
        "years_back": years_back,
    }


class IncidentAnalyzerTool(DynamicTool):
    """Returns historical whale strike statistics."""

    @property
    def tool_name(self) -> str:
        return "incident_analyzer"

    @property
    def tool_description(self) -> str:
        return (
            "Returns historical whale strike statistics near a location. "
            "Uses known incident databases to report year, species, vessel type, "
            "and outcome for each incident within a search radius."
        )

    @property
    def parameters_schema(self) -> adk_types.Schema:
        return adk_types.Schema(
            type=adk_types.Type.OBJECT,
            properties={
                "latitude": adk_types.Schema(
                    type=adk_types.Type.NUMBER,
                    description="Latitude of the search center",
                ),
                "longitude": adk_types.Schema(
                    type=adk_types.Type.NUMBER,
                    description="Longitude of the search center",
                ),
                "radius_km": adk_types.Schema(
                    type=adk_types.Type.NUMBER,
                    description="Search radius in kilometers (default 200)",
                    nullable=True,
                ),
                "species": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="Optional: filter by species (e.g. 'right_whale')",
                    nullable=True,
                ),
                "years_back": adk_types.Schema(
                    type=adk_types.Type.INTEGER,
                    description="Number of years to look back (default 10)",
                    nullable=True,
                ),
            },
            required=["latitude", "longitude"],
        )

    async def _run_async_impl(
        self,
        args: dict,
        tool_context: Optional[ToolContext] = None,
        credential: Optional[str] = None,
    ) -> dict:
        try:
            return query_incidents(
                latitude=float(args["latitude"]),
                longitude=float(args["longitude"]),
                radius_km=float(args.get("radius_km", 200)),
                species=args.get("species"),
                years_back=int(args.get("years_back", 10)),
            )
        except (KeyError, ValueError, TypeError) as exc:
            return {"error": f"Invalid input: {exc}"}
