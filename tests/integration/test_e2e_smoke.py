"""End-to-end smoke tests for the whale agent project.

Verifies that:
1. Each MCP server module imports and has expected tools registered.
2. Each custom DynamicTool subclass can be instantiated.
3. Each tool's _run_async_impl handles basic inputs without crashing.
4. Core tools produce valid output structures (risk_scorer, route_calculator,
   map_renderer, fuel_estimator, query_decomposer).

All tests are self-contained -- no external API calls, no running servers.
HTTP calls are mocked via unittest.mock.patch on the resilient_get helper.
"""

import importlib
import json
import os
import sys
import tempfile
from unittest.mock import patch

import pytest

# Ensure src is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))


# ============================================================================
# Section 1: MCP server imports and tool registration
# ============================================================================


MCP_SERVERS = [
    ("mcp_servers.noaa.server", "noaa", ["get_marine_forecast", "get_buoy_data"]),
    ("mcp_servers.open_meteo.server", "open_meteo", ["get_marine_conditions"]),
    ("mcp_servers.whale_alert.server", "whale_alert", ["get_whale_sightings"]),
    ("mcp_servers.gbif.server", "gbif", ["search_whale_occurrences"]),
    ("mcp_servers.iucn.server", "iucn", ["get_species_status", "get_species_by_region"]),
    (
        "mcp_servers.marine_cadastre.server",
        "marine_cadastre",
        ["get_vessel_traffic", "get_shipping_lane_density"],
    ),
]


@pytest.mark.parametrize("module_path,server_name,expected_tools", MCP_SERVERS)
def test_mcp_server_import_and_tools(module_path, server_name, expected_tools):
    """Each MCP server module imports without error and its FastMCP instance
    has the expected tool functions registered."""
    mod = importlib.import_module(module_path)
    mcp_instance = getattr(mod, "mcp")
    assert mcp_instance is not None
    assert mcp_instance.name == server_name

    # FastMCP stores tool functions; get registered tool names.
    registered = set()
    if hasattr(mcp_instance, "_tool_manager"):
        tm = mcp_instance._tool_manager
        if hasattr(tm, "_tools"):
            registered = set(tm._tools.keys())
        elif hasattr(tm, "tools"):
            registered = set(tm.tools.keys())
    elif hasattr(mcp_instance, "tools"):
        registered = set(mcp_instance.tools.keys())

    for tool_name in expected_tools:
        assert tool_name in registered, (
            f"Tool '{tool_name}' not found in {server_name}. "
            f"Registered: {registered}"
        )


# ============================================================================
# Section 2: Custom whale tool instantiation
# ============================================================================


TOOL_CLASSES = [
    ("whale_tools.risk_scorer", "RiskScorerTool"),
    ("whale_tools.route_calculator", "RouteCalculatorTool"),
    ("whale_tools.map_renderer", "MapRendererTool"),
    ("whale_tools.fuel_estimator", "FuelEstimatorTool"),
    ("whale_tools.query_decomposer", "QueryDecomposerTool"),
    ("whale_tools.cold_store", "ColdStoreTool"),
    ("whale_tools.habitat_mapper", "HabitatMapperTool"),
    ("whale_tools.incident_analyzer", "IncidentAnalyzerTool"),
    ("whale_tools.memory_plane", "MemoryPlaneTool"),
    ("whale_tools.migration_model", "MigrationModelTool"),
    ("whale_tools.report_generator", "ReportGeneratorTool"),
    ("whale_tools.traffic_density", "TrafficDensityTool"),
]


@pytest.mark.parametrize("module_path,class_name", TOOL_CLASSES)
def test_tool_class_instantiation(module_path, class_name):
    """Each DynamicTool subclass can be constructed and exposes the
    expected properties: tool_name, tool_description, parameters_schema."""
    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    tool = cls()
    assert isinstance(tool.tool_name, str)
    assert len(tool.tool_name) > 0
    assert isinstance(tool.tool_description, str)
    assert len(tool.tool_description) > 0
    assert tool.parameters_schema is not None


# ============================================================================
# Section 3: Tool _run_async_impl smoke tests (no HTTP, no LLM)
# ============================================================================


