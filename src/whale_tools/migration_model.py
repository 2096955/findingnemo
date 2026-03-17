"""Migration Model — returns expected whale density by species, region, and month.

Uses hardcoded seasonal patterns for key species (blue, humpback, right, gray)
across major ocean regions.
"""

import logging
import math
from typing import Optional

from google.adk.tools import ToolContext
from google.genai import types as adk_types

from solace_agent_mesh.agent.tools.dynamic_tool import DynamicTool

log = logging.getLogger(__name__)

# Seasonal density patterns by species and month (1-indexed).
# Values represent relative density (0-1) in their primary habitat areas.
_SPECIES_SEASONAL = {
    "blue_whale": {
        "months": {
            1: 0.3, 2: 0.3, 3: 0.4, 4: 0.5, 5: 0.7, 6: 0.9,
            7: 1.0, 8: 1.0, 9: 0.8, 10: 0.6, 11: 0.4, 12: 0.3,
        },
        "migration_phases": {
            1: "wintering", 2: "wintering", 3: "northward_migration",
            4: "northward_migration", 5: "feeding", 6: "feeding",
            7: "peak_feeding", 8: "peak_feeding", 9: "feeding",
            10: "southward_migration", 11: "southward_migration", 12: "wintering",
        },
    },
    "humpback_whale": {
        "months": {
            1: 0.8, 2: 0.9, 3: 1.0, 4: 0.7, 5: 0.5, 6: 0.6,
            7: 0.8, 8: 0.9, 9: 0.7, 10: 0.5, 11: 0.6, 12: 0.7,
        },
        "migration_phases": {
            1: "breeding", 2: "breeding", 3: "breeding",
            4: "northward_migration", 5: "northward_migration", 6: "feeding",
            7: "feeding", 8: "peak_feeding", 9: "feeding",
            10: "southward_migration", 11: "southward_migration", 12: "breeding",
        },
    },
    "right_whale": {
        "months": {
            1: 0.9, 2: 0.8, 3: 0.6, 4: 0.7, 5: 0.8, 6: 0.7,
            7: 0.6, 8: 0.5, 9: 0.5, 10: 0.6, 11: 0.7, 12: 0.8,
        },
        "migration_phases": {
            1: "calving", 2: "calving", 3: "northward_migration",
            4: "northward_migration", 5: "feeding", 6: "feeding",
            7: "feeding", 8: "feeding", 9: "southward_migration",
            10: "southward_migration", 11: "southward_migration", 12: "calving",
        },
    },
    "gray_whale": {
        "months": {
            1: 0.7, 2: 0.8, 3: 0.6, 4: 0.4, 5: 0.5, 6: 0.7,
            7: 0.9, 8: 1.0, 9: 0.8, 10: 0.6, 11: 0.5, 12: 0.6,
        },
        "migration_phases": {
            1: "calving", 2: "calving", 3: "northward_migration",
            4: "northward_migration", 5: "northward_migration", 6: "feeding",
            7: "feeding", 8: "peak_feeding", 9: "southward_migration",
            10: "southward_migration", 11: "southward_migration", 12: "calving",
        },
    },
}

# Known whale habitat regions with approximate bounding boxes
_REGIONS = [
    {
        "name": "US West Coast",
        "lat_range": (30.0, 50.0),
        "lng_range": (-130.0, -117.0),
        "species": ["blue_whale", "humpback_whale", "gray_whale"],
        "base_density_boost": 0.3,
    },
    {
        "name": "US East Coast",
        "lat_range": (25.0, 45.0),
        "lng_range": (-82.0, -65.0),
        "species": ["right_whale", "humpback_whale"],
        "base_density_boost": 0.25,
    },
    {
        "name": "Gulf of Alaska",
        "lat_range": (50.0, 62.0),
        "lng_range": (-165.0, -130.0),
        "species": ["humpback_whale", "gray_whale", "blue_whale"],
        "base_density_boost": 0.2,
    },
    {
        "name": "North Atlantic",
        "lat_range": (40.0, 65.0),
        "lng_range": (-60.0, -10.0),
        "species": ["right_whale", "humpback_whale", "blue_whale"],
        "base_density_boost": 0.15,
    },
    {
        "name": "English Channel / North Sea",
        "lat_range": (48.0, 55.0),
        "lng_range": (-6.0, 5.0),
        "species": ["humpback_whale"],
        "base_density_boost": 0.05,
    },
]


