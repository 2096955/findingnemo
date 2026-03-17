"""Map Renderer — generates Deck.gl-compatible GeoJSON layers from agent outputs.

Supports render types: risk_heatmap, route, sightings, shipping_lanes,
migration_corridors.
"""

import logging
from typing import Optional

from google.adk.tools import ToolContext
from google.genai import types as adk_types

from solace_agent_mesh.agent.tools.dynamic_tool import DynamicTool

log = logging.getLogger(__name__)

RENDER_TYPES = (
    "risk_heatmap",
    "route",
    "sightings",
    "shipping_lanes",
    "migration_corridors",
)


def _render_risk_heatmap(data: list[dict]) -> dict:
    """Generate Point features with risk property for HeatmapLayer."""
    features = []
    for item in data:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [item.get("lng", item.get("longitude", 0)), item.get("lat", item.get("latitude", 0))],
            },
            "properties": {
                "risk": item.get("risk", item.get("risk_score", 0)),
                "weight": item.get("weight", item.get("risk", item.get("risk_score", 0.5))),
            },
        })
    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {"render_type": "risk_heatmap", "layer_type": "HeatmapLayer"},
    }


def _render_route(data: list[dict]) -> dict:
    """Generate LineString features for PathLayer."""
    features = []
    if data and "waypoints" in data[0]:
        # Single route with waypoints
        for route in data:
            waypoints = route.get("waypoints", [])
            coordinates = [
                [wp.get("lng", wp.get("longitude", 0)), wp.get("lat", wp.get("latitude", 0))]
                for wp in waypoints
            ]
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": coordinates,
                },
                "properties": {
                    "distance_nm": route.get("distance_nm", 0),
                    "name": route.get("name", "Route"),
                },
            })
    else:
        # Data is a list of coordinate points forming a single route
        coordinates = [
            [pt.get("lng", pt.get("longitude", 0)), pt.get("lat", pt.get("latitude", 0))]
            for pt in data
        ]
        if coordinates:
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": coordinates,
                },
                "properties": {"name": "Route"},
            })
    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {"render_type": "route", "layer_type": "PathLayer"},
    }


def _render_sightings(data: list[dict]) -> dict:
    """Generate Point features with species/count for ScatterplotLayer."""
    features = []
    for item in data:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [item.get("lng", item.get("longitude", 0)), item.get("lat", item.get("latitude", 0))],
            },
            "properties": {
                "species": item.get("species", "unknown"),
                "count": item.get("count", 1),
                "date": item.get("date", ""),
            },
        })
    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {"render_type": "sightings", "layer_type": "ScatterplotLayer"},
    }


def _render_shipping_lanes(data: list[dict]) -> dict:
    """Generate LineString features with density for PathLayer."""
    features = []
    for lane in data:
        waypoints = lane.get("waypoints", lane.get("coordinates", []))
        coordinates = [
            [wp.get("lng", wp.get("longitude", 0)), wp.get("lat", wp.get("latitude", 0))]
            for wp in waypoints
        ]
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates,
            },
            "properties": {
                "density": lane.get("density", 0),
                "name": lane.get("name", "Shipping Lane"),
            },
        })
    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {"render_type": "shipping_lanes", "layer_type": "PathLayer"},
    }


def _render_migration_corridors(data: list[dict]) -> dict:
    """Generate LineString features with species for PathLayer."""
    features = []
    for corridor in data:
        waypoints = corridor.get("waypoints", corridor.get("coordinates", []))
        coordinates = [
            [wp.get("lng", wp.get("longitude", 0)), wp.get("lat", wp.get("latitude", 0))]
            for wp in waypoints
        ]
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates,
            },
            "properties": {
                "species": corridor.get("species", "unknown"),
                "name": corridor.get("name", "Migration Corridor"),
            },
        })
    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {"render_type": "migration_corridors", "layer_type": "PathLayer"},
    }


_RENDERERS = {
    "risk_heatmap": _render_risk_heatmap,
    "route": _render_route,
    "sightings": _render_sightings,
    "shipping_lanes": _render_shipping_lanes,
    "migration_corridors": _render_migration_corridors,
}


class MapRendererTool(DynamicTool):
    """Generates Deck.gl-compatible GeoJSON layers from agent outputs."""

    @property
    def tool_name(self) -> str:
        return "map_renderer"

    @property
    def tool_description(self) -> str:
        return (
            "Generates Deck.gl-compatible GeoJSON layers from agent outputs. "
            "Supports render types: risk_heatmap (HeatmapLayer), route (PathLayer), "
            "sightings (ScatterplotLayer), shipping_lanes (PathLayer), "
            "migration_corridors (PathLayer)."
        )

    @property
    def parameters_schema(self) -> adk_types.Schema:
        return adk_types.Schema(
            type=adk_types.Type.OBJECT,
            properties={
                "render_type": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="Render type: risk_heatmap, route, sightings, shipping_lanes, migration_corridors",
                ),
                "data": adk_types.Schema(
                    type=adk_types.Type.ARRAY,
                    description="List of data dicts to render",
                    items=adk_types.Schema(type=adk_types.Type.OBJECT),
                ),
            },
            required=["render_type", "data"],
        )

    async def _run_async_impl(
        self,
        args: dict,
        tool_context: Optional[ToolContext] = None,
        credential: Optional[str] = None,
    ) -> dict:
        render_type = args.get("render_type", "")
        data = args.get("data", [])

        if render_type not in RENDER_TYPES:
            return {
                "error": f"Unknown render_type '{render_type}'. Must be one of: {RENDER_TYPES}"
            }

        if not isinstance(data, list):
            return {"error": "data must be a list of dicts"}

        renderer = _RENDERERS[render_type]
        return renderer(data)
