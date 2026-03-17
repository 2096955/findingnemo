"""Tests for the traffic_density tool."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from whale_tools.traffic_density import TrafficDensityTool, compute_density_grid


# ---------------------------------------------------------------------------
# compute_density_grid tests
# ---------------------------------------------------------------------------


def test_density_grid_la_area():
    """LA/Long Beach area should have vessels from sample data."""
    result = compute_density_grid(
        min_lat=33.0, min_lng=-119.5, max_lat=34.5, max_lng=-118.0,
        grid_resolution=0.5,
    )
    assert result["total_vessels_in_bbox"] > 0
    assert result["cells_with_traffic"] > 0
    assert len(result["grid_cells"]) > 0


def test_density_grid_cell_structure():
    result = compute_density_grid(
        min_lat=33.0, min_lng=-119.5, max_lat=34.5, max_lng=-118.0,
        grid_resolution=0.5,
    )
    for cell in result["grid_cells"]:
        assert "cell_lat" in cell
        assert "cell_lng" in cell
        assert "vessel_count" in cell
        assert "avg_speed" in cell
        assert cell["vessel_count"] > 0


def test_density_grid_empty_area():
    """Middle of nowhere should have no vessels."""
    result = compute_density_grid(
        min_lat=0.0, min_lng=0.0, max_lat=1.0, max_lng=1.0,
        grid_resolution=0.5,
    )
    assert result["total_vessels_in_bbox"] == 0
    assert result["cells_with_traffic"] == 0


def test_density_grid_custom_resolution():
    result = compute_density_grid(
        min_lat=33.0, min_lng=-119.5, max_lat=34.5, max_lng=-118.0,
        grid_resolution=1.0,
    )
    assert result["grid_resolution"] == 1.0


def test_density_grid_with_mock_data():
    """Test with explicit AIS data."""
    mock_ais = [
        {"latitude": 37.5, "longitude": -122.3, "speed_knots": 12.0, "vessel_type": "cargo"},
        {"latitude": 37.6, "longitude": -122.4, "speed_knots": 14.0, "vessel_type": "tanker"},
    ]
    result = compute_density_grid(
        min_lat=37.0, min_lng=-123.0, max_lat=38.0, max_lng=-122.0,
        grid_resolution=0.5,
        ais_data=mock_ais,
    )
    assert result["total_vessels_in_bbox"] == 2


def test_density_grid_bounding_box():
    result = compute_density_grid(
        min_lat=33.0, min_lng=-119.5, max_lat=34.5, max_lng=-118.0,
    )
    bb = result["bounding_box"]
    assert bb["min_lat"] == 33.0
    assert bb["max_lat"] == 34.5


# ---------------------------------------------------------------------------
# TrafficDensityTool integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_valid_input():
    tool = TrafficDensityTool()
    result = await tool._run_async_impl(
        args={
            "min_lat": 33.0,
            "min_lng": -119.5,
            "max_lat": 34.5,
            "max_lng": -118.0,
        },
    )
    assert "grid_cells" in result
    assert "total_vessels_in_bbox" in result


@pytest.mark.asyncio
async def test_tool_properties():
    tool = TrafficDensityTool()
    assert tool.tool_name == "traffic_density"
    assert "density" in tool.tool_description.lower()
    schema = tool.parameters_schema
    assert "min_lat" in schema.properties
