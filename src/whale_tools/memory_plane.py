"""Central Memory Plane — shared state for whale agent orchestrator and specialists.

Provides session-scoped key-value storage with namespace separation.
Uses a simple dict-backed implementation for the PoC (no Redis required).
Cold-store operations use SQLite at data/whale_cold.db.

Key operations: store, retrieve, list_keys, append, clear_session,
seed_session, flush_cold, query_cold.
"""

import asyncio
import json
import logging
import os
from typing import Optional

from google.adk.tools import ToolContext
from google.genai import types as adk_types

from solace_agent_mesh.agent.tools.dynamic_tool import DynamicTool

log = logging.getLogger(__name__)

NAMESPACES = ("evidence", "intermediate", "citations", "verification", "learning")

_DEFAULT_COLD_DB = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "whale_cold.db"
)


class DictBackend:
    """In-memory fallback when Redis is not available."""

    def __init__(self):
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = value

    async def delete(self, *keys: str) -> None:
        for k in keys:
            self._store.pop(k, None)

    async def keys(self, pattern: str) -> list[str]:
        import fnmatch
        return [k for k in self._store if fnmatch.fnmatch(k, pattern)]

    async def exists(self, key: str) -> bool:
        return key in self._store


class MemoryPlaneTool(DynamicTool):
    """Session-scoped key-value store with namespace separation."""

    _backend = None

    def __init__(self, tool_config: Optional[dict] = None, **kwargs):
        super().__init__(tool_config=tool_config, **kwargs)
        cfg = tool_config or {}
        self._read_only = bool(cfg.get("read_only", False))
        self._ttl_seconds = int(cfg.get("ttl_seconds", 3600))
        self._cold_db_path = cfg.get("cold_db_path", _DEFAULT_COLD_DB)

    @property
    def tool_name(self) -> str:
        return "memory_plane"

    @property
    def tool_description(self) -> str:
        return (
            "Central memory plane for storing and retrieving shared state across "
            "whale agents. Supports operations: store, retrieve, list_keys, "
            "clear_session, append, flush_cold, seed_session, query_cold. "
            "Keys are scoped by session ID and namespace (evidence, intermediate, "
            "citations, verification, learning)."
        )

    @property
    def parameters_schema(self) -> adk_types.Schema:
        return adk_types.Schema(
            type=adk_types.Type.OBJECT,
            properties={
                "operation": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description=(
                        "Operation: store, retrieve, list_keys, clear_session, append, "
                        "flush_cold, seed_session, query_cold"
                    ),
                ),
                "key": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="Key name (required for store, retrieve, append)",
                    nullable=True,
                ),
                "value": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="Value to store (JSON string). Required for store/append.",
                    nullable=True,
                ),
                "namespace": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="Namespace: evidence, intermediate, citations, verification, learning. Default: intermediate",
                    nullable=True,
                ),
                "query": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="User query text. Required for seed_session and query_cold.",
                    nullable=True,
                ),
            },
            required=["operation"],
        )

    def _ensure_backend(self):
        if MemoryPlaneTool._backend is None:
            MemoryPlaneTool._backend = DictBackend()

    def _make_key(self, session_id: str, namespace: str, key: str) -> str:
        return f"whale:{session_id}:{namespace}:{key}"

    def _session_pattern(self, session_id: str, namespace: str | None = None) -> str:
        if namespace:
            return f"whale:{session_id}:{namespace}:*"
        return f"whale:{session_id}:*"

    async def _run_async_impl(
        self,
        args: dict,
        tool_context: Optional[ToolContext] = None,
        credential: Optional[str] = None,
    ) -> dict:
        self._ensure_backend()

        operation = args.get("operation", "").lower()
        key = args.get("key", "")
        value = args.get("value", "")
        namespace = args.get("namespace", "intermediate")

        # Resolve session ID
        session_id = "default"
        if tool_context:
            session_obj = getattr(tool_context, "session", None)
            session_id = getattr(session_obj, "id", "default") if session_obj else "default"

        cold_ops = ("flush_cold", "seed_session", "query_cold")
        if operation not in cold_ops and namespace not in NAMESPACES:
            return {
                "success": False,
                "error": f"Invalid namespace '{namespace}'. Must be one of: {NAMESPACES}",
            }

        write_ops = ("store", "append", "clear_session", "flush_cold")
        if self._read_only and operation in write_ops:
            return {
                "success": False,
                "error": f"Memory plane is read-only. Cannot perform '{operation}'.",
            }

        if operation == "store":
            if not key:
                return {"success": False, "error": "Key is required for store"}
            full_key = self._make_key(session_id, namespace, key)
            existing = await self._backend.get(full_key)
            if existing == value:
                return {"success": True, "key": key, "namespace": namespace, "idempotent": True}
            await self._backend.set(full_key, value, ex=self._ttl_seconds)
            return {"success": True, "key": key, "namespace": namespace}

        elif operation == "retrieve":
            if not key:
                return {"success": False, "error": "Key is required for retrieve"}
            full_key = self._make_key(session_id, namespace, key)
            stored = await self._backend.get(full_key)
            if stored is None:
                return {"success": True, "found": False, "value": None}
            return {"success": True, "found": True, "value": stored}

        elif operation == "list_keys":
            pattern = self._session_pattern(session_id, namespace)
            raw_keys = await self._backend.keys(pattern)
            prefix = f"whale:{session_id}:{namespace}:"
            keys = [k[len(prefix):] for k in raw_keys if k.startswith(prefix)]
            return {"success": True, "namespace": namespace, "keys": keys}

        elif operation == "clear_session":
            pattern = self._session_pattern(session_id)
            all_keys = await self._backend.keys(pattern)
            if all_keys:
                await self._backend.delete(*all_keys)
            return {"success": True, "cleared": len(all_keys)}

        elif operation == "append":
            if not key:
                return {"success": False, "error": "Key is required for append"}
            full_key = self._make_key(session_id, namespace, key)
            existing = await self._backend.get(full_key)
            if existing:
                try:
                    existing_list = json.loads(existing)
                    if not isinstance(existing_list, list):
                        existing_list = [existing_list]
                except (json.JSONDecodeError, TypeError):
                    existing_list = [existing]
            else:
                existing_list = []

            try:
                new_item = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                new_item = value

            existing_list.append(new_item)
            await self._backend.set(full_key, json.dumps(existing_list), ex=self._ttl_seconds)
            return {
                "success": True,
                "key": key,
                "namespace": namespace,
                "length": len(existing_list),
            }

        elif operation == "flush_cold":
            return await self._op_flush_cold(args, session_id)

        elif operation == "seed_session":
            return await self._op_seed_session(args, session_id)

        elif operation == "query_cold":
            return await self._op_query_cold(args)

        else:
            return {
                "success": False,
                "error": (
                    f"Unknown operation '{operation}'. Use: store, retrieve, list_keys, "
                    "clear_session, append, flush_cold, seed_session, query_cold"
                ),
            }

    # ------------------------------------------------------------------
    # Cold store operations (simplified for PoC)
    # ------------------------------------------------------------------

    def _get_cold_connection(self):
        from whale_tools.cold_store import get_connection
        return get_connection(self._cold_db_path)

    async def _op_flush_cold(self, args: dict, session_id: str) -> dict:
        """Persist session data to cold store."""
        try:
            query_text = args.get("query", "")
            query_domain = args.get("query_domain", "general")
            specialists_used = args.get("specialists_used", "")

            def _sync_flush():
                conn = self._get_cold_connection()
                try:
                    conn.execute(
                        "INSERT OR REPLACE INTO session_outcomes (session_id, query_text, query_domain, specialists_used) VALUES (?, ?, ?, ?)",
                        (session_id, query_text, query_domain, specialists_used),
                    )
                    conn.commit()
                finally:
                    conn.close()

            await asyncio.to_thread(_sync_flush)
            return {"success": True, "flushed": True, "session_id": session_id}
        except Exception as exc:
            log.exception("Failed to flush cold store")
            return {"success": False, "error": f"flush_cold failed: {exc}"}

    async def _op_seed_session(self, args: dict, session_id: str) -> dict:
        """Load learned strategies from cold store into session."""
        try:
            query_text = args.get("query", "")

            def _sync_seed():
                conn = self._get_cold_connection()
                try:
                    cursor = conn.execute(
                        "SELECT query_domain FROM session_outcomes ORDER BY created_at DESC LIMIT 5"
                    )
                    rows = cursor.fetchall()
                    if rows:
                        return {
                            "seeded": True,
                            "past_domains": [r[0] for r in rows],
                        }
                    return {"seeded": False, "reason": "No historical data"}
                finally:
                    conn.close()

            result = await asyncio.to_thread(_sync_seed)
            return {"success": True, **result}
        except Exception as exc:
            log.exception("Failed to seed session")
            return {"success": False, "error": f"seed_session failed: {exc}"}

    async def _op_query_cold(self, args: dict) -> dict:
        """Look up historical intelligence from the cold store."""
        try:
            def _sync_query():
                conn = self._get_cold_connection()
                try:
                    cursor = conn.execute(
                        "SELECT session_id, query_text, query_domain, created_at FROM session_outcomes ORDER BY created_at DESC LIMIT 10"
                    )
                    rows = cursor.fetchall()
                    return {
                        "success": True,
                        "results": [
                            {
                                "session_id": r[0],
                                "query_text": r[1],
                                "query_domain": r[2],
                                "created_at": r[3],
                            }
                            for r in rows
                        ],
                    }
                finally:
                    conn.close()

            return await asyncio.to_thread(_sync_query)
        except Exception as exc:
            log.exception("Failed to query cold store")
            return {"success": False, "error": f"query_cold failed: {exc}"}
