"""Tests for the query_decomposer tool."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from whale_tools.query_decomposer import (
    QueryDecomposerTool,
    _score_domain,
    _route_question,
    _split_question,
)
from whale_common.constants import DOMAIN_AGENT_ROUTING


# ---------------------------------------------------------------------------
# _score_domain tests
# ---------------------------------------------------------------------------


def test_score_domain_route_optimization():
    info = DOMAIN_AGENT_ROUTING["route_optimization"]
    score = _score_domain("safest route from Seattle to Anchorage", info)
    assert score > 0


def test_score_domain_no_match():
    info = DOMAIN_AGENT_ROUTING["route_optimization"]
    score = _score_domain("hello world", info)
    assert score == 0.0


def test_score_domain_risk_assessment():
    info = DOMAIN_AGENT_ROUTING["risk_assessment"]
    score = _score_domain("what is the collision risk in the channel", info)
    assert score > 0


# ---------------------------------------------------------------------------
# _route_question tests
# ---------------------------------------------------------------------------


def test_route_question_safest_route():
    """Route question about safest route should hit RouteOptimizer + RiskAssessor."""
    result = _route_question("safest route from Seattle to Anchorage")
    agents = {r["agent"] for r in result}
    assert "RouteOptimizer" in agents or "RiskAssessor" in agents
    assert len(result) >= 1


def test_route_question_whale_migration():
    result = _route_question("what are the seasonal migration patterns for humpback whales")
    agents = {r["agent"] for r in result}
    assert "WhaleMigrationTracker" in agents


def test_route_question_collision_risk():
    result = _route_question("what is the whale strike collision risk score in this area")
    agents = {r["agent"] for r in result}
    # Should match risk_assessment and/or incidents
    assert "RiskAssessor" in agents or "IncidentAnalyst" in agents


def test_route_question_returns_primary_and_secondary():
    result = _route_question("safest shipping route avoiding whale migration corridors")
    assert result[0]["role"] == "primary"
    # Should have secondary agents too given multiple keyword matches
    assert len(result) >= 2


# ---------------------------------------------------------------------------
# _split_question tests
# ---------------------------------------------------------------------------


def test_split_simple_question():
    result = _split_question("What is the safest route?", 5)
    assert len(result) == 1
    assert result[0].endswith("?")


def test_split_compound_semicolon():
    result = _split_question("What is the route risk; what species are nearby", 5)
    assert len(result) == 2


def test_split_compound_and():
    result = _split_question("Check the weather conditions and also check for whale sightings nearby", 5)
    assert len(result) >= 2


# ---------------------------------------------------------------------------
# QueryDecomposerTool integration tests (keyword fallback)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_decomposer_keyword_routing():
    tool = QueryDecomposerTool(tool_config={})
    result = await tool._run_async_impl(
        args={"question": "safest route from Seattle to Anchorage"},
        tool_context=None,
    )
    assert result["routing_method"] == "keyword"
    assert result["count"] >= 1
    assert "all_agents" in result
    agents = result["all_agents"]
    # Route + risk keywords should trigger RouteOptimizer
    assert any("RouteOptimizer" in a or "RiskAssessor" in a for a in agents)


@pytest.mark.asyncio
async def test_decomposer_empty_question():
    tool = QueryDecomposerTool(tool_config={})
    result = await tool._run_async_impl(
        args={"question": ""},
        tool_context=None,
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_decomposer_vessel_traffic():
    tool = QueryDecomposerTool(tool_config={})
    result = await tool._run_async_impl(
        args={"question": "Show me vessel traffic density in shipping lanes near Los Angeles port"},
        tool_context=None,
    )
    assert result["routing_method"] == "keyword"
    agents = result["all_agents"]
    assert "VesselTrafficMonitor" in agents


@pytest.mark.asyncio
async def test_decomposer_stores_selected_agents_key():
    """Verify that decomposer returns all_agents suitable for session state."""
    tool = QueryDecomposerTool(tool_config={})
    result = await tool._run_async_impl(
        args={"question": "whale migration patterns and habitat analysis"},
        tool_context=None,
    )
    assert isinstance(result["all_agents"], list)
    assert len(result["all_agents"]) >= 1
    # Agents should be sorted
    assert result["all_agents"] == sorted(result["all_agents"])


@pytest.mark.asyncio
async def test_decomposer_tool_properties():
    tool = QueryDecomposerTool(tool_config={})
    assert tool.tool_name == "query_decomposer"
    assert "whale" in tool.tool_description.lower() or "marine" in tool.tool_description.lower()
    schema = tool.parameters_schema
    assert "question" in schema.properties