@pytest.mark.asyncio
async def test_risk_scorer_run():
    """RiskScorerTool produces a valid risk dict with expected keys."""
    from whale_tools.risk_scorer import RiskScorerTool

    tool = RiskScorerTool()
    result = await tool._run_async_impl(
        args={
            "latitude": 37.0,
            "longitude": -122.0,
            "month": 4,
            "whale_density": 0.8,
            "vessel_traffic_density": 0.6,
            "vessel_speed_knots": 15.0,
        }
    )
    assert "collision_risk_score" in result
    assert "risk_level" in result
    assert "recommendation" in result
    assert "components" in result
    assert 0 <= result["collision_risk_score"] <= 1
    assert result["risk_level"] in ("LOW", "MODERATE", "HIGH")


@pytest.mark.asyncio
async def test_route_calculator_run():
    """RouteCalculatorTool produces waypoints and distances."""
    from whale_tools.route_calculator import RouteCalculatorTool

    tool = RouteCalculatorTool()
    result = await tool._run_async_impl(
        args={
            "origin_lat": 34.0,
            "origin_lng": -118.0,
            "dest_lat": 37.8,
            "dest_lng": -122.4,
        }
    )
    assert "waypoints" in result
    assert "total_distance_nm" in result
    assert "direct_distance_nm" in result
    assert "geojson" in result
    assert len(result["waypoints"]) >= 2
    assert result["total_distance_nm"] > 0


@pytest.mark.asyncio
async def test_map_renderer_risk_heatmap():
    """MapRendererTool renders risk_heatmap as valid GeoJSON."""
    from whale_tools.map_renderer import MapRendererTool

    tool = MapRendererTool()
    result = await tool._run_async_impl(
        args={
            "render_type": "risk_heatmap",
            "data": [
                {"lat": 37.0, "lng": -122.0, "risk": 0.8},
                {"lat": 37.5, "lng": -122.5, "risk": 0.3},
            ],
        }
    )
    assert result["type"] == "FeatureCollection"
    assert len(result["features"]) == 2
    assert result["metadata"]["render_type"] == "risk_heatmap"
    for feature in result["features"]:
        assert feature["type"] == "Feature"
        assert feature["geometry"]["type"] == "Point"
        assert len(feature["geometry"]["coordinates"]) == 2


@pytest.mark.asyncio
async def test_map_renderer_route():
    """MapRendererTool renders a route as valid GeoJSON LineString."""
    from whale_tools.map_renderer import MapRendererTool

    tool = MapRendererTool()
    result = await tool._run_async_impl(
        args={
            "render_type": "route",
            "data": [
                {
                    "waypoints": [
                        {"lat": 34.0, "lng": -118.0},
                        {"lat": 35.5, "lng": -120.0},
                        {"lat": 37.8, "lng": -122.4},
                    ],
                    "distance_nm": 350,
                    "name": "Test Route",
                }
            ],
        }
    )
    assert result["type"] == "FeatureCollection"
    assert len(result["features"]) == 1
    assert result["features"][0]["geometry"]["type"] == "LineString"
    assert len(result["features"][0]["geometry"]["coordinates"]) == 3


@pytest.mark.asyncio
async def test_map_renderer_sightings():
    """MapRendererTool renders sightings as valid GeoJSON Points."""
    from whale_tools.map_renderer import MapRendererTool

    tool = MapRendererTool()
    result = await tool._run_async_impl(
        args={
            "render_type": "sightings",
            "data": [
                {"lat": 37.0, "lng": -122.0, "species": "blue_whale", "count": 2},
            ],
        }
    )
    assert result["type"] == "FeatureCollection"
    assert result["features"][0]["properties"]["species"] == "blue_whale"


