"""Tests for the cold_store tool."""

import sys
import os
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from whale_tools.cold_store import (
    get_connection,
    store_session,
    store_route_pattern,
    query_patterns,
    get_strategies,
)


@pytest.fixture
def tmp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    try:
        os.unlink(db_path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Direct function tests
# ---------------------------------------------------------------------------


def test_get_connection(tmp_db):
    conn = get_connection(tmp_db)
    assert conn is not None
    # Verify tables exist
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    assert "session_outcomes" in tables
    assert "route_patterns" in tables
    assert "risk_calibrations" in tables
    assert "seasonal_strategies" in tables
    conn.close()


def test_store_session(tmp_db):
    conn = get_connection(tmp_db)
    ok = store_session(
        conn,
        session_id="test-001",
        query_text="safest route from LA to SF",
        query_domain="route_optimization",
        context={"origin": "LA", "dest": "SF"},
        actions={"computed_route": True},
        outcomes={"risk_level": "MODERATE"},
        specialists_used=["RouteOptimizer", "RiskAssessor"],
        risk_level="MODERATE",
    )
    assert ok is True

    cursor = conn.execute(
        "SELECT * FROM session_outcomes WHERE session_id = 'test-001'"
    )
    row = cursor.fetchone()
    assert row is not None
    conn.close()


def test_store_route_pattern(tmp_db):
    conn = get_connection(tmp_db)
    ok = store_route_pattern(
        conn,
        origin_region="LA",
        dest_region="SF",
        risk_zones_avoided=2,
        distance_penalty_pct=5.2,
        fuel_penalty_pct=6.1,
        recommended_speed=12.0,
        season="spring",
    )
    assert ok is True
    conn.close()


def test_query_patterns(tmp_db):
    conn = get_connection(tmp_db)
    store_route_pattern(conn, "LA", "SF", season="spring")
    store_route_pattern(conn, "LA", "Seattle", season="winter")

    patterns = query_patterns(conn, origin_region="LA")
    assert len(patterns) == 2

    patterns = query_patterns(conn, season="spring")
    assert len(patterns) == 1
    conn.close()


def test_get_strategies_empty(tmp_db):
    conn = get_connection(tmp_db)
    strategies = get_strategies(conn)
    assert strategies == []
    conn.close()

