"""SearXNG MCP server — private web search via self-hosted SearXNG.

Compatible with the mcp-searxng tool surface (web search + instance info).
Agents connect via SSE on port 9007.
"""

import logging
import os
import sys

from fastmcp import FastMCP

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from mcp_servers._security import sanitize_query
from whale_common.searxng import parse_searxng_urls, search_searxng

log = logging.getLogger(__name__)

mcp = FastMCP("searxng")


@mcp.tool()
async def searxng_web_search(
    query: str,
    pageno: int = 1,
    time_range: str = None,
    language: str = "all",
    num_results: int = 10,
    categories: str = None,
) -> dict:
    """Execute a web search via SearXNG.

    Args:
        query: Search query string.
        pageno: Page number (1-based). Only the first page is fetched for now.
        time_range: Optional filter — day, week, month, or year.
        language: Language code (e.g. en, fr) or all.
        num_results: Maximum results to return (1-20).
        categories: Comma-separated SearXNG categories (e.g. news, it).

    Returns search results with title, url, and snippet for each hit.
    """
    safe_query = sanitize_query(query, max_len=500)
    if not safe_query:
        return {"error": "Query is empty or invalid", "results": []}

    if not parse_searxng_urls():
        return {
            "error": "SEARXNG_URL is not configured",
            "results": [],
        }

    if pageno > 1:
        log.info("[searxng] pageno=%d requested — returning page 1 only", pageno)

    num_results = max(1, min(20, num_results))
    valid_ranges = {"day", "week", "month", "year", None}
    if time_range not in valid_ranges:
        time_range = None

    results = await search_searxng(
        safe_query,
        max_results=num_results,
        language=language or "all",
        time_range=time_range,
        categories=categories,
    )

    return {
        "success": True,
        "query": safe_query,
        "result_count": len(results),
        "results": results,
    }


@mcp.tool()
async def searxng_instance_info() -> dict:
    """Report configured SearXNG instance URLs and availability."""
    instances = parse_searxng_urls()
    if not instances:
        return {
            "configured": False,
            "instances": [],
            "message": "Set SEARXNG_URL to enable web search",
        }

    return {
        "configured": True,
        "instance_count": len(instances),
        "instances": instances,
        "html_fallback": os.environ.get("SEARXNG_HTML_FALLBACK", "false"),
    }


if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=9007)
