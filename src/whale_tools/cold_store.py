"""Cold Store — SQLite cross-session learning.

Stores decisions in Context/Actions/Outcomes format per Project Resilience
data guidelines. Tables: session_outcomes, route_patterns, risk_calibrations,
seasonal_strategies.

Operations: store_session, query_patterns, get_strategies.
Uses data/whale_cold.db.
"""

import json
import logging
import os
import sqlite3
from typing import Optional

from google.adk.tools import ToolContext
from google.genai import types as adk_types

from solace_agent_mesh.agent.tools.dynamic_tool import DynamicTool

log = logging.getLogger(__name__)

_DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "whale_cold.db"
)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS session_outcomes (
    session_id TEXT PRIMARY KEY,
    query_text TEXT,
    query_domain TEXT,
    context TEXT,
    actions TEXT,
    outcomes TEXT,
    specialists_used TEXT,
    risk_level TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS route_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    origin_region TEXT,
    dest_region TEXT,
    risk_zones_avoided INTEGER DEFAULT 0,
    distance_penalty_pct REAL DEFAULT 0.0,
    fuel_penalty_pct REAL DEFAULT 0.0,
    recommended_speed REAL,
    season TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS risk_calibrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    region TEXT,
    month INTEGER,
    predicted_risk REAL,
    actual_outcome TEXT,
    calibration_delta REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS seasonal_strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season TEXT,
    region TEXT,
    strategy_type TEXT,
    strategy_data TEXT,
    effectiveness_score REAL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Get a connection to the cold store SQLite database."""
    path = db_path or _DEFAULT_DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    return conn


def store_session(
    conn: sqlite3.Connection,
    session_id: str,
    query_text: str,
    query_domain: str,
    context: dict | None = None,
    actions: dict | None = None,
    outcomes: dict | None = None,
    specialists_used: list[str] | None = None,
    risk_level: str | None = None,
) -> bool:
    """Store a session outcome in the cold store."""
    try:
        conn.execute(
            """INSERT OR REPLACE INTO session_outcomes
               (session_id, query_text, query_domain, context, actions, outcomes, specialists_used, risk_level)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                query_text,
                query_domain,
                json.dumps(context) if context else None,
                json.dumps(actions) if actions else None,
                json.dumps(outcomes) if outcomes else None,
                json.dumps(specialists_used) if specialists_used else None,
                risk_level,
            ),
        )
        conn.commit()
        return True
    except Exception as exc:
        log.exception("Failed to store session outcome: %s", exc)
        return False


