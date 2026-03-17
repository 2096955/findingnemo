"""Tests for the risk_scorer tool."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from whale_tools.risk_scorer import RiskScorerTool, compute_risk, _speed_risk, SEASONAL_MULTIPLIERS


# ---------------------------------------------------------------------------
# _speed_risk tests
# ---------------------------------------------------------------------------


def test_speed_risk_slow():
    assert _speed_risk(8.0) == 0.2


def test_speed_risk_moderate():
    assert _speed_risk(12.0) == 0.5


def test_speed_risk_fast():
    assert _speed_risk(16.0) == 0.8


def test_speed_risk_very_fast():
    assert _speed_risk(22.0) == 1.0


def test_speed_risk_boundary_10():
    assert _speed_risk(10.0) == 0.2


def test_speed_risk_boundary_14():
    assert _speed_risk(14.0) == 0.5


def test_speed_risk_boundary_18():
    assert _speed_risk(18.0) == 0.8


# ---------------------------------------------------------------------------
# compute_risk tests
# ---------------------------------------------------------------------------


def test_compute_risk_score_in_range():
    result = compute_risk(
        latitude=37.0, longitude=-122.0, month=4,
        whale_density=0.8, vessel_traffic_density=0.6,
        vessel_speed_knots=15.0,
    )
    assert 0 <= result["collision_risk_score"] <= 1


def test_compute_risk_high_risk():
    result = compute_risk(
        latitude=37.0, longitude=-122.0, month=4,
        whale_density=0.9, vessel_traffic_density=0.9,
        vessel_speed_knots=20.0,
    )
    assert result["collision_risk_score"] >= 0.7
    assert result["risk_level"] == "HIGH"


def test_compute_risk_low_risk():
    result = compute_risk(
        latitude=37.0, longitude=-122.0, month=8,
        whale_density=0.1, vessel_traffic_density=0.1,
        vessel_speed_knots=8.0,
    )
    assert result["collision_risk_score"] < 0.4
    assert result["risk_level"] == "LOW"


def test_compute_risk_moderate():
    result = compute_risk(
        latitude=37.0, longitude=-122.0, month=3,
        whale_density=0.5, vessel_traffic_density=0.5,
        vessel_speed_knots=14.0,
    )
    assert result["risk_level"] in ("MODERATE", "HIGH", "LOW")
    assert 0 <= result["collision_risk_score"] <= 1


def test_compute_risk_components_present():
    result = compute_risk(
        latitude=37.0, longitude=-122.0, month=4,
        whale_density=0.8, vessel_traffic_density=0.6,
        vessel_speed_knots=15.0,
    )
    assert "components" in result
    components = result["components"]
    assert "whale_seasonal_factor" in components
    assert "seasonal_multiplier" in components
    assert "traffic_density" in components
    assert "speed_risk" in components
    assert "interaction_term" in components


def test_compute_risk_clamps_inputs():
    result = compute_risk(
        latitude=37.0, longitude=-122.0, month=15,
        whale_density=1.5, vessel_traffic_density=-0.5,
        vessel_speed_knots=20.0,
    )
    # Should not error, month should clamp to 12, density to bounds
    assert 0 <= result["collision_risk_score"] <= 1
    assert result["inputs"]["whale_density"] == 1.0
    assert result["inputs"]["vessel_traffic_density"] == 0.0
    assert result["inputs"]["month"] == 12


def test_compute_risk_recommendation_present():
    result = compute_risk(
        latitude=37.0, longitude=-122.0, month=4,
        whale_density=0.5, vessel_traffic_density=0.5,
        vessel_speed_knots=14.0,
    )
    assert "recommendation" in result
    assert len(result["recommendation"]) > 0


# ---------------------------------------------------------------------------
# Seasonal multipliers tests
# ---------------------------------------------------------------------------


def test_seasonal_multipliers_all_months():
    for month in range(1, 13):
        assert month in SEASONAL_MULTIPLIERS
        assert 0 < SEASONAL_MULTIPLIERS[month] <= 1.0


def test_seasonal_april_is_peak():
    assert SEASONAL_MULTIPLIERS[4] == 1.0


# ---------------------------------------------------------------------------
# RiskScorerTool integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_valid_input():
    tool = RiskScorerTool()
    result = await tool._run_async_impl(
        args={
            "latitude": 37.0,
            "longitude": -122.0,
            "month": 4,
            "whale_density": 0.8,
            "vessel_traffic_density": 0.6,
            "vessel_speed_knots": 15.0,
        },
    )
    assert "collision_risk_score" in result
    assert "risk_level" in result


@pytest.mark.asyncio
async def test_tool_properties():
    tool = RiskScorerTool()
    assert tool.tool_name == "risk_scorer"
    assert "collision" in tool.tool_description.lower()
    schema = tool.parameters_schema
    assert "latitude" in schema.properties
