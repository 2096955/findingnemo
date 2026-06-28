"""Tests for the SearXNG MCP server and shared client."""

import os
import sys

import httpx
import pytest
import respx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from mcp_servers.searxng import server as searxng_module
from whale_common import searxng as searxng_client

searxng_web_search = searxng_module.searxng_web_search.fn
searxng_instance_info = searxng_module.searxng_instance_info.fn

SEARXNG_RESPONSE = {
    "results": [
        {
            "title": "Red Sea shipping attacks continue",
            "url": "https://example.com/red-sea",
            "content": "Houthi forces target commercial vessels in the Red Sea.",
        },
        {
            "title": "Maritime security advisory",
            "url": "https://example.com/advisory",
            "content": "Navies increase patrols in Gulf of Aden.",
        },
    ]
}


@pytest.mark.asyncio
async def test_search_searxng_success(monkeypatch):
    monkeypatch.setenv("SEARXNG_URL", "http://searxng.local")

    with respx.mock:
        respx.get(url__regex=r"http://searxng\.local/search.*").mock(
            return_value=httpx.Response(200, json=SEARXNG_RESPONSE)
        )

        results = await searxng_client.search_searxng(
            "Red Sea shipping disruption", max_results=5
        )

    assert len(results) == 2
    assert results[0]["title"] == "Red Sea shipping attacks continue"
    assert results[0]["url"] == "https://example.com/red-sea"
    assert "Houthi" in results[0]["snippet"]


@pytest.mark.asyncio
async def test_search_searxng_failover(monkeypatch):
    monkeypatch.setenv("SEARXNG_URL", "http://down.local;http://up.local")

    with respx.mock:
        respx.get(url__regex=r"http://down\.local/search.*").mock(
            return_value=httpx.Response(503)
        )
        respx.get(url__regex=r"http://up\.local/search.*").mock(
            return_value=httpx.Response(200, json=SEARXNG_RESPONSE)
        )

        results = await searxng_client.search_searxng("maritime piracy")

    assert len(results) == 2


@pytest.mark.asyncio
async def test_searxng_web_search_tool(monkeypatch):
    monkeypatch.setenv("SEARXNG_URL", "http://searxng.local")

    with respx.mock:
        respx.get(url__regex=r"http://searxng\.local/search.*").mock(
            return_value=httpx.Response(200, json=SEARXNG_RESPONSE)
        )

        result = await searxng_web_search(
            query="Strait of Hormuz shipping",
            num_results=5,
        )

    assert result["success"] is True
    assert result["result_count"] == 2
    assert result["results"][0]["url"].startswith("https://")


@pytest.mark.asyncio
async def test_searxng_web_search_unconfigured(monkeypatch):
    monkeypatch.delenv("SEARXNG_URL", raising=False)

    result = await searxng_web_search(query="test query")

    assert "error" in result
    assert result["results"] == []


@pytest.mark.asyncio
async def test_searxng_instance_info(monkeypatch):
    monkeypatch.setenv("SEARXNG_URL", "http://one.local;http://two.local")

    info = await searxng_instance_info()

    assert info["configured"] is True
    assert info["instance_count"] == 2
    assert info["instances"] == ["http://one.local", "http://two.local"]
