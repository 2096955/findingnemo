"""Tests for the fuel_estimator tool."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from whale_tools.fuel_estimator import FuelEstimatorTool, compute_fuel_impact


# ---------------------------------------------------------------------------
# compute_fuel_impact tests
# ---------------------------------------------------------------------------


def test_fuel_impact_no_diversion():
    result = compute_fuel_impact(
        route_distance_nm=500.0,
        original_distance_nm=500.0,
        speed_knots=14.0,
    )
    assert result["fuel_impact_pct"] == 0.0
    assert result["extra_fuel_liters"] == 0.0
    assert result["time_delta_hours"] == 0.0


def test_fuel_impact_with_diversion():
    result = compute_fuel_impact(
        route_distance_nm=550.0,
        original_distance_nm=500.0,
        speed_knots=14.0,
    )
    assert result["fuel_impact_pct"] == 10.0
    assert result["extra_fuel_liters"] > 0
    assert result["time_delta_hours"] > 0
    assert result["extra_distance_nm"] == 50.0


def test_fuel_impact_slow_speed():
    result = compute_fuel_impact(
        route_distance_nm=600.0,
        original_distance_nm=500.0,
        speed_knots=10.0,
    )
    assert result["fuel_impact_pct"] == 20.0
    # Slow speed has lower fuel rate
    assert result["fuel_rate_liters_per_nm"] == 8.0


def test_fuel_impact_fast_speed():
    result = compute_fuel_impact(
        route_distance_nm=600.0,
        original_distance_nm=500.0,
        speed_knots=22.0,
    )
    # Fast speed has higher fuel rate
    assert result["fuel_rate_liters_per_nm"] == 32.0
    assert result["extra_fuel_liters"] > 0


def test_fuel_impact_total_fuel():
    result = compute_fuel_impact(
        route_distance_nm=1000.0,
        original_distance_nm=900.0,
        speed_knots=14.0,
    )
    assert result["total_fuel_liters"] > result["original_fuel_liters"]


# ---------------------------------------------------------------------------
# FuelEstimatorTool integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_valid_input():
    tool = FuelEstimatorTool()
    result = await tool._run_async_impl(
        args={
            "route_distance_nm": 550.0,
            "original_distance_nm": 500.0,
            "speed_knots": 14.0,
        },
    )
    assert "fuel_impact_pct" in result
    assert "extra_fuel_liters" in result
    assert "time_delta_hours" in result


@pytest.mark.asyncio
async def test_tool_properties():
    tool = FuelEstimatorTool()
    assert tool.tool_name == "fuel_estimator"
    assert "fuel" in tool.tool_description.lower()
    schema = tool.parameters_schema
    assert "route_distance_nm" in schema.properties
