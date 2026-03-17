"""Tests for the Marine Cadastre AIS mock MCP server."""

import sys
import os
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from mcp_servers.marine_cadastre import server as mc_module

get_vessel_traffic = mc_module.get_vessel_traffic.fn
get_shipping_lane_density = mc_module.get_shipping_lane_density.fn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reload_vessels():
    """Ensure vessels are loaded fresh for each test."""
    mc_module._vessels = []
    yield
    mc_module._vessels = []


# ---------------------------------------------------------------------------
# Tests: get_vessel_traffic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_vessel_traffic_finds_nearby_vessels():
    """Vessels near LA/Long Beach should be returned."""
    result = await get_vessel_traffic(33.85, -118.70, radius_km=50)

    assert result["success"] is True
    assert result["returned_count"] > 0
    # All returned vessels should be within the radius
    for v in result["vessels"]:
        assert v["distance_km"] <= 50


@pytest.mark.asyncio
async def test_get_vessel_traffic_sorted_by_distance():
    result = await get_vessel_traffic(33.85, -118.70, radius_km=100)

    if result["returned_count"] > 1:
        distances = [v["distance_km"] for v in result["vessels"]]
        assert distances == sorted(distances)


@pytest.mark.asyncio
async def test_get_vessel_traffic_empty_for_remote_location():
    """Middle of the Pacific Ocean should have no vessels."""
    result = await get_vessel_traffic(0.0, -160.0, radius_km=50)

    assert result["success"] is True
    assert result["returned_count"] == 0
    assert result["vessels"] == []


@pytest.mark.asyncio
async def test_get_vessel_traffic_invalid_latitude():
    result = await get_vessel_traffic(100.0, -118.0)
    assert "error" in result
    assert result["vessels"] == []


@pytest.mark.asyncio
async def test_get_vessel_traffic_radius_clamped():
    result = await get_vessel_traffic(33.85, -118.70, radius_km=9999)
    assert result["success"] is True
    assert result["radius_km"] == 500.0


# ---------------------------------------------------------------------------
# Tests: get_shipping_lane_density
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_shipping_lane_density_english_channel():
    """English Channel bounding box should contain several vessels."""
    result = await get_shipping_lane_density(
        min_lat=50.5, min_lng=0.5, max_lat=51.5, max_lng=2.5
    )

    assert result["success"] is True
    density = result["density"]
    assert density["total_vessels"] > 0
    assert density["vessels_per_sq_km"] > 0
    assert density["average_speed_knots"] > 0
    assert len(density["by_vessel_type"]) > 0


@pytest.mark.asyncio
async def test_get_shipping_lane_density_empty_box():
    """Remote bounding box with no vessels."""
    result = await get_shipping_lane_density(
        min_lat=-60.0, min_lng=-60.0, max_lat=-59.0, max_lng=-59.0
    )

    assert result["success"] is True
    assert result["density"]["total_vessels"] == 0


@pytest.mark.asyncio
async def test_get_shipping_lane_density_invalid_bounds():
    result = await get_shipping_lane_density(
        min_lat=50.0, min_lng=1.0, max_lat=49.0, max_lng=2.0
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_get_shipping_lane_density_has_area():
    result = await get_shipping_lane_density(
        min_lat=33.0, min_lng=-119.0, max_lat=35.0, max_lng=-117.0
    )
    assert result["success"] is True
    assert result["area_sq_km"] > 0


# ---------------------------------------------------------------------------
# Tests: data integrity
# ---------------------------------------------------------------------------


def test_sample_ais_data_valid():
    """Verify the sample AIS JSON file is well-formed."""
    data_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "data", "sample_ais_tracks.json"
    )
    with open(data_path) as f:
        vessels = json.load(f)

    assert len(vessels) >= 50
    required_keys = {
        "mmsi", "vessel_name", "vessel_type", "latitude",
        "longitude", "speed_knots", "heading", "timestamp",
    }
    for v in vessels:
        assert required_keys.issubset(v.keys()), f"Missing keys in {v.get('mmsi')}"
        assert -90 <= v["latitude"] <= 90
        assert -180 <= v["longitude"] <= 180
        assert v["speed_knots"] >= 0
        assert 0 <= v["heading"] < 360
