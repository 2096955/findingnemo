"""Tests for the route_calculator tool."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from whale_tools.route_calculator import (
    RouteCalculatorTool,
    compute_route,
    _haversine_nm,
)
from whale_common.geo_utils import haversine_km as _haversine_km


# ---------------------------------------------------------------------------
# Haversine tests
# ---------------------------------------------------------------------------


def test_haversine_same_point():
    dist = _haversine_nm(37.0, -122.0, 37.0, -122.0)
    assert dist == 0.0


def test_haversine_known_distance():
    # Seattle to Anchorage is approximately 1230 nm
    dist = _haversine_nm(47.6, -122.3, 61.2, -149.9)
    assert 1100 < dist < 1400


def test_haversine_km_positive():
    dist = _haversine_km(37.0, -122.0, 38.0, -123.0)
    assert dist > 0


# ---------------------------------------------------------------------------
# compute_route tests
# ---------------------------------------------------------------------------


def test_compute_route_basic():
    result = compute_route(47.6, -122.3, 61.2, -149.9)
    assert "waypoints" in result
    assert len(result["waypoints"]) >= 2
    assert result["total_distance_nm"] > 0
    assert result["estimated_fuel_impact_pct"] >= 0


def test_compute_route_has_geojson():
    result = compute_route(47.6, -122.3, 61.2, -149.9)
    geojson = result["geojson"]
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) >= 1
    feature = geojson["features"][0]
    assert feature["type"] == "Feature"
    assert feature["geometry"]["type"] == "LineString"
    assert len(feature["geometry"]["coordinates"]) >= 2


def test_compute_route_waypoints_start_end():
    result = compute_route(47.6, -122.3, 61.2, -149.9)
    waypoints = result["waypoints"]
    assert waypoints[0]["lat"] == 47.6
    assert waypoints[0]["lng"] == -122.3
    assert waypoints[-1]["lat"] == 61.2
    assert waypoints[-1]["lng"] == -149.9


def test_compute_route_with_risk_zones():
    risk_zones = [
        {"lat": 54.0, "lng": -136.0, "radius_km": 100, "risk_score": 0.9},
    ]
    result = compute_route(47.6, -122.3, 61.2, -149.9, risk_zones=risk_zones)
    assert result["total_distance_nm"] > 0
    assert len(result["waypoints"]) >= 2


def test_compute_route_same_point():
    result = compute_route(37.0, -122.0, 37.0, -122.0)
    assert len(result["waypoints"]) == 2
    assert result["total_distance_nm"] < 1


def test_compute_route_short_distance():
    # Two nearby points
    result = compute_route(37.0, -122.0, 37.1, -122.1)
    assert result["total_distance_nm"] > 0
    assert len(result["waypoints"]) >= 2


def test_compute_route_fuel_impact_no_diversion():
    # Without risk zones, fuel impact should be near zero
    result = compute_route(47.6, -122.3, 61.2, -149.9)
    assert result["estimated_fuel_impact_pct"] >= -1  # may be slightly negative due to rounding


# ---------------------------------------------------------------------------
# RouteCalculatorTool integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_valid_input():
    tool = RouteCalculatorTool()
    result = await tool._run_async_impl(
        args={
            "origin_lat": 47.6,
            "origin_lng": -122.3,
            "dest_lat": 61.2,
            "dest_lng": -149.9,
        },
    )
    assert "waypoints" in result
    assert "total_distance_nm" in result
    assert "geojson" in result


@pytest.mark.asyncio
async def test_tool_with_risk_zones():
    tool = RouteCalculatorTool()
    result = await tool._run_async_impl(
        args={
            "origin_lat": 47.6,
            "origin_lng": -122.3,
            "dest_lat": 61.2,
            "dest_lng": -149.9,
            "risk_zones": [
                {"lat": 54.0, "lng": -136.0, "radius_km": 80, "risk_score": 0.8},
            ],
        },
    )
    assert "waypoints" in result


@pytest.mark.asyncio
async def test_tool_properties():
    tool = RouteCalculatorTool()
    assert tool.tool_name == "route_calculator"
    assert "waypoint" in tool.tool_description.lower()
    schema = tool.parameters_schema
    assert "origin_lat" in schema.properties
