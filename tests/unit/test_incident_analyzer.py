"""Tests for the incident_analyzer tool."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from whale_tools.incident_analyzer import IncidentAnalyzerTool, query_incidents


# ---------------------------------------------------------------------------
# query_incidents tests
# ---------------------------------------------------------------------------


def test_incidents_sf_bay():
    """San Francisco Bay area should have incidents."""
    result = query_incidents(latitude=37.7, longitude=-122.5, radius_km=100)
    assert result["total_incidents"] > 0
    for incident in result["incidents"]:
        assert "year" in incident
        assert "species" in incident
        assert "vessel_type" in incident
        assert "outcome" in incident


def test_incidents_stellwagen():
    """Stellwagen Bank should have right whale incidents."""
    result = query_incidents(latitude=42.3, longitude=-70.5, radius_km=100)
    assert result["total_incidents"] > 0
    assert "right_whale" in result["species_breakdown"]


def test_incidents_no_results():
    """Middle of nowhere should have no incidents."""
    result = query_incidents(latitude=0.0, longitude=0.0, radius_km=50)
    assert result["total_incidents"] == 0


def test_incidents_species_filter():
    result = query_incidents(latitude=37.7, longitude=-122.5, radius_km=200, species="blue_whale")
    for incident in result["incidents"]:
        assert incident["species"] == "blue_whale"


def test_incidents_years_back_filter():
    result = query_incidents(latitude=37.7, longitude=-122.5, radius_km=200, years_back=2)
    for incident in result["incidents"]:
        assert incident["year"] >= 2024  # current year - 2


def test_incidents_lethal_count():
    result = query_incidents(latitude=34.0, longitude=-119.5, radius_km=200)
    assert "lethal_incidents" in result
    assert result["lethal_incidents"] >= 0
    assert result["lethal_incidents"] <= result["total_incidents"]


def test_incidents_species_breakdown():
    result = query_incidents(latitude=37.7, longitude=-122.5, radius_km=200)
    assert "species_breakdown" in result
    assert isinstance(result["species_breakdown"], dict)


def test_incidents_sorted_by_year():
    result = query_incidents(latitude=37.7, longitude=-122.5, radius_km=200)
    if result["total_incidents"] >= 2:
        years = [i["year"] for i in result["incidents"]]
        assert years == sorted(years, reverse=True)


# ---------------------------------------------------------------------------
# IncidentAnalyzerTool integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_valid_input():
    tool = IncidentAnalyzerTool()
    result = await tool._run_async_impl(
        args={"latitude": 37.7, "longitude": -122.5},
    )
    assert "incidents" in result
    assert "total_incidents" in result


@pytest.mark.asyncio
async def test_tool_properties():
    tool = IncidentAnalyzerTool()
    assert tool.tool_name == "incident_analyzer"
    assert "strike" in tool.tool_description.lower() or "incident" in tool.tool_description.lower()
    schema = tool.parameters_schema
    assert "latitude" in schema.properties