def _find_regions(lat: float, lng: float) -> list[dict]:
    """Find all regions containing the given coordinates."""
    matched = []
    for region in _REGIONS:
        lat_min, lat_max = region["lat_range"]
        lng_min, lng_max = region["lng_range"]
        if lat_min <= lat <= lat_max and lng_min <= lng <= lng_max:
            matched.append(region)
    return matched


def compute_migration(
    latitude: float,
    longitude: float,
    month: int,
    species: str | None = None,
) -> dict:
    """Compute whale density and migration info for a location/month."""
    month = max(1, min(12, month))
    regions = _find_regions(latitude, longitude)

    if not regions:
        return {
            "density": 0.0,
            "species_present": [],
            "migration_phase": "none",
            "region": "open_ocean",
            "location": {"latitude": latitude, "longitude": longitude},
            "month": month,
        }

    # Aggregate species across matched regions
    all_species = set()
    max_boost = 0.0
    primary_region = regions[0]["name"]
    for region in regions:
        all_species.update(region["species"])
        max_boost = max(max_boost, region["base_density_boost"])

    # Filter to requested species if given
    if species:
        # Normalize species name
        species_key = species.lower().replace(" ", "_").replace("-", "_")
        if species_key in _SPECIES_SEASONAL:
            target_species = [species_key]
        else:
            target_species = list(all_species)
    else:
        target_species = list(all_species)

    # Compute max density across present species
    max_density = 0.0
    migration_phase = "none"
    species_present = []

    for sp in target_species:
        if sp in _SPECIES_SEASONAL:
            sp_data = _SPECIES_SEASONAL[sp]
            density = sp_data["months"].get(month, 0.0) * (1.0 + max_boost)
            density = min(1.0, density)
            phase = sp_data["migration_phases"].get(month, "unknown")
            species_present.append({
                "species": sp,
                "density": round(density, 3),
                "migration_phase": phase,
            })
            if density > max_density:
                max_density = density
                migration_phase = phase

    return {
        "density": round(max_density, 3),
        "species_present": species_present,
        "migration_phase": migration_phase,
        "region": primary_region,
        "location": {"latitude": latitude, "longitude": longitude},
        "month": month,
    }


class MigrationModelTool(DynamicTool):
    """Returns expected whale density by species, region, and month."""

    @property
    def tool_name(self) -> str:
        return "migration_model"

    @property
    def tool_description(self) -> str:
        return (
            "Returns expected whale density by species, region, and month. "
            "Uses seasonal migration patterns for blue, humpback, right, and "
            "gray whales across major ocean regions."
        )

    @property
    def parameters_schema(self) -> adk_types.Schema:
        return adk_types.Schema(
            type=adk_types.Type.OBJECT,
            properties={
                "latitude": adk_types.Schema(
                    type=adk_types.Type.NUMBER,
                    description="Latitude of the assessment point",
                ),
                "longitude": adk_types.Schema(
                    type=adk_types.Type.NUMBER,
                    description="Longitude of the assessment point",
                ),
                "month": adk_types.Schema(
                    type=adk_types.Type.INTEGER,
                    description="Month (1-12)",
                ),
                "species": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="Optional: specific species to query (e.g. 'blue_whale', 'humpback_whale')",
                    nullable=True,
                ),
            },
            required=["latitude", "longitude", "month"],
        )

    async def _run_async_impl(
        self,
        args: dict,
        tool_context: Optional[ToolContext] = None,
        credential: Optional[str] = None,
    ) -> dict:
        try:
            return compute_migration(
                latitude=float(args["latitude"]),
                longitude=float(args["longitude"]),
                month=int(args["month"]),
                species=args.get("species"),
            )
        except (KeyError, ValueError, TypeError) as exc:
            return {"error": f"Invalid input: {exc}"}
