"""Integration tests for the orchestrator -> specialist delegation flow.

Tests the 7-step orchestration protocol end-to-end using the real tool
implementations (query_decomposer, memory_plane, cold_store, report_generator,
map_renderer) and real computation tools (risk_scorer, route_calculator).

External dependencies (LLM, Redis, MCP servers, SAM broker) are mocked.
The tests validate that the orchestrator's tools compose correctly when
chained together in the documented protocol order.
"""

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from whale_tools.query_decomposer import QueryDecomposerTool, _route_question
from whale_tools.memory_plane import MemoryPlaneTool, DictBackend
from whale_tools.cold_store import (
    ColdStoreTool,
    get_connection,
    store_session,
    store_route_pattern,
    query_patterns,
    get_strategies,
)
from whale_tools.report_generator import ReportGeneratorTool, generate_report
from whale_tools.map_renderer import MapRendererTool, RENDER_TYPES
from whale_tools.risk_scorer import RiskScorerTool, compute_risk
from whale_tools.route_calculator import RouteCalculatorTool, compute_route


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_memory_backend():
    """Ensure each test starts with a clean in-memory backend."""
    MemoryPlaneTool._backend = None
    yield
    MemoryPlaneTool._backend = None


@pytest.fixture
def memory_tool():
    return MemoryPlaneTool(tool_config={})


@pytest.fixture
def decomposer():
    # No model configured -> keyword routing, no LLM calls
    return QueryDecomposerTool(tool_config={})


@pytest.fixture
def report_tool():
    return ReportGeneratorTool()


@pytest.fixture
def map_tool():
    return MapRendererTool()


@pytest.fixture
def risk_tool():
    return RiskScorerTool()


@pytest.fixture
def route_tool():
    return RouteCalculatorTool()


