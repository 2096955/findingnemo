"""Tests for the map_renderer tool."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from whale_tools.map_renderer import MapRendererTool, RENDER_TYPES


@pytest.fixture
def tool():
    return MapRendererTool()


# ---------------------------------------------------------------------------
# risk_heatmap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_render_risk_heatmap(tool):
    data = [
        {"lat": 37.0, "lng": -122.0, "risk": 0.8},
        {"lat": 38.0, "lng": -123.0, "risk": 0.3},
    ]
    result = await tool._run_async_impl(
        args={"render_type": "risk_heatmap", "data": data},
    )
    assert result["type"] == "FeatureCollection"
    assert len(result["features"]) == 2
    feat = result["features"][0]
    assert feat["type"] == "Feature"
    assert feat["geometry"]["type"] == "Point"
    assert feat["properties"]["risk"] == 0.8
    assert result["metadata"]["layer_type"] == "HeatmapLayer"


# ---------------------------------------------------------------------------
# route
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_render_route_with_waypoints(tool):
    data = [
        {
            "waypoints": [
                {"lat": 47.6, "lng": -122.3},
                {"lat": 50.0, "lng": -130.0},
                {"lat": 61.2, "lng": -149.9},
            ],
            "distance_nm": 1200,
            "name": "Seattle-Anchorage",
        }
    ]
    result = await tool._run_async_impl(
        args={"render_type": "route", "data": data},
    )
    assert result["type"] == "FeatureCollection"
    assert len(result["features"]) == 1
    feat = result["features"][0]
    assert feat["geometry"]["type"] == "LineString"
    assert len(feat["geometry"]["coordinates"]) == 3
    assert result["metadata"]["layer_type"] == "PathLayer"


@pytest.mark.asyncio
async def test_render_route_point_list(tool):
    data = [
        {"lat": 37.0, "lng": -122.0},
        {"lat": 38.0, "lng": -123.0},
    ]
    result = await tool._run_async_impl(
        args={"render_type": "route", "data": data},
    )
    assert result["type"] == "FeatureCollection"
    assert result["features"][0]["geometry"]["type"] == "LineString"


# ---------------------------------------------------------------------------
# sightings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_render_sightings(tool):
    data = [
        {"lat": 36.8, "lng": -121.9, "species": "humpback_whale", "count": 3},
        {"lat": 42.3, "lng": -70.5, "species": "right_whale", "count": 1},
    ]
    result = await tool._run_async_impl(
        args={"render_type": "sightings", "data": data},
    )
    assert result["type"] == "FeatureCollection"
    assert len(result["features"]) == 2
    feat = result["features"][0]
    assert feat["geometry"]["type"] == "Point"
    assert feat["properties"]["species"] == "humpback_whale"
    assert feat["properties"]["count"] == 3
    assert result["metadata"]["layer_type"] == "ScatterplotLayer"


# ---------------------------------------------------------------------------
# shipping_lanes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_render_shipping_lanes(tool):
    data = [
        {
            "waypoints": [
                {"lat": 33.7, "lng": -118.3},
                {"lat": 34.0, "lng": -119.0},
            ],
            "density": 0.8,
            "name": "LA-SB Shipping Lane",
        }
    ]
    result = await tool._run_async_impl(
        args={"render_type": "shipping_lanes", "data": data},
    )
    assert result["type"] == "FeatureCollection"
    feat = result["features"][0]
    assert feat["geometry"]["type"] == "LineString"
    assert feat["properties"]["density"] == 0.8
    assert result["metadata"]["layer_type"] == "PathLayer"


# ---------------------------------------------------------------------------
# migration_corridors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_render_migration_corridors(tool):
    data = [
        {
            "waypoints": [
                {"lat": 27.5, "lng": -114.5},
                {"lat": 36.8, "lng": -121.9},
                {"lat": 48.0, "lng": -125.0},
            ],
            "species": "gray_whale",
            "name": "Eastern Pacific Gray Whale Corridor",
        }
    ]
    result = await tool._run_async_impl(
        args={"render_type": "migration_corridors", "data": data},
    )
    assert result["type"] == "FeatureCollection"
    feat = result["features"][0]
    assert feat["geometry"]["type"] == "LineString"
    assert feat["properties"]["species"] == "gray_whale"
    assert result["metadata"]["layer_type"] == "PathLayer"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_render_type(tool):
    result = await tool._run_async_impl(
        args={"render_type": "invalid_type", "data": []},
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_render_types_constant():
    assert "risk_heatmap" in RENDER_TYPES
    assert "route" in RENDER_TYPES
    assert "sightings" in RENDER_TYPES
    assert "shipping_lanes" in RENDER_TYPES
    assert "migration_corridors" in RENDER_TYPES


@pytest.mark.asyncio
async def test_tool_properties():
    tool = MapRendererTool()
    assert tool.tool_name == "map_renderer"
    assert "geojson" in tool.tool_description.lower() or "deck" in tool.tool_description.lower()