def store_route_pattern(
    conn: sqlite3.Connection,
    origin_region: str,
    dest_region: str,
    risk_zones_avoided: int = 0,
    distance_penalty_pct: float = 0.0,
    fuel_penalty_pct: float = 0.0,
    recommended_speed: float | None = None,
    season: str | None = None,
) -> bool:
    """Store a route pattern in the cold store."""
    try:
        conn.execute(
            """INSERT INTO route_patterns
               (origin_region, dest_region, risk_zones_avoided, distance_penalty_pct,
                fuel_penalty_pct, recommended_speed, season)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (origin_region, dest_region, risk_zones_avoided,
             distance_penalty_pct, fuel_penalty_pct, recommended_speed, season),
        )
        conn.commit()
        return True
    except Exception as exc:
        log.exception("Failed to store route pattern: %s", exc)
        return False


def query_patterns(
    conn: sqlite3.Connection,
    origin_region: str | None = None,
    dest_region: str | None = None,
    season: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Query route patterns from the cold store."""
    query = "SELECT * FROM route_patterns WHERE 1=1"
    params = []
    if origin_region:
        query += " AND origin_region = ?"
        params.append(origin_region)
    if dest_region:
        query += " AND dest_region = ?"
        params.append(dest_region)
    if season:
        query += " AND season = ?"
        params.append(season)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    cursor = conn.execute(query, params)
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_strategies(
    conn: sqlite3.Connection,
    region: str | None = None,
    season: str | None = None,
    strategy_type: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Get seasonal strategies from the cold store."""
    query = "SELECT * FROM seasonal_strategies WHERE 1=1"
    params = []
    if region:
        query += " AND region = ?"
        params.append(region)
    if season:
        query += " AND season = ?"
        params.append(season)
    if strategy_type:
        query += " AND strategy_type = ?"
        params.append(strategy_type)
    query += " ORDER BY effectiveness_score DESC LIMIT ?"
    params.append(limit)

    cursor = conn.execute(query, params)
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    results = []
    for row in rows:
        d = dict(zip(columns, row))
        # Parse strategy_data JSON
        if d.get("strategy_data"):
            try:
                d["strategy_data"] = json.loads(d["strategy_data"])
            except (json.JSONDecodeError, TypeError):
                pass
        results.append(d)
    return results


class ColdStoreTool(DynamicTool):
    """SQLite cross-session learning for whale agent."""

    def __init__(self, tool_config: Optional[dict] = None, **kwargs):
        super().__init__(tool_config=tool_config, **kwargs)
        cfg = tool_config or {}
        self._db_path = cfg.get("db_path", _DEFAULT_DB_PATH)

    @property
    def tool_name(self) -> str:
        return "cold_store"

    @property
    def tool_description(self) -> str:
        return (
            "SQLite cross-session learning store. Stores decisions in "
            "Context/Actions/Outcomes format. Operations: store_session, "
            "query_patterns, get_strategies."
        )

    @property
    def parameters_schema(self) -> adk_types.Schema:
        return adk_types.Schema(
            type=adk_types.Type.OBJECT,
            properties={
                "operation": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="Operation: store_session, query_patterns, get_strategies",
                ),
                "session_id": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="Session ID (for store_session)",
                    nullable=True,
                ),
                "query_text": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="Query text (for store_session)",
                    nullable=True,
                ),
                "query_domain": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="Query domain (for store_session)",
                    nullable=True,
                ),
                "context": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="JSON context data (for store_session)",
                    nullable=True,
                ),
                "actions": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="JSON actions data (for store_session)",
                    nullable=True,
                ),
                "outcomes": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="JSON outcomes data (for store_session)",
                    nullable=True,
                ),
                "region": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="Region filter (for query_patterns, get_strategies)",
                    nullable=True,
                ),
                "season": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="Season filter (for query_patterns, get_strategies)",
                    nullable=True,
                ),
                "strategy_type": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="Strategy type filter (for get_strategies)",
                    nullable=True,
                ),
            },
            required=["operation"],
        )

    async def _run_async_impl(
        self,
        args: dict,
        tool_context: Optional[ToolContext] = None,
        credential: Optional[str] = None,
    ) -> dict:
        import asyncio

        operation = args.get("operation", "").lower()

        if operation == "store_session":
            def _sync_store():
                conn = get_connection(self._db_path)
                try:
                    ctx = None
                    acts = None
                    outs = None
                    if args.get("context"):
                        try:
                            ctx = json.loads(args["context"])
                        except (json.JSONDecodeError, TypeError):
                            ctx = {"raw": args["context"]}
                    if args.get("actions"):
                        try:
                            acts = json.loads(args["actions"])
                        except (json.JSONDecodeError, TypeError):
                            acts = {"raw": args["actions"]}
                    if args.get("outcomes"):
                        try:
                            outs = json.loads(args["outcomes"])
                        except (json.JSONDecodeError, TypeError):
                            outs = {"raw": args["outcomes"]}

                    ok = store_session(
                        conn,
                        session_id=args.get("session_id", "unknown"),
                        query_text=args.get("query_text", ""),
                        query_domain=args.get("query_domain", "general"),
                        context=ctx,
                        actions=acts,
                        outcomes=outs,
                    )
                    return {"success": ok}
                finally:
                    conn.close()

            return await asyncio.to_thread(_sync_store)

        elif operation == "query_patterns":
            def _sync_query():
                conn = get_connection(self._db_path)
                try:
                    patterns = query_patterns(
                        conn,
                        origin_region=args.get("region"),
                        season=args.get("season"),
                    )
                    return {"success": True, "patterns": patterns, "count": len(patterns)}
                finally:
                    conn.close()

            return await asyncio.to_thread(_sync_query)

        elif operation == "get_strategies":
            def _sync_strategies():
                conn = get_connection(self._db_path)
                try:
                    strategies = get_strategies(
                        conn,
                        region=args.get("region"),
                        season=args.get("season"),
                        strategy_type=args.get("strategy_type"),
                    )
                    return {"success": True, "strategies": strategies, "count": len(strategies)}
                finally:
                    conn.close()

            return await asyncio.to_thread(_sync_strategies)

        else:
            return {
                "success": False,
                "error": f"Unknown operation '{operation}'. Use: store_session, query_patterns, get_strategies",
            }