@pytest.fixture
def cold_db_path():
    """Provide a temporary SQLite database for cold store tests."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def cold_tool(cold_db_path):
    return ColdStoreTool(tool_config={"db_path": cold_db_path})


@pytest.fixture
def memory_tool_with_cold(cold_db_path):
    """Memory plane wired to the same temp cold store."""
    MemoryPlaneTool._backend = None
    return MemoryPlaneTool(tool_config={"cold_db_path": cold_db_path})


# ============================================================================
# 1. Query Decomposer -> Specialist Routing
# ============================================================================


class TestQueryDecomposerRouting:
    """Validate that different query types route to the correct specialists."""

    @pytest.mark.asyncio
    async def test_route_planning_query(self, decomposer):
        """Route planning queries should target RouteOptimizer."""
        result = await decomposer._run_async_impl(
            args={"question": "Plan the safest shipping route from San Francisco to Tokyo avoiding whale zones"},
        )
        assert result["routing_method"] == "keyword"
        agents = result["all_agents"]
        assert "RouteOptimizer" in agents
        assert result["count"] >= 1

    @pytest.mark.asyncio
    async def test_risk_query(self, decomposer):
        """Risk queries should target RiskAssessor and/or IncidentAnalyst."""
        result = await decomposer._run_async_impl(
            args={"question": "What is the whale collision risk score in the Santa Barbara Channel"},
        )
        agents = result["all_agents"]
        assert "RiskAssessor" in agents or "IncidentAnalyst" in agents

    @pytest.mark.asyncio
    async def test_whale_migration_query(self, decomposer):
        """Migration queries should target WhaleMigrationTracker."""
        result = await decomposer._run_async_impl(
            args={"question": "Show humpback whale seasonal migration corridors in the North Pacific"},
        )
        agents = result["all_agents"]
        assert "WhaleMigrationTracker" in agents

    @pytest.mark.asyncio
    async def test_weather_query(self, decomposer):
        """Weather queries should target WeatherAnalyst."""
        result = await decomposer._run_async_impl(
            args={"question": "What are the current sea state and wave conditions for the Strait of Juan de Fuca"},
        )
        agents = result["all_agents"]
        assert "WeatherAnalyst" in agents

    @pytest.mark.asyncio
    async def test_vessel_traffic_query(self, decomposer):
        """Vessel traffic queries should target VesselTrafficMonitor."""
        result = await decomposer._run_async_impl(
            args={"question": "Show AIS vessel traffic density in shipping lanes near Los Angeles port"},
        )
        agents = result["all_agents"]
        assert "VesselTrafficMonitor" in agents

    @pytest.mark.asyncio
    async def test_habitat_query(self, decomposer):
        """Habitat queries should target HabitatAnalyst."""
        result = await decomposer._run_async_impl(
            args={"question": "Where are the krill feeding habitat hotspots and upwelling zones near Monterey Bay"},
        )
        agents = result["all_agents"]
        assert "HabitatAnalyst" in agents

    @pytest.mark.asyncio
    async def test_species_query(self, decomposer):
        """Species identification queries should target SpeciesIdentifier."""
        result = await decomposer._run_async_impl(
            args={"question": "What endangered whale species are protected in the IUCN red list with conservation status"},
        )
        agents = result["all_agents"]
        assert "SpeciesIdentifier" in agents

    @pytest.mark.asyncio
    async def test_incident_query(self, decomposer):
        """Historical incident queries should target IncidentAnalyst."""
        result = await decomposer._run_async_impl(
            args={"question": "Show historical whale strike incident records and mortality trends in the east coast"},
        )
        agents = result["all_agents"]
        assert "IncidentAnalyst" in agents

    @pytest.mark.asyncio
    async def test_compound_query_routes_to_multiple_specialists(self, decomposer):
        """A compound query mentioning multiple domains routes to multiple agents."""
        result = await decomposer._run_async_impl(
            args={
                "question": (
                    "Plan a safe route from Seattle to Anchorage; "
                    "what is the whale collision risk along the way; "
                    "and show seasonal migration patterns nearby"
                ),
            },
        )
        agents = set(result["all_agents"])
        # Should involve at least 2 distinct specialists
        assert len(agents) >= 2
        # The sub-questions should each have been split and routed
        assert result["count"] >= 2

    @pytest.mark.asyncio
    async def test_decomposer_returns_valid_structure(self, decomposer):
        """Every decomposition result must have the expected top-level keys."""
        result = await decomposer._run_async_impl(
            args={"question": "Is there collision danger for cargo ships near whale habitats"},
        )
        assert "original_question" in result
        assert "sub_questions" in result
        assert "routing_confidence" in result
        assert "count" in result
        assert "all_agents" in result
        assert "routing_method" in result
        # Sub-question structure
        sq = result["sub_questions"][0]
        assert "question" in sq
        assert "domain" in sq
        assert "target_agent" in sq
        assert "secondary_agents" in sq
        assert "priority" in sq
        assert "routing_confidence" in sq

    @pytest.mark.asyncio
    async def test_max_sub_questions_clamped(self, decomposer):
        """max_sub_questions is respected and clamped."""
        result = await decomposer._run_async_impl(
            args={
                "question": "route risk; weather conditions; whale sightings; traffic density; habitat data",
                "max_sub_questions": 2,
            },
        )
        assert result["count"] <= 2


# ============================================================================
# 2. Memory Plane: Session State Store / Retrieve
# ============================================================================


class TestMemoryPlaneSessionState:
    """Test the memory plane operations used in Steps 0, 3, and 6."""

    @pytest.mark.asyncio
    async def test_store_and_retrieve_in_evidence_namespace(self, memory_tool):
        store_result = await memory_tool._run_async_impl(
            args={
                "operation": "store",
                "key": "route_optimizer_response",
                "value": json.dumps({"waypoints": 5, "distance_nm": 1200}),
                "namespace": "evidence",
            },
        )
        assert store_result["success"] is True

        retrieve_result = await memory_tool._run_async_impl(
            args={
                "operation": "retrieve",
                "key": "route_optimizer_response",
                "namespace": "evidence",
            },
        )
        assert retrieve_result["success"] is True
        assert retrieve_result["found"] is True
        data = json.loads(retrieve_result["value"])
        assert data["waypoints"] == 5
        assert data["distance_nm"] == 1200

    @pytest.mark.asyncio
    async def test_store_intermediate_coverage_data(self, memory_tool):
        """Step 3: Store specialists_used and query_domain."""
        await memory_tool._run_async_impl(
            args={
                "operation": "store",
                "key": "specialists_used",
                "value": json.dumps(["RouteOptimizer", "RiskAssessor", "WeatherAnalyst"]),
                "namespace": "intermediate",
            },
        )
        await memory_tool._run_async_impl(
            args={
                "operation": "store",
                "key": "query_domain",
                "value": "route_optimization",
                "namespace": "intermediate",
            },
        )

        result = await memory_tool._run_async_impl(
            args={"operation": "list_keys", "namespace": "intermediate"},
        )
        assert result["success"] is True
        assert "specialists_used" in result["keys"]
        assert "query_domain" in result["keys"]

    @pytest.mark.asyncio
    async def test_append_evidence_from_multiple_specialists(self, memory_tool):
        """Step 3: Append evidence items from different specialist responses."""
        for specialist_data in [
            {"agent": "RouteOptimizer", "finding": "Route distance 1200nm"},
            {"agent": "RiskAssessor", "finding": "Risk level MODERATE"},
            {"agent": "WeatherAnalyst", "finding": "Sea state 3, wind 15kt"},
        ]:
            await memory_tool._run_async_impl(
                args={
                    "operation": "append",
                    "key": "specialist_findings",
                    "value": json.dumps(specialist_data),
                    "namespace": "evidence",
                },
            )

        result = await memory_tool._run_async_impl(
            args={
                "operation": "retrieve",
                "key": "specialist_findings",
                "namespace": "evidence",
            },
        )
        findings = json.loads(result["value"])
        assert len(findings) == 3
        agents = [f["agent"] for f in findings]
        assert "RouteOptimizer" in agents
        assert "RiskAssessor" in agents
        assert "WeatherAnalyst" in agents

    @pytest.mark.asyncio
    async def test_all_namespaces_isolated(self, memory_tool):
        """Keys in different namespaces do not leak across."""
        for ns in ("evidence", "intermediate", "citations", "verification", "learning"):
            await memory_tool._run_async_impl(
                args={
                    "operation": "store",
                    "key": "shared_key",
                    "value": f"value_for_{ns}",
                    "namespace": ns,
                },
            )

        for ns in ("evidence", "intermediate", "citations", "verification", "learning"):
            result = await memory_tool._run_async_impl(
                args={"operation": "retrieve", "key": "shared_key", "namespace": ns},
            )
            assert result["value"] == f"value_for_{ns}"

    @pytest.mark.asyncio
    async def test_clear_session_removes_all_namespaces(self, memory_tool):
        """clear_session wipes every namespace for the session."""
        for ns in ("evidence", "intermediate"):
            await memory_tool._run_async_impl(
                args={
                    "operation": "store",
                    "key": f"key_in_{ns}",
                    "value": "data",
                    "namespace": ns,
                },
            )

        clear_result = await memory_tool._run_async_impl(
            args={"operation": "clear_session"},
        )
        assert clear_result["success"] is True
        assert clear_result["cleared"] >= 2

        for ns in ("evidence", "intermediate"):
            result = await memory_tool._run_async_impl(
                args={"operation": "retrieve", "key": f"key_in_{ns}", "namespace": ns},
            )
            assert result["found"] is False


# ============================================================================
# 3. Cold Store: Persist & Query Session Outcomes
# ============================================================================


class TestColdStore:
    """Test that the cold store persists and retrieves session history."""

    def test_store_and_query_session_via_library(self, cold_db_path):
        """Direct library-level cold store round-trip."""
        conn = get_connection(cold_db_path)
        try:
            ok = store_session(
                conn,
                session_id="sess_001",
                query_text="Plan route from SF to Tokyo",
                query_domain="route_optimization",
                context={"origin": "SF", "destination": "Tokyo"},
                actions={"agents_called": ["RouteOptimizer", "RiskAssessor"]},
                outcomes={"risk_level": "MODERATE", "distance_nm": 4500},
                specialists_used=["RouteOptimizer", "RiskAssessor"],
                risk_level="MODERATE",
            )
            assert ok is True

            cursor = conn.execute(
                "SELECT * FROM session_outcomes WHERE session_id = ?",
                ("sess_001",),
            )
            row = cursor.fetchone()
            assert row is not None
            # session_id, query_text, query_domain, context, actions, outcomes, specialists_used, risk_level, created_at
            assert row[0] == "sess_001"
            assert row[1] == "Plan route from SF to Tokyo"
            assert row[2] == "route_optimization"
            assert json.loads(row[3])["origin"] == "SF"
            assert "RouteOptimizer" in json.loads(row[6])
        finally:
            conn.close()

    def test_store_route_pattern_and_query(self, cold_db_path):
        conn = get_connection(cold_db_path)
        try:
            ok = store_route_pattern(
                conn,
                origin_region="US_West_Coast",
                dest_region="Japan",
                risk_zones_avoided=3,
                distance_penalty_pct=4.5,
                fuel_penalty_pct=5.2,
                recommended_speed=12.0,
                season="winter",
            )
            assert ok is True

            patterns = query_patterns(conn, origin_region="US_West_Coast", season="winter")
            assert len(patterns) == 1
            assert patterns[0]["dest_region"] == "Japan"
            assert patterns[0]["risk_zones_avoided"] == 3
            assert patterns[0]["recommended_speed"] == 12.0
        finally:
            conn.close()

    def test_query_patterns_empty(self, cold_db_path):
        conn = get_connection(cold_db_path)
        try:
            patterns = query_patterns(conn, origin_region="Antarctica")
            assert patterns == []
        finally:
            conn.close()

    def test_get_strategies_empty(self, cold_db_path):
        conn = get_connection(cold_db_path)
        try:
            strategies = get_strategies(conn, region="Arctic")
            assert strategies == []
        finally:
            conn.close()

    @pytest.mark.asyncio
    async def test_cold_tool_store_session(self, cold_tool, cold_db_path):
        """ColdStoreTool.store_session round-trip through the DynamicTool interface."""
        result = await cold_tool._run_async_impl(
            args={
                "operation": "store_session",
                "session_id": "sess_tool_001",
                "query_text": "whale strike risk near SF",
                "query_domain": "risk_assessment",
                "context": json.dumps({"lat": 37.7749, "lng": -122.4194}),
                "outcomes": json.dumps({"risk_level": "HIGH"}),
            },
        )
        assert result["success"] is True

        # Verify via direct query
        conn = get_connection(cold_db_path)
        try:
            cursor = conn.execute(
                "SELECT query_domain FROM session_outcomes WHERE session_id = ?",
                ("sess_tool_001",),
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "risk_assessment"
        finally:
            conn.close()

    @pytest.mark.asyncio
    async def test_cold_tool_query_patterns(self, cold_tool, cold_db_path):
        """ColdStoreTool.query_patterns returns empty when no data exists."""
        result = await cold_tool._run_async_impl(
            args={"operation": "query_patterns", "region": "Pacific"},
        )
        assert result["success"] is True
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_cold_tool_get_strategies(self, cold_tool):
        result = await cold_tool._run_async_impl(
            args={"operation": "get_strategies", "season": "summer"},
        )
        assert result["success"] is True
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_cold_tool_unknown_operation(self, cold_tool):
        result = await cold_tool._run_async_impl(
            args={"operation": "delete_all"},
        )
        assert result["success"] is False
        assert "Unknown operation" in result["error"]


# ============================================================================
# 4. Memory Plane cold operations (seed_session / flush_cold / query_cold)
# ============================================================================


class TestMemoryPlaneColdOps:
    """Step 0 (seed_session), Step 6 (flush_cold), and query_cold."""

    @pytest.mark.asyncio
    async def test_seed_session_on_empty_db(self, memory_tool_with_cold):
        result = await memory_tool_with_cold._run_async_impl(
            args={"operation": "seed_session", "query": "safe route from LA to Hawaii"},
        )
        assert result["success"] is True
        # No historical data yet
        assert result.get("seeded") is False or result.get("past_domains") is not None

    @pytest.mark.asyncio
    async def test_flush_cold_persists_session(self, memory_tool_with_cold, cold_db_path):
        result = await memory_tool_with_cold._run_async_impl(
            args={
                "operation": "flush_cold",
                "query": "route from Seattle to Anchorage",
                "query_domain": "route_optimization",
            },
        )
        assert result["success"] is True
        assert result["flushed"] is True

        # Verify persistence in the same DB
        conn = get_connection(cold_db_path)
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM session_outcomes")
            count = cursor.fetchone()[0]
            assert count >= 1
        finally:
            conn.close()

    @pytest.mark.asyncio
    async def test_flush_then_seed_round_trip(self, memory_tool_with_cold):
        """After flushing a session, seed_session should find historical data."""
        # Flush a session first
        await memory_tool_with_cold._run_async_impl(
            args={
                "operation": "flush_cold",
                "query": "whale risk in Santa Barbara Channel",
                "query_domain": "risk_assessment",
            },
        )

        # Now seed should find it
        result = await memory_tool_with_cold._run_async_impl(
            args={"operation": "seed_session", "query": "another query"},
        )
        assert result["success"] is True
        assert result["seeded"] is True
        assert "risk_assessment" in result["past_domains"]

    @pytest.mark.asyncio
    async def test_query_cold_returns_flushed_data(self, memory_tool_with_cold):
        await memory_tool_with_cold._run_async_impl(
            args={
                "operation": "flush_cold",
                "query": "migration patterns in Bering Sea",
                "query_domain": "whale_migration",
            },
        )

        result = await memory_tool_with_cold._run_async_impl(
            args={"operation": "query_cold", "query": "migration"},
        )
        assert result["success"] is True
        assert len(result["results"]) >= 1
        assert result["results"][0]["query_domain"] == "whale_migration"


# ============================================================================
# 5. Report Generator: Synthesize Specialist Findings
# ============================================================================


class TestReportGenerator:
    """Step 4: report_generator produces structured reports from evidence."""

    @pytest.mark.asyncio
    async def test_route_recommendation_report(self, report_tool):
        evidence = {
            "RouteOptimizer": {
                "total_distance_nm": 1200,
                "estimated_fuel_impact_pct": 3.5,
                "waypoints": [
                    {"lat": 37.7749, "lng": -122.4194},
                    {"lat": 40.0, "lng": -130.0},
                    {"lat": 48.0, "lng": -135.0},
                ],
            },
            "RiskAssessor": {
                "collision_risk_score": 0.45,
                "risk_level": "MODERATE",
                "recommendation": "Reduce speed to 14 knots in Channel Islands zone",
            },
            "WeatherAnalyst": {
                "sea_state": 3,
                "wind_speed_kt": 15,
                "visibility_nm": 8,
            },
            "WhaleMigrationTracker": {
                "density": 0.6,
                "migration_phase": "northbound_feeding",
                "species_present": ["humpback_whale", "gray_whale"],
            },
        }

        result = await report_tool._run_async_impl(
            args={
                "question": "Plan a safe route from San Francisco to Seattle",
                "evidence": evidence,
                "report_mode": "route_recommendation",
            },
        )
        assert "formatted_report" in result
        assert result["report_mode"] == "route_recommendation"

        report = result["formatted_report"]
        assert "## Route Recommendation Report" in report
        assert "Route Details" in report
        assert "Risk Assessment" in report
        assert "MODERATE" in report
        assert "Weather Conditions" in report
        assert "Whale Migration" in report
        assert "humpback_whale" in report

    @pytest.mark.asyncio
    async def test_risk_assessment_report(self, report_tool):
        evidence = {
            "RiskAssessor": {
                "collision_risk_score": 0.78,
                "risk_level": "HIGH",
                "recommendation": "Immediate speed reduction and route diversion",
                "components": {
                    "whale_seasonal_factor": 0.85,
                    "traffic_density": 0.7,
                    "speed_risk": 1.0,
                },
            },
            "IncidentAnalyst": {
                "total_incidents": 12,
                "lethal_incidents": 3,
                "species_breakdown": {
                    "blue_whale": 5,
                    "fin_whale": 4,
                    "humpback_whale": 3,
                },
            },
        }

        result = await report_tool._run_async_impl(
            args={
                "question": "What is the collision risk in the Santa Barbara Channel",
                "evidence": evidence,
                "report_mode": "risk_assessment",
            },
        )
        report = result["formatted_report"]
        assert "## Risk Assessment Report" in report
        assert "Collision Risk Score" in report
        assert "HIGH" in report
        assert "Historical Incidents" in report
        assert "blue_whale" in report
        assert "12" in report  # total_incidents

    @pytest.mark.asyncio
    async def test_quick_answer_report(self, report_tool):
        evidence = {
            "SpeciesIdentifier": {
                "species": "Balaenoptera musculus",
                "common_name": "Blue Whale",
                "iucn_status": "Endangered",
            },
        }

        result = await report_tool._run_async_impl(
            args={
                "question": "What conservation status is the blue whale",
                "evidence": evidence,
                "report_mode": "quick_answer",
            },
        )
        report = result["formatted_report"]
        assert "## Quick Answer" in report
        assert "Endangered" in report

    @pytest.mark.asyncio
    async def test_report_invalid_mode(self, report_tool):
        result = await report_tool._run_async_impl(
            args={
                "question": "test",
                "evidence": {},
                "report_mode": "nonexistent_mode",
            },
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_report_lists_specialists_used(self, report_tool):
        evidence = {
            "RouteOptimizer": {"distance": 500},
            "RiskAssessor": {"risk": 0.3},
        }
        result = await report_tool._run_async_impl(
            args={
                "question": "test",
                "evidence": evidence,
                "report_mode": "quick_answer",
            },
        )
        assert set(result["specialists_used"]) == {"RouteOptimizer", "RiskAssessor"}


# ============================================================================
# 6. Map Renderer: Valid GeoJSON Output
# ============================================================================


class TestMapRenderer:
    """Step 4: map_renderer produces valid Deck.gl-compatible GeoJSON."""

    @pytest.mark.asyncio
    async def test_risk_heatmap_geojson(self, map_tool):
        data = [
            {"lat": 34.0, "lng": -119.5, "risk_score": 0.8},
            {"lat": 34.2, "lng": -119.3, "risk_score": 0.6},
            {"lat": 34.5, "lng": -119.0, "risk_score": 0.3},
        ]
        result = await map_tool._run_async_impl(
            args={"render_type": "risk_heatmap", "data": data},
        )
        self._assert_valid_feature_collection(result)
        assert result["metadata"]["render_type"] == "risk_heatmap"
        assert result["metadata"]["layer_type"] == "HeatmapLayer"
        assert len(result["features"]) == 3

        # Each feature should be a Point with risk property
        for feature in result["features"]:
            assert feature["geometry"]["type"] == "Point"
            assert len(feature["geometry"]["coordinates"]) == 2
            assert "risk" in feature["properties"]

    @pytest.mark.asyncio
    async def test_route_geojson_from_waypoints(self, map_tool):
        data = [
            {
                "name": "SF to Seattle",
                "distance_nm": 680,
                "waypoints": [
                    {"lat": 37.7749, "lng": -122.4194},
                    {"lat": 40.0, "lng": -124.0},
                    {"lat": 44.0, "lng": -124.5},
                    {"lat": 47.6, "lng": -122.3},
                ],
            }
        ]
        result = await map_tool._run_async_impl(
            args={"render_type": "route", "data": data},
        )
        self._assert_valid_feature_collection(result)
        assert result["metadata"]["render_type"] == "route"
        assert result["metadata"]["layer_type"] == "PathLayer"
        feature = result["features"][0]
        assert feature["geometry"]["type"] == "LineString"
        assert len(feature["geometry"]["coordinates"]) == 4

    @pytest.mark.asyncio
    async def test_route_geojson_from_flat_points(self, map_tool):
        """Route can also be rendered from a flat list of coordinate points."""
        data = [
            {"lat": 37.7749, "lng": -122.4194},
            {"lat": 40.0, "lng": -124.0},
            {"lat": 47.6, "lng": -122.3},
        ]
        result = await map_tool._run_async_impl(
            args={"render_type": "route", "data": data},
        )
        self._assert_valid_feature_collection(result)
        assert result["features"][0]["geometry"]["type"] == "LineString"
        assert len(result["features"][0]["geometry"]["coordinates"]) == 3

    @pytest.mark.asyncio
    async def test_sightings_geojson(self, map_tool):
        data = [
            {"lat": 34.0, "lng": -119.5, "species": "humpback_whale", "count": 3, "date": "2025-04-15"},
            {"lat": 34.2, "lng": -119.3, "species": "blue_whale", "count": 1, "date": "2025-04-14"},
        ]
        result = await map_tool._run_async_impl(
            args={"render_type": "sightings", "data": data},
        )
        self._assert_valid_feature_collection(result)
        assert result["metadata"]["layer_type"] == "ScatterplotLayer"
        for f in result["features"]:
            assert f["geometry"]["type"] == "Point"
            assert "species" in f["properties"]
            assert "count" in f["properties"]

    @pytest.mark.asyncio
    async def test_shipping_lanes_geojson(self, map_tool):
        data = [
            {
                "name": "TSS Lane Alpha",
                "density": 0.7,
                "waypoints": [
                    {"lat": 34.0, "lng": -119.5},
                    {"lat": 34.5, "lng": -118.5},
                ],
            },
        ]
        result = await map_tool._run_async_impl(
            args={"render_type": "shipping_lanes", "data": data},
        )
        self._assert_valid_feature_collection(result)
        feature = result["features"][0]
        assert feature["geometry"]["type"] == "LineString"
        assert feature["properties"]["density"] == 0.7

    @pytest.mark.asyncio
    async def test_migration_corridors_geojson(self, map_tool):
        data = [
            {
                "species": "gray_whale",
                "name": "Eastern Pacific Corridor",
                "waypoints": [
                    {"lat": 20.0, "lng": -110.0},
                    {"lat": 30.0, "lng": -118.0},
                    {"lat": 40.0, "lng": -124.0},
                    {"lat": 48.0, "lng": -125.0},
                ],
            },
        ]
        result = await map_tool._run_async_impl(
            args={"render_type": "migration_corridors", "data": data},
        )
        self._assert_valid_feature_collection(result)
        assert result["metadata"]["render_type"] == "migration_corridors"
        feature = result["features"][0]
        assert feature["properties"]["species"] == "gray_whale"
        assert len(feature["geometry"]["coordinates"]) == 4

    @pytest.mark.asyncio
    async def test_invalid_render_type(self, map_tool):
        result = await map_tool._run_async_impl(
            args={"render_type": "unknown_layer", "data": []},
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_empty_data_produces_empty_features(self, map_tool):
        for render_type in ("risk_heatmap", "sightings", "shipping_lanes", "migration_corridors"):
            result = await map_tool._run_async_impl(
                args={"render_type": render_type, "data": []},
            )
            self._assert_valid_feature_collection(result)
            assert result["features"] == []

    def _assert_valid_feature_collection(self, result: dict):
        """Assert the result is a valid GeoJSON FeatureCollection."""
        assert result["type"] == "FeatureCollection"
        assert "features" in result
        assert isinstance(result["features"], list)
        assert "metadata" in result
        for feature in result["features"]:
            assert feature["type"] == "Feature"
            assert "geometry" in feature
            assert "properties" in feature
            assert "type" in feature["geometry"]
            assert "coordinates" in feature["geometry"]


# ============================================================================
# 7. End-to-End Orchestration Flow (Steps 0-6)
# ============================================================================


class TestOrchestratorProtocolFlow:
    """
    Simulate the full 7-step orchestration protocol by calling the real
    tool implementations in sequence. This tests that all tools compose
    correctly without needing the SAM broker or LLM.
    """

    @pytest.mark.asyncio
    async def test_full_route_planning_flow(
        self, decomposer, memory_tool_with_cold, report_tool, map_tool, route_tool, risk_tool
    ):
        """Simulate the complete orchestrator protocol for a route planning query."""
        question = "Plan the safest shipping route from San Francisco to Tokyo avoiding whale zones"

        # -- Step 0: SEED --
        seed_result = await memory_tool_with_cold._run_async_impl(
            args={"operation": "seed_session", "query": question},
        )
        assert seed_result["success"] is True

        # -- Step 1: PLAN --
        plan_result = await decomposer._run_async_impl(
            args={"question": question},
        )
        assert plan_result["count"] >= 1
        all_agents = plan_result["all_agents"]
        assert len(all_agents) >= 1

        # -- Step 2: DELEGATE (simulate specialist responses) --
        # In a real system, the orchestrator calls peer_* tools here.
        # We simulate by calling our computation tools directly.
        route_result = compute_route(
            origin_lat=37.7749, origin_lng=-122.4194,
            dest_lat=35.6762, dest_lng=139.6503,
            risk_zones=[
                {"lat": 40.0, "lng": -155.0, "radius_km": 80, "risk_score": 0.8},
                {"lat": 35.0, "lng": -170.0, "radius_km": 60, "risk_score": 0.6},
            ],
        )
        assert route_result["total_distance_nm"] > 0
        assert len(route_result["waypoints"]) >= 2

        risk_result = compute_risk(
            latitude=40.0, longitude=-155.0,
            month=4, whale_density=0.7,
            vessel_traffic_density=0.5, vessel_speed_knots=16.0,
        )
        assert risk_result["risk_level"] in ("LOW", "MODERATE", "HIGH")

        # -- Step 3: COLLECT --
        # Store specialist evidence in memory plane
        await memory_tool_with_cold._run_async_impl(
            args={
                "operation": "store",
                "key": "specialists_used",
                "value": json.dumps(all_agents),
                "namespace": "intermediate",
            },
        )
        await memory_tool_with_cold._run_async_impl(
            args={
                "operation": "store",
                "key": "route_optimizer_response",
                "value": json.dumps({
                    "total_distance_nm": route_result["total_distance_nm"],
                    "waypoints": route_result["waypoints"][:3],  # truncate for storage
                    "estimated_fuel_impact_pct": route_result["estimated_fuel_impact_pct"],
                }),
                "namespace": "evidence",
            },
        )
        await memory_tool_with_cold._run_async_impl(
            args={
                "operation": "store",
                "key": "risk_assessor_response",
                "value": json.dumps(risk_result),
                "namespace": "evidence",
            },
        )

        # Verify coverage check
        stored_specialists = await memory_tool_with_cold._run_async_impl(
            args={"operation": "retrieve", "key": "specialists_used", "namespace": "intermediate"},
        )
        assert stored_specialists["found"] is True

        # -- Step 4: SYNTHESIZE --
        evidence = {
            "RouteOptimizer": {
                "total_distance_nm": route_result["total_distance_nm"],
                "estimated_fuel_impact_pct": route_result["estimated_fuel_impact_pct"],
                "waypoints": route_result["waypoints"][:3],
            },
            "RiskAssessor": {
                "collision_risk_score": risk_result["collision_risk_score"],
                "risk_level": risk_result["risk_level"],
                "recommendation": risk_result["recommendation"],
            },
        }

        report_result = await report_tool._run_async_impl(
            args={
                "question": question,
                "evidence": evidence,
                "report_mode": "route_recommendation",
            },
        )
        assert "formatted_report" in report_result
        assert "Route Recommendation Report" in report_result["formatted_report"]
        assert risk_result["risk_level"] in report_result["formatted_report"]

        # Map rendering: render the route and risk heatmap layers
        route_geojson = await map_tool._run_async_impl(
            args={
                "render_type": "route",
                "data": [
                    {
                        "name": "SF to Tokyo (safe route)",
                        "distance_nm": route_result["total_distance_nm"],
                        "waypoints": route_result["waypoints"][:5],
                    }
                ],
            },
        )
        assert route_geojson["type"] == "FeatureCollection"
        assert len(route_geojson["features"]) >= 1

        risk_geojson = await map_tool._run_async_impl(
            args={
                "render_type": "risk_heatmap",
                "data": [
                    {"lat": 40.0, "lng": -155.0, "risk_score": risk_result["collision_risk_score"]},
                    {"lat": 35.0, "lng": -170.0, "risk_score": 0.6},
                ],
            },
        )
        assert risk_geojson["type"] == "FeatureCollection"
        assert len(risk_geojson["features"]) == 2

        # -- Step 5: VERIFY + REVISE --
        # In the real system, this delegates to peer_Verifier. Here we
        # just verify the report is non-empty and structurally valid.
        assert len(report_result["formatted_report"]) > 100

        # -- Step 6: PERSIST --
        flush_result = await memory_tool_with_cold._run_async_impl(
            args={
                "operation": "flush_cold",
                "query": question,
                "query_domain": "route_optimization",
            },
        )
        assert flush_result["success"] is True
        assert flush_result["flushed"] is True

        # Verify cold store has the data
        cold_result = await memory_tool_with_cold._run_async_impl(
            args={"operation": "query_cold", "query": question},
        )
        assert cold_result["success"] is True
        assert len(cold_result["results"]) >= 1

    @pytest.mark.asyncio
    async def test_full_risk_assessment_flow(
        self, decomposer, memory_tool_with_cold, report_tool, map_tool, risk_tool
    ):
        """Simulate the protocol for a risk assessment query."""
        question = "What is the whale collision risk for vessels transiting the Santa Barbara Channel"

        # Step 0: SEED
        seed = await memory_tool_with_cold._run_async_impl(
            args={"operation": "seed_session", "query": question},
        )
        assert seed["success"] is True

        # Step 1: PLAN
        plan = await decomposer._run_async_impl(args={"question": question})
        assert plan["count"] >= 1
        agents = plan["all_agents"]
        # Should route to risk-related agents
        assert any(a in agents for a in ["RiskAssessor", "IncidentAnalyst", "VesselTrafficMonitor"])

        # Step 2: DELEGATE (simulated)
        risk = compute_risk(
            latitude=34.4, longitude=-119.8,
            month=3, whale_density=0.8,
            vessel_traffic_density=0.6, vessel_speed_knots=18.0,
        )
        assert risk["collision_risk_score"] > 0

        # Step 3: COLLECT
        await memory_tool_with_cold._run_async_impl(
            args={
                "operation": "store",
                "key": "risk_response",
                "value": json.dumps(risk),
                "namespace": "evidence",
            },
        )

        # Step 4: SYNTHESIZE
        evidence = {
            "RiskAssessor": {
                "collision_risk_score": risk["collision_risk_score"],
                "risk_level": risk["risk_level"],
                "recommendation": risk["recommendation"],
                "components": risk["components"],
            },
            "IncidentAnalyst": {
                "total_incidents": 8,
                "lethal_incidents": 2,
                "species_breakdown": {"blue_whale": 3, "fin_whale": 5},
            },
        }

        report = await report_tool._run_async_impl(
            args={
                "question": question,
                "evidence": evidence,
                "report_mode": "risk_assessment",
            },
        )
        assert "Risk Assessment Report" in report["formatted_report"]
        assert risk["risk_level"] in report["formatted_report"]
        assert "Historical Incidents" in report["formatted_report"]

        # Map: risk heatmap layer
        heatmap = await map_tool._run_async_impl(
            args={
                "render_type": "risk_heatmap",
                "data": [{"lat": 34.4, "lng": -119.8, "risk_score": risk["collision_risk_score"]}],
            },
        )
        assert heatmap["type"] == "FeatureCollection"

        # Step 6: PERSIST
        flush = await memory_tool_with_cold._run_async_impl(
            args={
                "operation": "flush_cold",
                "query": question,
                "query_domain": "risk_assessment",
            },
        )
        assert flush["success"] is True

    @pytest.mark.asyncio
    async def test_quick_answer_flow(
        self, decomposer, memory_tool_with_cold, report_tool
    ):
        """Simulate a simple factual query that uses quick_answer mode."""
        question = "What whale species are endangered in the North Pacific"

        seed = await memory_tool_with_cold._run_async_impl(
            args={"operation": "seed_session", "query": question},
        )
        assert seed["success"] is True

        plan = await decomposer._run_async_impl(args={"question": question})
        assert plan["count"] >= 1
        # Should target SpeciesIdentifier
        assert "SpeciesIdentifier" in plan["all_agents"]

        evidence = {
            "SpeciesIdentifier": {
                "species_list": [
                    {"common_name": "Blue Whale", "iucn_status": "Endangered"},
                    {"common_name": "Sei Whale", "iucn_status": "Endangered"},
                    {"common_name": "North Pacific Right Whale", "iucn_status": "Critically Endangered"},
                ],
            },
        }

        report = await report_tool._run_async_impl(
            args={
                "question": question,
                "evidence": evidence,
                "report_mode": "quick_answer",
            },
        )
        assert "Quick Answer" in report["formatted_report"]
        assert "SpeciesIdentifier" in report["specialists_used"]

        flush = await memory_tool_with_cold._run_async_impl(
            args={
                "operation": "flush_cold",
                "query": question,
                "query_domain": "species",
            },
        )
        assert flush["success"] is True


# ============================================================================
# 8. Cross-Tool Integration: Route Calculator -> Risk Scorer -> Map Renderer
# ============================================================================


class TestToolChainIntegration:
    """Test that outputs from one tool feed correctly into the next."""

    @pytest.mark.asyncio
    async def test_route_output_feeds_risk_scorer(self, route_tool, risk_tool):
        """Route waypoints can be used to compute risk at each point."""
        route = await route_tool._run_async_impl(
            args={
                "origin_lat": 37.7749,
                "origin_lng": -122.4194,
                "dest_lat": 47.6062,
                "dest_lng": -122.3321,
            },
        )
        waypoints = route["waypoints"]
        assert len(waypoints) >= 2

        # Score risk at each waypoint
        risk_scores = []
        for wp in waypoints:
            risk = await risk_tool._run_async_impl(
                args={
                    "latitude": wp["lat"],
                    "longitude": wp["lng"],
                    "month": 4,
                    "whale_density": 0.5,
                    "vessel_traffic_density": 0.3,
                    "vessel_speed_knots": 14.0,
                },
            )
            assert "collision_risk_score" in risk
            risk_scores.append(risk)

        assert len(risk_scores) == len(waypoints)
        assert all(0 <= r["collision_risk_score"] <= 1 for r in risk_scores)

    @pytest.mark.asyncio
    async def test_route_output_feeds_map_renderer(self, route_tool, map_tool):
        """Route calculator output can be rendered as a map layer."""
        route = await route_tool._run_async_impl(
            args={
                "origin_lat": 34.0522,
                "origin_lng": -118.2437,
                "dest_lat": 21.3069,
                "dest_lng": -157.8583,
            },
        )
        waypoints = route["waypoints"]

        geojson = await map_tool._run_async_impl(
            args={
                "render_type": "route",
                "data": [
                    {
                        "name": "LA to Honolulu",
                        "distance_nm": route["total_distance_nm"],
                        "waypoints": waypoints,
                    },
                ],
            },
        )
        assert geojson["type"] == "FeatureCollection"
        line = geojson["features"][0]
        assert line["geometry"]["type"] == "LineString"
        # Coordinates should match waypoint count
        assert len(line["geometry"]["coordinates"]) == len(waypoints)

    @pytest.mark.asyncio
    async def test_risk_scores_feed_map_heatmap(self, risk_tool, map_tool):
        """Risk scores from multiple points become a heatmap layer."""
        points = [
            (34.0, -119.5, 0.8, 0.6, 16.0),
            (34.2, -119.3, 0.5, 0.4, 14.0),
            (34.5, -119.0, 0.2, 0.3, 10.0),
        ]

        risk_data = []
        for lat, lng, wd, td, speed in points:
            risk = await risk_tool._run_async_impl(
                args={
                    "latitude": lat,
                    "longitude": lng,
                    "month": 4,
                    "whale_density": wd,
                    "vessel_traffic_density": td,
                    "vessel_speed_knots": speed,
                },
            )
            risk_data.append({
                "lat": lat,
                "lng": lng,
                "risk_score": risk["collision_risk_score"],
            })

        heatmap = await map_tool._run_async_impl(
            args={"render_type": "risk_heatmap", "data": risk_data},
        )
        assert heatmap["type"] == "FeatureCollection"
        assert len(heatmap["features"]) == 3
        # Higher whale density / speed should produce higher risk
        scores = [f["properties"]["risk"] for f in heatmap["features"]]
        assert scores[0] > scores[2]  # first point has higher density+speed

    @pytest.mark.asyncio
    async def test_route_with_avoidance_feeds_report(self, route_tool, risk_tool, report_tool):
        """Full chain: route with risk zones -> risk scoring -> report."""
        risk_zones = [
            {"lat": 38.0, "lng": -123.5, "radius_km": 40, "risk_score": 0.9},
        ]
        route = await route_tool._run_async_impl(
            args={
                "origin_lat": 37.7749,
                "origin_lng": -122.4194,
                "dest_lat": 38.5,
                "dest_lng": -123.5,
                "risk_zones": risk_zones,
            },
        )

        mid_wp = route["waypoints"][len(route["waypoints"]) // 2]
        risk = await risk_tool._run_async_impl(
            args={
                "latitude": mid_wp["lat"],
                "longitude": mid_wp["lng"],
                "month": 4,
                "whale_density": 0.9,
                "vessel_traffic_density": 0.5,
                "vessel_speed_knots": 12.0,
            },
        )

        evidence = {
            "RouteOptimizer": {
                "total_distance_nm": route["total_distance_nm"],
                "estimated_fuel_impact_pct": route["estimated_fuel_impact_pct"],
                "waypoints": route["waypoints"],
            },
            "RiskAssessor": {
                "collision_risk_score": risk["collision_risk_score"],
                "risk_level": risk["risk_level"],
                "recommendation": risk["recommendation"],
            },
        }
        report = await report_tool._run_async_impl(
            args={
                "question": "Safe route from SF to coastal waypoint avoiding whale zone",
                "evidence": evidence,
                "report_mode": "route_recommendation",
            },
        )
        assert "Route Recommendation Report" in report["formatted_report"]
        assert str(route["total_distance_nm"]) in report["formatted_report"]

    @pytest.mark.asyncio
    async def test_decomposer_into_memory_into_cold_store(
        self, decomposer, memory_tool_with_cold
    ):
        """Plan -> store routing in memory -> flush to cold -> query cold."""
        question = "What is the whale migration pattern near the Aleutian Islands and what is the collision risk"

        # Plan
        plan = await decomposer._run_async_impl(args={"question": question})
        assert plan["count"] >= 1

        # Store routing info in memory
        await memory_tool_with_cold._run_async_impl(
            args={
                "operation": "store",
                "key": "routing_plan",
                "value": json.dumps({
                    "all_agents": plan["all_agents"],
                    "routing_method": plan["routing_method"],
                    "routing_confidence": plan["routing_confidence"],
                }),
                "namespace": "intermediate",
            },
        )

        # Retrieve to verify
        retrieved = await memory_tool_with_cold._run_async_impl(
            args={"operation": "retrieve", "key": "routing_plan", "namespace": "intermediate"},
        )
        stored_plan = json.loads(retrieved["value"])
        assert stored_plan["all_agents"] == plan["all_agents"]

        # Flush to cold store
        flush = await memory_tool_with_cold._run_async_impl(
            args={
                "operation": "flush_cold",
                "query": question,
                "query_domain": plan["sub_questions"][0]["domain"],
            },
        )
        assert flush["success"] is True

        # Query cold store for historical data
        cold = await memory_tool_with_cold._run_async_impl(
            args={"operation": "query_cold", "query": question},
        )
        assert cold["success"] is True
        assert len(cold["results"]) >= 1
        assert cold["results"][0]["query_text"] == question
