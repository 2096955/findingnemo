"""Tests for the report_generator tool."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from whale_tools.report_generator import ReportGeneratorTool, generate_report, REPORT_MODES


# ---------------------------------------------------------------------------
# generate_report tests
# ---------------------------------------------------------------------------


def test_quick_answer():
    result = generate_report(
        question="What whales are near Monterey Bay?",
        evidence={"SpeciesIdentifier": {"species": "humpback_whale", "count": 12}},
        report_mode="quick_answer",
    )
    assert "formatted_report" in result
    assert "Quick Answer" in result["formatted_report"]
    assert result["report_mode"] == "quick_answer"


def test_route_recommendation():
    result = generate_report(
        question="Safest route from LA to SF",
        evidence={
            "route_calculator": {
                "total_distance_nm": 350,
                "estimated_fuel_impact_pct": 5.2,
                "waypoints": [{"lat": 33.7, "lng": -118.3}, {"lat": 37.8, "lng": -122.4}],
            },
            "risk_scorer": {
                "collision_risk_score": 0.45,
                "risk_level": "MODERATE",
                "recommendation": "Reduce speed to 14 knots",
            },
        },
        report_mode="route_recommendation",
    )
    assert "formatted_report" in result
    assert "Route Recommendation" in result["formatted_report"]
    assert "350" in result["formatted_report"]
    assert "MODERATE" in result["formatted_report"]


def test_risk_assessment():
    result = generate_report(
        question="What is the collision risk in the Santa Barbara Channel?",
        evidence={
            "risk_scorer": {
                "collision_risk_score": 0.72,
                "risk_level": "HIGH",
                "recommendation": "Immediate speed reduction",
                "components": {"whale_seasonal_factor": 0.9, "speed_risk": 0.8},
            },
            "incident_analyzer": {
                "total_incidents": 5,
                "lethal_incidents": 3,
                "species_breakdown": {"blue_whale": 2, "humpback_whale": 3},
            },
        },
        report_mode="risk_assessment",
    )
    assert "formatted_report" in result
    assert "Risk Assessment" in result["formatted_report"]
    assert "0.72" in result["formatted_report"]
    assert "HIGH" in result["formatted_report"]


def test_invalid_report_mode():
    result = generate_report(
        question="test", evidence={}, report_mode="invalid",
    )
    assert "error" in result


def test_report_specialists_used():
    result = generate_report(
        question="test",
        evidence={"RouteOptimizer": {}, "RiskAssessor": {}},
        report_mode="quick_answer",
    )
    assert "RouteOptimizer" in result["specialists_used"]
    assert "RiskAssessor" in result["specialists_used"]


# ---------------------------------------------------------------------------
# ReportGeneratorTool integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_valid_input():
    tool = ReportGeneratorTool()
    result = await tool._run_async_impl(
        args={
            "question": "What is the risk?",
            "evidence": {"RiskAssessor": {"risk_level": "HIGH"}},
            "report_mode": "quick_answer",
        },
    )
    assert "formatted_report" in result


@pytest.mark.asyncio
async def test_tool_missing_question():
    tool = ReportGeneratorTool()
    result = await tool._run_async_impl(
        args={"question": "", "evidence": {}},
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_tool_properties():
    tool = ReportGeneratorTool()
    assert tool.tool_name == "report_generator"
    assert "report" in tool.tool_description.lower()
    schema = tool.parameters_schema
    assert "question" in schema.properties
    assert "evidence" in schema.properties


def test_report_modes_constant():
    assert "quick_answer" in REPORT_MODES
    assert "route_recommendation" in REPORT_MODES
    assert "risk_assessment" in REPORT_MODES