@pytest.mark.asyncio
async def test_map_renderer_unknown_type():
    """MapRendererTool returns an error dict for unknown render types."""
    from whale_tools.map_renderer import MapRendererTool

    tool = MapRendererTool()
    result = await tool._run_async_impl(
        args={"render_type": "bad_type", "data": []}
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_fuel_estimator_run():
    """FuelEstimatorTool returns fuel impact numbers."""
    from whale_tools.fuel_estimator import FuelEstimatorTool

    tool = FuelEstimatorTool()
    result = await tool._run_async_impl(
        args={
            "route_distance_nm": 520.0,
            "original_distance_nm": 500.0,
            "speed_knots": 14.0,
        }
    )
    assert "fuel_impact_pct" in result
    assert "extra_fuel_liters" in result
    assert "time_delta_hours" in result
    assert "total_fuel_liters" in result
    assert result["extra_fuel_liters"] >= 0
    assert result["fuel_impact_pct"] > 0  # route is longer than original


@pytest.mark.asyncio
async def test_query_decomposer_route_question():
    """QueryDecomposerTool routes a route-planning question correctly."""
    from whale_tools.query_decomposer import QueryDecomposerTool

    tool = QueryDecomposerTool()  # No model configured -> keyword fallback
    result = await tool._run_async_impl(
        args={"question": "What is the safest route from LA to San Francisco avoiding whale areas?"}
    )
    assert "sub_questions" in result
    assert "all_agents" in result
    assert "routing_method" in result
    assert result["routing_method"] == "keyword"
    assert len(result["sub_questions"]) >= 1
    assert len(result["all_agents"]) >= 1
    # Should include RouteOptimizer for a route question
    assert "RouteOptimizer" in result["all_agents"]


@pytest.mark.asyncio
async def test_query_decomposer_risk_question():
    """QueryDecomposerTool routes a risk question to RiskAssessor."""
    from whale_tools.query_decomposer import QueryDecomposerTool

    tool = QueryDecomposerTool()
    result = await tool._run_async_impl(
        args={"question": "What is the collision risk for vessels near Stellwagen Bank?"}
    )
    assert result["routing_method"] == "keyword"
    agents = result["all_agents"]
    has_risk_agent = any(
        a in agents for a in ["RiskAssessor", "IncidentAnalyst"]
    )
    assert has_risk_agent, f"Expected risk/incident agent in {agents}"


@pytest.mark.asyncio
async def test_query_decomposer_compound_question():
    """QueryDecomposerTool splits compound questions using conjunctions."""
    from whale_tools.query_decomposer import QueryDecomposerTool

    tool = QueryDecomposerTool()
    result = await tool._run_async_impl(
        args={
            "question": (
                "What is the whale migration forecast for March "
                "and also what is the vessel traffic density in the Santa Barbara Channel?"
            )
        }
    )
    assert result["count"] >= 2, f"Expected >=2 sub-questions, got {result['count']}"


@pytest.mark.asyncio
async def test_query_decomposer_empty_question():
    """QueryDecomposerTool returns error for empty question."""
    from whale_tools.query_decomposer import QueryDecomposerTool

    tool = QueryDecomposerTool()
    result = await tool._run_async_impl(args={"question": ""})
    assert "error" in result


@pytest.mark.asyncio
async def test_habitat_mapper_run():
    """HabitatMapperTool finds hotspots near Monterey Bay."""
    from whale_tools.habitat_mapper import HabitatMapperTool

    tool = HabitatMapperTool()
    result = await tool._run_async_impl(
        args={"latitude": 36.8, "longitude": -121.9, "radius_km": 50}
    )
    assert "hotspots" in result
    assert result["count"] >= 1
    assert result["hotspots"][0]["name"] == "Monterey Bay"


@pytest.mark.asyncio
async def test_incident_analyzer_run():
    """IncidentAnalyzerTool returns incidents near San Francisco."""
    from whale_tools.incident_analyzer import IncidentAnalyzerTool

    tool = IncidentAnalyzerTool()
    result = await tool._run_async_impl(
        args={"latitude": 37.6, "longitude": -122.5, "radius_km": 100}
    )
    assert "incidents" in result
    assert "total_incidents" in result
    assert "species_breakdown" in result
    assert result["total_incidents"] >= 1


@pytest.mark.asyncio
async def test_migration_model_run():
    """MigrationModelTool returns density for US West Coast in July."""
    from whale_tools.migration_model import MigrationModelTool

    tool = MigrationModelTool()
    result = await tool._run_async_impl(
        args={"latitude": 37.0, "longitude": -122.0, "month": 7}
    )
    assert "density" in result
    assert "species_present" in result
    assert "migration_phase" in result
    assert result["density"] > 0
    assert len(result["species_present"]) >= 1


@pytest.mark.asyncio
async def test_migration_model_open_ocean():
    """MigrationModelTool returns zero density for open ocean."""
    from whale_tools.migration_model import MigrationModelTool

    tool = MigrationModelTool()
    result = await tool._run_async_impl(
        args={"latitude": 0.0, "longitude": 0.0, "month": 6}
    )
    assert result["density"] == 0.0
    assert result["region"] == "open_ocean"


@pytest.mark.asyncio
async def test_report_generator_quick_answer():
    """ReportGeneratorTool produces a formatted quick_answer report."""
    from whale_tools.report_generator import ReportGeneratorTool

    tool = ReportGeneratorTool()
    result = await tool._run_async_impl(
        args={
            "question": "What is the risk near Monterey Bay?",
            "evidence": {
                "RiskAssessor": {"collision_risk_score": 0.65, "risk_level": "MODERATE"},
            },
            "report_mode": "quick_answer",
        }
    )
    assert "formatted_report" in result
    assert "Quick Answer" in result["formatted_report"]
    assert result["report_mode"] == "quick_answer"


@pytest.mark.asyncio
async def test_report_generator_route_recommendation():
    """ReportGeneratorTool produces a route recommendation report."""
    from whale_tools.report_generator import ReportGeneratorTool

    tool = ReportGeneratorTool()
    result = await tool._run_async_impl(
        args={
            "question": "Plan a safe route from LA to SF",
            "evidence": {
                "route_calculator": {
                    "total_distance_nm": 350,
                    "estimated_fuel_impact_pct": 2.5,
                    "waypoints": [{"lat": 34, "lng": -118}, {"lat": 37.8, "lng": -122.4}],
                },
                "risk_scorer": {
                    "collision_risk_score": 0.45,
                    "risk_level": "MODERATE",
                    "recommendation": "Reduce speed.",
                },
            },
            "report_mode": "route_recommendation",
        }
    )
    assert "formatted_report" in result
    assert "Route Recommendation" in result["formatted_report"]


@pytest.mark.asyncio
async def test_report_generator_risk_assessment():
    """ReportGeneratorTool produces a risk assessment report."""
    from whale_tools.report_generator import ReportGeneratorTool

    tool = ReportGeneratorTool()
    result = await tool._run_async_impl(
        args={
            "question": "Assess collision risk near Stellwagen Bank",
            "evidence": {
                "risk_scorer": {
                    "collision_risk_score": 0.82,
                    "risk_level": "HIGH",
                    "recommendation": "Speed reduction.",
                    "components": {"whale_seasonal_factor": 0.7},
                },
                "incident_analyzer": {
                    "total_incidents": 5,
                    "lethal_incidents": 2,
                    "species_breakdown": {"right_whale": 3},
                },
            },
            "report_mode": "risk_assessment",
        }
    )
    assert "formatted_report" in result
    assert "Risk Assessment" in result["formatted_report"]
    assert "HIGH" in result["formatted_report"]


@pytest.mark.asyncio
async def test_traffic_density_run():
    """TrafficDensityTool returns a grid (may be empty with no AIS data file)."""
    from whale_tools.traffic_density import TrafficDensityTool, compute_density_grid

    # Call compute_density_grid directly with empty AIS data to avoid file I/O
    result = compute_density_grid(
        min_lat=33.0,
        min_lng=-119.0,
        max_lat=35.0,
        max_lng=-117.0,
        grid_resolution=1.0,
        ais_data=[
            {"latitude": 34.0, "longitude": -118.0, "speed_knots": 12.0, "vessel_type": "cargo"},
            {"latitude": 34.5, "longitude": -118.5, "speed_knots": 15.0, "vessel_type": "tanker"},
        ],
    )
    assert "grid_cells" in result
    assert "total_vessels_in_bbox" in result
    assert result["total_vessels_in_bbox"] == 2
    assert result["cells_with_traffic"] >= 1

    # Also verify the tool wrapper handles inputs without crashing
    tool = TrafficDensityTool()
    # Patch internal data loading to avoid needing the real file
    with patch("whale_tools.traffic_density._load_ais_data", return_value=[]):
        tool_result = await tool._run_async_impl(
            args={"min_lat": 33.0, "min_lng": -119.0, "max_lat": 35.0, "max_lng": -117.0}
        )
    assert "grid_cells" in tool_result
    assert tool_result["total_vessels_in_bbox"] == 0


@pytest.mark.asyncio
async def test_cold_store_store_and_query():
    """ColdStoreTool stores and queries session data using a temp DB."""
    from whale_tools.cold_store import ColdStoreTool

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        tool = ColdStoreTool(tool_config={"db_path": db_path})

        # Store a session
        store_result = await tool._run_async_impl(
            args={
                "operation": "store_session",
                "session_id": "smoke-test-001",
                "query_text": "Test route question",
                "query_domain": "route_optimization",
            }
        )
        assert store_result.get("success") is True

        # Query patterns (should return empty since we only stored a session)
        query_result = await tool._run_async_impl(
            args={"operation": "query_patterns"}
        )
        assert query_result.get("success") is True
        assert "patterns" in query_result

        # Get strategies (should return empty)
        strat_result = await tool._run_async_impl(
            args={"operation": "get_strategies"}
        )
        assert strat_result.get("success") is True
        assert "strategies" in strat_result

        # Unknown operation
        err_result = await tool._run_async_impl(
            args={"operation": "bad_op"}
        )
        assert err_result.get("success") is False
        assert "error" in err_result
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_memory_plane_store_and_retrieve():
    """MemoryPlaneTool stores and retrieves values in-memory."""
    from whale_tools.memory_plane import MemoryPlaneTool

    tool = MemoryPlaneTool()

    # Store
    store_result = await tool._run_async_impl(
        args={
            "operation": "store",
            "key": "test_key",
            "value": json.dumps({"data": "hello"}),
            "namespace": "evidence",
        }
    )
    assert store_result["success"] is True

    # Retrieve
    retrieve_result = await tool._run_async_impl(
        args={
            "operation": "retrieve",
            "key": "test_key",
            "namespace": "evidence",
        }
    )
    assert retrieve_result["success"] is True
    assert retrieve_result["found"] is True
    retrieved = json.loads(retrieve_result["value"])
    assert retrieved["data"] == "hello"

    # List keys
    list_result = await tool._run_async_impl(
        args={"operation": "list_keys", "namespace": "evidence"}
    )
    assert list_result["success"] is True
    assert "test_key" in list_result["keys"]


# ============================================================================
# Section 4: Risk scorer -- detailed validation
# ============================================================================


@pytest.mark.asyncio
async def test_risk_scorer_high_risk_scenario():
    """High whale density + high traffic + high speed -> HIGH risk."""
    from whale_tools.risk_scorer import compute_risk

    result = compute_risk(
        latitude=37.0,
        longitude=-122.0,
        month=4,  # April: seasonal multiplier = 1.0
        whale_density=0.9,
        vessel_traffic_density=0.9,
        vessel_speed_knots=20.0,
    )
    assert result["risk_level"] in ("HIGH", "CRITICAL")
    assert result["collision_risk_score"] >= 0.6


@pytest.mark.asyncio
async def test_risk_scorer_low_risk_scenario():
    """Low whale density + low traffic + slow speed -> LOW risk."""
    from whale_tools.risk_scorer import compute_risk

    result = compute_risk(
        latitude=37.0,
        longitude=-122.0,
        month=8,  # August: seasonal multiplier = 0.4
        whale_density=0.1,
        vessel_traffic_density=0.1,
        vessel_speed_knots=8.0,
    )
    assert result["risk_level"] == "LOW"
    assert result["collision_risk_score"] < 0.4


@pytest.mark.asyncio
async def test_risk_scorer_clamping():
    """Inputs outside valid ranges are clamped."""
    from whale_tools.risk_scorer import compute_risk

    result = compute_risk(
        latitude=37.0,
        longitude=-122.0,
        month=15,
        whale_density=2.0,
        vessel_traffic_density=-1.0,
        vessel_speed_knots=25.0,
    )
    assert result["inputs"]["month"] == 12
    assert result["inputs"]["whale_density"] == 1.0
    assert result["inputs"]["vessel_traffic_density"] == 0.0
    assert 0 <= result["collision_risk_score"] <= 1


# ============================================================================
# Section 5: Route calculator -- detailed validation
# ============================================================================


@pytest.mark.asyncio
async def test_route_calculator_with_risk_zones():
    """Route calculator deviates around risk zones."""
    from whale_tools.route_calculator import compute_route

    result = compute_route(
        origin_lat=34.0,
        origin_lng=-118.0,
        dest_lat=37.8,
        dest_lng=-122.4,
        risk_zones=[
            {"lat": 36.0, "lng": -120.0, "radius_km": 50, "risk_score": 0.9},
        ],
    )
    assert len(result["waypoints"]) >= 2
    assert result["total_distance_nm"] >= result["direct_distance_nm"]
    # GeoJSON structure
    geojson = result["geojson"]
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == 1
    assert geojson["features"][0]["geometry"]["type"] == "LineString"


@pytest.mark.asyncio
async def test_route_calculator_short_route():
    """Very short routes (< 1nm) produce origin + destination only."""
    from whale_tools.route_calculator import compute_route

    result = compute_route(
        origin_lat=37.0,
        origin_lng=-122.0,
        dest_lat=37.001,
        dest_lng=-122.001,
    )
    assert len(result["waypoints"]) == 2


@pytest.mark.asyncio
async def test_route_calculator_geojson_coordinates():
    """GeoJSON coordinates are [lng, lat] order per the spec."""
    from whale_tools.route_calculator import compute_route

    result = compute_route(
        origin_lat=34.0,
        origin_lng=-118.0,
        dest_lat=37.8,
        dest_lng=-122.4,
    )
    coords = result["geojson"]["features"][0]["geometry"]["coordinates"]
    # First coordinate should match origin [lng, lat]
    assert coords[0][0] == -118.0  # lng
    assert coords[0][1] == 34.0  # lat
    # Last coordinate should match destination
    assert coords[-1][0] == -122.4
    assert coords[-1][1] == 37.8


# ============================================================================
# Section 6: Map renderer -- all render types
# ============================================================================


@pytest.mark.asyncio
async def test_map_renderer_shipping_lanes():
    """MapRendererTool renders shipping_lanes as GeoJSON LineStrings."""
    from whale_tools.map_renderer import MapRendererTool

    tool = MapRendererTool()
    result = await tool._run_async_impl(
        args={
            "render_type": "shipping_lanes",
            "data": [
                {
                    "waypoints": [
                        {"lat": 33.7, "lng": -118.2},
                        {"lat": 34.0, "lng": -119.0},
                    ],
                    "density": 0.8,
                    "name": "LA-SB Lane",
                }
            ],
        }
    )
    assert result["type"] == "FeatureCollection"
    assert result["metadata"]["render_type"] == "shipping_lanes"
    assert result["features"][0]["geometry"]["type"] == "LineString"


@pytest.mark.asyncio
async def test_map_renderer_migration_corridors():
    """MapRendererTool renders migration_corridors as GeoJSON LineStrings."""
    from whale_tools.map_renderer import MapRendererTool

    tool = MapRendererTool()
    result = await tool._run_async_impl(
        args={
            "render_type": "migration_corridors",
            "data": [
                {
                    "waypoints": [
                        {"lat": 27.5, "lng": -114.5},
                        {"lat": 36.8, "lng": -121.9},
                    ],
                    "species": "gray_whale",
                    "name": "Pacific Gray Whale Corridor",
                }
            ],
        }
    )
    assert result["type"] == "FeatureCollection"
    assert result["metadata"]["render_type"] == "migration_corridors"
    assert result["features"][0]["properties"]["species"] == "gray_whale"


# ============================================================================
# Section 7: Fuel estimator -- detailed validation
# ============================================================================


@pytest.mark.asyncio
async def test_fuel_estimator_no_diversion():
    """When route equals original distance, extra cost is zero."""
    from whale_tools.fuel_estimator import compute_fuel_impact

    result = compute_fuel_impact(
        route_distance_nm=500.0,
        original_distance_nm=500.0,
        speed_knots=14.0,
    )
    assert result["fuel_impact_pct"] == 0.0
    assert result["extra_fuel_liters"] == 0.0
    assert result["time_delta_hours"] == 0.0


@pytest.mark.asyncio
async def test_fuel_estimator_with_diversion():
    """Extra distance leads to positive fuel impact."""
    from whale_tools.fuel_estimator import compute_fuel_impact

    result = compute_fuel_impact(
        route_distance_nm=550.0,
        original_distance_nm=500.0,
        speed_knots=14.0,
    )
    assert result["fuel_impact_pct"] == 10.0
    assert result["extra_fuel_liters"] > 0
    assert result["extra_distance_nm"] == 50.0
    assert result["time_delta_hours"] > 0


@pytest.mark.asyncio
async def test_fuel_estimator_speed_interpolation():
    """Fuel rate interpolates between defined speed breakpoints."""
    from whale_tools.fuel_estimator import _interpolate_fuel_rate

    # At defined breakpoints
    assert _interpolate_fuel_rate(10) == 8.0
    assert _interpolate_fuel_rate(14) == 13.5
    # Between breakpoints
    rate_13 = _interpolate_fuel_rate(13)
    assert 10.5 < rate_13 < 13.5
    # Below minimum and above maximum
    assert _interpolate_fuel_rate(5) == 8.0
    assert _interpolate_fuel_rate(30) == 32.0


# ============================================================================
# Section 8: Query decomposer -- classification accuracy
# ============================================================================


CLASSIFICATION_CASES = [
    ("Plan a safe shipping route from Seattle to LA", "RouteOptimizer"),
    ("What whale species are endangered in this area?", "SpeciesIdentifier"),
    ("What is the weather forecast for the next 3 days?", "WeatherAnalyst"),
    ("Show me vessel traffic density in the Santa Barbara Channel", "VesselTrafficMonitor"),
    ("What are the seasonal migration patterns and corridors in the Pacific?", "WhaleMigrationTracker"),
]


@pytest.mark.parametrize("question,expected_agent", CLASSIFICATION_CASES)
@pytest.mark.asyncio
async def test_query_decomposer_classification(question, expected_agent):
    """QueryDecomposerTool routes domain questions to the correct primary agent."""
    from whale_tools.query_decomposer import QueryDecomposerTool

    tool = QueryDecomposerTool()
    result = await tool._run_async_impl(args={"question": question})
    primary_agents = [
        sq["target_agent"] for sq in result["sub_questions"]
    ]
    assert expected_agent in primary_agents or expected_agent in result["all_agents"], (
        f"Expected {expected_agent} for '{question}', got primary={primary_agents}, all={result['all_agents']}"
    )


# ============================================================================
# Section 9: Cross-tool pipeline smoke test
# ============================================================================


@pytest.mark.asyncio
async def test_risk_then_route_then_fuel_pipeline():
    """Simulate a mini pipeline: risk score -> route -> fuel estimate."""
    from whale_tools.risk_scorer import compute_risk
    from whale_tools.route_calculator import compute_route
    from whale_tools.fuel_estimator import compute_fuel_impact

    # Step 1: Score risk at midpoint
    risk = compute_risk(
        latitude=36.0,
        longitude=-120.0,
        month=4,
        whale_density=0.7,
        vessel_traffic_density=0.5,
        vessel_speed_knots=14.0,
    )
    assert risk["risk_level"] in ("LOW", "MODERATE", "HIGH")

    # Step 2: Compute route, using risk result to build a risk zone
    risk_zone = {
        "lat": 36.0,
        "lng": -120.0,
        "radius_km": 50,
        "risk_score": risk["collision_risk_score"],
    }
    route = compute_route(
        origin_lat=34.0,
        origin_lng=-118.0,
        dest_lat=37.8,
        dest_lng=-122.4,
        risk_zones=[risk_zone],
    )
    assert route["total_distance_nm"] > 0

    # Step 3: Estimate fuel for the diversion
    fuel = compute_fuel_impact(
        route_distance_nm=route["total_distance_nm"],
        original_distance_nm=route["direct_distance_nm"],
        speed_knots=14.0,
    )
    assert "fuel_impact_pct" in fuel
    assert fuel["total_fuel_liters"] > 0

    # Step 4: Render the route as GeoJSON (via pure function)
    from whale_tools.map_renderer import _render_route

    geojson = _render_route([
        {"waypoints": route["waypoints"], "distance_nm": route["total_distance_nm"]}
    ])
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == 1
