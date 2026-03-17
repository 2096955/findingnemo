"""Tests for the memory_plane tool."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from whale_tools.memory_plane import MemoryPlaneTool, DictBackend, NAMESPACES


# ---------------------------------------------------------------------------
# DictBackend tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dict_backend_set_get():
    backend = DictBackend()
    await backend.set("test_key", "test_value")
    result = await backend.get("test_key")
    assert result == "test_value"


@pytest.mark.asyncio
async def test_dict_backend_get_missing():
    backend = DictBackend()
    result = await backend.get("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_dict_backend_delete():
    backend = DictBackend()
    await backend.set("key1", "val1")
    await backend.delete("key1")
    result = await backend.get("key1")
    assert result is None


@pytest.mark.asyncio
async def test_dict_backend_keys_pattern():
    backend = DictBackend()
    await backend.set("whale:sess1:evidence:item1", "v1")
    await backend.set("whale:sess1:evidence:item2", "v2")
    await backend.set("whale:sess1:citations:ref1", "v3")
    keys = await backend.keys("whale:sess1:evidence:*")
    assert len(keys) == 2
    assert "whale:sess1:evidence:item1" in keys


# ---------------------------------------------------------------------------
# MemoryPlaneTool tests
# ---------------------------------------------------------------------------


@pytest.fixture
def memory_tool():
    """Create a fresh MemoryPlaneTool with its own backend."""
    # Reset the class-level backend
    MemoryPlaneTool._backend = None
    return MemoryPlaneTool(tool_config={})


@pytest.mark.asyncio
async def test_store_and_retrieve(memory_tool):
    result = await memory_tool._run_async_impl(
        args={"operation": "store", "key": "test_key", "value": "test_value", "namespace": "evidence"},
    )
    assert result["success"] is True
    assert result["key"] == "test_key"

    result = await memory_tool._run_async_impl(
        args={"operation": "retrieve", "key": "test_key", "namespace": "evidence"},
    )
    assert result["success"] is True
    assert result["found"] is True
    assert result["value"] == "test_value"


@pytest.mark.asyncio
async def test_retrieve_missing_key(memory_tool):
    result = await memory_tool._run_async_impl(
        args={"operation": "retrieve", "key": "nonexistent", "namespace": "evidence"},
    )
    assert result["success"] is True
    assert result["found"] is False


@pytest.mark.asyncio
async def test_list_keys(memory_tool):
    await memory_tool._run_async_impl(
        args={"operation": "store", "key": "k1", "value": "v1", "namespace": "evidence"},
    )
    await memory_tool._run_async_impl(
        args={"operation": "store", "key": "k2", "value": "v2", "namespace": "evidence"},
    )

    result = await memory_tool._run_async_impl(
        args={"operation": "list_keys", "namespace": "evidence"},
    )
    assert result["success"] is True
    assert "k1" in result["keys"]
    assert "k2" in result["keys"]


@pytest.mark.asyncio
async def test_append(memory_tool):
    await memory_tool._run_async_impl(
        args={"operation": "append", "key": "items", "value": '"item1"', "namespace": "intermediate"},
    )
    await memory_tool._run_async_impl(
        args={"operation": "append", "key": "items", "value": '"item2"', "namespace": "intermediate"},
    )

    result = await memory_tool._run_async_impl(
        args={"operation": "retrieve", "key": "items", "namespace": "intermediate"},
    )
    assert result["found"] is True
    import json
    items = json.loads(result["value"])
    assert items == ["item1", "item2"]


@pytest.mark.asyncio
async def test_clear_session(memory_tool):
    await memory_tool._run_async_impl(
        args={"operation": "store", "key": "k1", "value": "v1", "namespace": "evidence"},
    )
    result = await memory_tool._run_async_impl(
        args={"operation": "clear_session"},
    )
    assert result["success"] is True
    assert result["cleared"] >= 1


@pytest.mark.asyncio
async def test_invalid_namespace(memory_tool):
    result = await memory_tool._run_async_impl(
        args={"operation": "store", "key": "k1", "value": "v1", "namespace": "bogus"},
    )
    assert result["success"] is False
    assert "Invalid namespace" in result["error"]


@pytest.mark.asyncio
async def test_unknown_operation(memory_tool):
    result = await memory_tool._run_async_impl(
        args={"operation": "delete_everything"},
    )
    assert result["success"] is False
    assert "Unknown operation" in result["error"]


@pytest.mark.asyncio
async def test_store_idempotent(memory_tool):
    await memory_tool._run_async_impl(
        args={"operation": "store", "key": "idem", "value": "same", "namespace": "evidence"},
    )
    result = await memory_tool._run_async_impl(
        args={"operation": "store", "key": "idem", "value": "same", "namespace": "evidence"},
    )
    assert result["success"] is True
    assert result.get("idempotent") is True


@pytest.mark.asyncio
async def test_tool_properties():
    tool = MemoryPlaneTool(tool_config={})
    assert tool.tool_name == "memory_plane"
    assert "memory" in tool.tool_description.lower()
    schema = tool.parameters_schema
    assert "operation" in schema.properties


def test_namespaces():
    assert "evidence" in NAMESPACES
    assert "intermediate" in NAMESPACES
    assert "citations" in NAMESPACES
    assert "verification" in NAMESPACES
    assert "learning" in NAMESPACES
