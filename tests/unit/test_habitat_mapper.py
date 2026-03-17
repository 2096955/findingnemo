"""Tests for the habitat_mapper tool."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from whale_tools.habitat_mapper import HabitatMapperTool, find_hotspots


# ---------------------------------------------------------------------------
# find_hotspots tests
# ---------------------------------------------------------------------------


def test_find_hotspots_monterey_bay():
    result = find_hotspots(latitude=36.8, longitude=-121.9, radius_km=50)
    assert result["count"] >= 1
    names = [h["name"] for h in result["hotspots"]]
    assert "Monterey Bay" in names


def test_find_hotspots_stellwagen():
    result = find_hotspots(latitude=42.35, longitude=-70.35, radius_km=50)
    assert result["count"] >= 1
    names = [h["name"] for h in result["hotspots"]]
    assert "Stellwagen Bank" in names


def test_find_hotspots_no_results():
    result = find_hotspots(latitude=0.0, longitude=0.0, radius_km=50)
    assert result["count"] == 0
    assert result["hotspots"] == []


def test_find_hotspots_large_radius():
    result = find_hotspots(latitude=37.0, longitude=-122.0, radius_km=500)
    assert result["count"] >= 2  # Should find Monterey Bay, Channel Islands, Farallones


def test_find_hotspots_distance_field():
    result = find_hotspots(latitude=36.8, longitude=-121.9, radius_km=200)
    for hotspot in result["hotspots"]:
        assert "distance_km" in hotspot
        assert hotspot["distance_km"] >= 0


def test_find_hotspots_sorted_by_distance():
    result = find_hotspots(latitude=37.0, longitude=-122.0, radius_km=500)
    if result["count"] >= 2:
        distances = [h["distance_km"] for h in result["hotspots"]]
        assert distances == sorted(distances)


def test_find_hotspots_has_species_and_type():
    result = find_hotspots(latitude=36.8, longitude=-121.9, radius_km=50)
    for hotspot in result["hotspots"]:
        assert "species" in hotspot
        assert "type" in hotspot
        assert "importance" in hotspot
        assert isinstance(hotspot["species"], list)


# ---------------------------------------------------------------------------
# HabitatMapperTool integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_valid_input():
    tool = HabitatMapperTool()
    result = await tool._run_async_impl(
        args={"latitude": 36.8, "longitude": -121.9},
    )
    assert "hotspots" in result
    assert "count" in result


@pytest.mark.asyncio
async def test_tool_with_radius():
    tool = HabitatMapperTool()
    result = await tool._run_async_impl(
        args={"latitude": 36.8, "longitude": -121.9, "radius_km": 500},
    )
    assert result["search_radius_km"] == 500


@pytest.mark.asyncio
async def test_tool_properties():
    tool = HabitatMapperTool()
    assert tool.tool_name == "habitat_mapper"
    assert "hotspot" in tool.tool_description.lower() or "habitat" in tool.tool_description.lower()
    schema = tool.parameters_schema
    assert "latitude" in schema.properties
