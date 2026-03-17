"""Habitat Mapper — maps feeding and breeding hotspots near a location.

Uses hardcoded known hotspot data for key whale habitats:
Monterey Bay, Stellwagen Bank, Channel Islands, etc.
"""

import logging
from typing import Optional

from google.adk.tools import ToolContext
from google.genai import types as adk_types

from solace_agent_mesh.agent.tools.dynamic_tool import DynamicTool
from whale_common.geo_utils import haversine_km

log = logging.getLogger(__name__)

# Known whale hotspots with coordinates and metadata
_HOTSPOTS = [
    {
        "name": "Monterey Bay",
        "lat": 36.80,
        "lng": -121.90,
        "type": "feeding",
        "species": ["blue_whale", "humpback_whale", "gray_whale"],
        "importance": "critical",
        "description": "Major upwelling zone, dense krill aggregations Jun-Nov",
    },
    {
        "name": "Stellwagen Bank",
        "lat": 42.35,
        "lng": -70.35,
        "type": "feeding",
        "species": ["humpback_whale", "right_whale", "fin_whale"],
        "importance": "critical",
        "description": "National Marine Sanctuary, peak feeding Apr-Oct",
    },
    {
        "name": "Channel Islands",
        "lat": 34.00,
        "lng": -119.80,
        "type": "feeding",
        "species": ["blue_whale", "humpback_whale", "gray_whale"],
        "importance": "high",
        "description": "Santa Barbara Channel, major feeding area Jun-Sep",
    },
    {
        "name": "Cape Cod Bay",
        "lat": 41.85,
        "lng": -70.15,
        "type": "feeding",
        "species": ["right_whale"],
        "importance": "critical",
        "description": "North Atlantic right whale critical habitat, Jan-May",
    },
    {
        "name": "Great South Channel",
        "lat": 41.00,
        "lng": -69.00,
        "type": "feeding",
        "species": ["right_whale", "humpback_whale"],
        "importance": "critical",
        "description": "Major copepod aggregation area, Apr-Jun",
    },
    {
        "name": "Southeast US Coast (calving)",
        "lat": 30.50,
        "lng": -80.50,
        "type": "breeding",
        "species": ["right_whale"],
        "importance": "critical",
        "description": "North Atlantic right whale calving ground, Nov-Apr",
    },
    {
        "name": "Baja California Lagoons",
        "lat": 27.50,
        "lng": -114.50,
        "type": "breeding",
        "species": ["gray_whale"],
        "importance": "critical",
        "description": "Gray whale calving lagoons (San Ignacio, Ojo de Liebre), Jan-Apr",
    },
    {
        "name": "Hawaii (Maui)",
        "lat": 20.80,
        "lng": -156.50,
        "type": "breeding",
        "species": ["humpback_whale"],
        "importance": "high",
        "description": "Humpback whale breeding/calving ground, Dec-Apr",
    },
    {
        "name": "Gulf of Maine",
        "lat": 43.50,
        "lng": -68.50,
        "type": "feeding",
        "species": ["humpback_whale", "right_whale", "fin_whale"],
        "importance": "high",
        "description": "Major feeding area with rich plankton, May-Oct",
    },
    {
        "name": "Puget Sound",
        "lat": 48.00,
        "lng": -122.50,
        "type": "feeding",
        "species": ["humpback_whale", "gray_whale"],
        "importance": "moderate",
        "description": "Seasonal feeding area, Apr-Sep",
    },
    {
        "name": "Gulf of the Farallones",
        "lat": 37.70,
        "lng": -123.00,
        "type": "feeding",
        "species": ["blue_whale", "humpback_whale", "gray_whale"],
        "importance": "high",
        "description": "National Marine Sanctuary near San Francisco, upwelling zone",
    },
    {
        "name": "Chesapeake Bay entrance",
        "lat": 36.95,
        "lng": -76.00,
        "type": "migration_corridor",
        "species": ["right_whale", "humpback_whale"],
        "importance": "moderate",
        "description": "Major shipping lane overlapping whale migration corridor",
    },
]


def find_hotspots(
    latitude: float,
    longitude: float,
    radius_km: float = 200.0,
) -> dict:
    """Find whale habitat hotspots within radius of a location."""
    results = []
    for hotspot in _HOTSPOTS:
        dist = haversine_km(latitude, longitude, hotspot["lat"], hotspot["lng"])
        if dist <= radius_km:
            results.append({
                **hotspot,
                "distance_km": round(dist, 1),
            })

    results.sort(key=lambda h: h["distance_km"])

    return {
        "hotspots": results,
        "count": len(results),
        "search_location": {"latitude": latitude, "longitude": longitude},
        "search_radius_km": radius_km,
    }


class HabitatMapperTool(DynamicTool):
    """Maps feeding and breeding hotspots near a location."""

    @property
    def tool_name(self) -> str:
        return "habitat_mapper"

    @property
    def tool_description(self) -> str:
        return (
            "Maps whale feeding, breeding, and migration hotspots near a given "
            "location. Uses known hotspot data for Monterey Bay, Stellwagen Bank, "
            "Channel Islands, and other critical whale habitats."
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
            return find_hotspots(
                latitude=float(args["latitude"]),
                longitude=float(args["longitude"]),
                radius_km=float(args.get("radius_km", 200)),
            )
        except (KeyError, ValueError, TypeError) as exc:
            return {"error": f"Invalid input: {exc}"}
