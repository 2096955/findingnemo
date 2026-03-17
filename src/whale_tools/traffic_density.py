"""Traffic Density — aggregates AIS data into a density grid.

Reads mock AIS track data from data/sample_ais_tracks.json and produces a
grid of vessel counts and average speeds for a specified bounding box.
"""

import json
import logging
import os
from typing import Optional

from google.adk.tools import ToolContext
from google.genai import types as adk_types

from solace_agent_mesh.agent.tools.dynamic_tool import DynamicTool

log = logging.getLogger(__name__)

_AIS_DATA_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "sample_ais_tracks.json"
)


def _load_ais_data(path: str | None = None) -> list[dict]:
    """Load AIS track data from JSON file."""
    fpath = path or _AIS_DATA_PATH
    try:
        with open(fpath, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        log.warning("Could not load AIS data from %s: %s", fpath, exc)
        return []


def compute_density_grid(
    min_lat: float,
    min_lng: float,
    max_lat: float,
    max_lng: float,
    grid_resolution: float = 0.5,
    ais_data: list[dict] | None = None,
) -> dict:
    """Aggregate AIS tracks into a density grid.

    Each grid cell reports vessel_count and avg_speed for vessels
    whose positions fall within that cell.
    """
    if ais_data is None:
        ais_data = _load_ais_data()

    # Filter tracks within bounding box
    filtered = [
        t for t in ais_data
        if min_lat <= t.get("latitude", 0) <= max_lat
        and min_lng <= t.get("longitude", 0) <= max_lng
    ]

    # Build grid
    grid_cells = []
    lat = min_lat
    while lat < max_lat:
        lng = min_lng
        while lng < max_lng:
            cell_lat_max = lat + grid_resolution
            cell_lng_max = lng + grid_resolution

            # Find vessels in this cell
            in_cell = [
                t for t in filtered
                if lat <= t.get("latitude", 0) < cell_lat_max
                and lng <= t.get("longitude", 0) < cell_lng_max
            ]

            if in_cell:
                speeds = [t.get("speed_knots", 0) for t in in_cell]
                avg_speed = round(sum(speeds) / len(speeds), 1)
                grid_cells.append({
                    "cell_lat": round(lat, 4),
                    "cell_lng": round(lng, 4),
                    "cell_lat_max": round(cell_lat_max, 4),
                    "cell_lng_max": round(cell_lng_max, 4),
                    "vessel_count": len(in_cell),
                    "avg_speed": avg_speed,
                    "vessel_types": list({t.get("vessel_type", "unknown") for t in in_cell}),
                })

            lng += grid_resolution
        lat += grid_resolution

    return {
        "grid_cells": grid_cells,
        "total_vessels_in_bbox": len(filtered),
        "cells_with_traffic": len(grid_cells),
        "grid_resolution": grid_resolution,
        "bounding_box": {
            "min_lat": min_lat,
            "min_lng": min_lng,
            "max_lat": max_lat,
            "max_lng": max_lng,
        },
    }


class TrafficDensityTool(DynamicTool):
    """Aggregates AIS data into a vessel density grid."""

    @property
    def tool_name(self) -> str:
        return "traffic_density"

    @property
    def tool_description(self) -> str:
        return (
            "Aggregates AIS vessel tracking data into a density grid for a "
            "given bounding box. Returns grid cells with vessel count and "
            "average speed. Uses data from sample_ais_tracks.json."
        )

    @property
    def parameters_schema(self) -> adk_types.Schema:
        return adk_types.Schema(
            type=adk_types.Type.OBJECT,
            properties={
                "min_lat": adk_types.Schema(
                    type=adk_types.Type.NUMBER,
                    description="Minimum latitude of bounding box",
                ),
                "min_lng": adk_types.Schema(
                    type=adk_types.Type.NUMBER,
                    description="Minimum longitude of bounding box",
                ),
                "max_lat": adk_types.Schema(
                    type=adk_types.Type.NUMBER,
                    description="Maximum latitude of bounding box",
                ),
                "max_lng": adk_types.Schema(
                    type=adk_types.Type.NUMBER,
                    description="Maximum longitude of bounding box",
                ),
                "grid_resolution": adk_types.Schema(
                    type=adk_types.Type.NUMBER,
                    description="Grid cell size in degrees (default 0.5)",
                    nullable=True,
                ),
            },
            required=["min_lat", "min_lng", "max_lat", "max_lng"],
        )

    async def _run_async_impl(
        self,
        args: dict,
        tool_context: Optional[ToolContext] = None,
        credential: Optional[str] = None,
    ) -> dict:
        try:
            return compute_density_grid(
                min_lat=float(args["min_lat"]),
                min_lng=float(args["min_lng"]),
                max_lat=float(args["max_lat"]),
                max_lng=float(args["max_lng"]),
                grid_resolution=float(args.get("grid_resolution", 0.5)),
            )
        except (KeyError, ValueError, TypeError) as exc:
            return {"error": f"Invalid input: {exc}"}
