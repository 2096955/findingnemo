"""Tests for the migration_model tool."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from whale_tools.migration_model import MigrationModelTool, compute_migration


# ---------------------------------------------------------------------------
# compute_migration tests
# ---------------------------------------------------------------------------


def test_migration_west_coast():
    result = compute_migration(latitude=37.0, longitude=-122.0, month=7)
    assert result["density"] > 0
    assert len(result["species_present"]) > 0
    assert result["region"] == "US West Coast"


def test_migration_east_coast():
    result = compute_migration(latitude=42.0, longitude=-70.0, month=1)
    assert result["density"] > 0
    assert result["region"] == "US East Coast"


def test_migration_open_ocean():
    result = compute_migration(latitude=0.0, longitude=0.0, month=6)
    assert result["density"] == 0.0
    assert result["species_present"] == []
    assert result["region"] == "open_ocean"


def test_migration_specific_species():
    result = compute_migration(latitude=37.0, longitude=-122.0, month=7, species="blue_whale")
    assert len(result["species_present"]) >= 1
    assert result["species_present"][0]["species"] == "blue_whale"


def test_migration_phase_present():
    result = compute_migration(latitude=37.0, longitude=-122.0, month=7)
    assert result["migration_phase"] != "none"
    for sp in result["species_present"]:
        assert "migration_phase" in sp


def test_migration_density_range():
    result = compute_migration(latitude=37.0, longitude=-122.0, month=4)
    assert 0 <= result["density"] <= 1.0


def test_migration_month_clamping():
    result = compute_migration(latitude=37.0, longitude=-122.0, month=15)
    assert result["month"] == 12


def test_migration_gulf_of_alaska():
    result = compute_migration(latitude=55.0, longitude=-140.0, month=8)
    assert result["density"] > 0
    assert result["region"] == "Gulf of Alaska"


# ---------------------------------------------------------------------------
# MigrationModelTool integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_valid_input():
    tool = MigrationModelTool()
    result = await tool._run_async_impl(
        args={"latitude": 37.0, "longitude": -122.0, "month": 7},
    )
    assert "density" in result
    assert "species_present" in result
    assert "migration_phase" in result


@pytest.mark.asyncio
async def test_tool_with_species():
    tool = MigrationModelTool()
    result = await tool._run_async_impl(
        args={"latitude": 37.0, "longitude": -122.0, "month": 7, "species": "humpback_whale"},
    )
    assert "density" in result


@pytest.mark.asyncio
async def test_tool_properties():
    tool = MigrationModelTool()
    assert tool.tool_name == "migration_model"
    assert "density" in tool.tool_description.lower()
    schema = tool.parameters_schema
    assert "latitude" in schema.properties
