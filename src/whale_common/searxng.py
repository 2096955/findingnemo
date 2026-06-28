"""Shared SearXNG search client.

Calls the SearXNG HTTP JSON API (same backend used by mcp-searxng).
Supports semicolon-separated replica URLs for failover.
"""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urlencode

import httpx

log = logging.getLogger(__name__)

SEARXNG_HTML_FALLBACK = os.environ.get("SEARXNG_HTML_FALLBACK", "false").lower() in (
    "1",
    "true",
    "yes",
)


def get_searxng_url() -> str:
    return os.environ.get("SEARXNG_URL", "")


def parse_searxng_urls(searxng_url: str = "") -> list[str]:
    """Return normalized SearXNG base URLs from env or argument."""
    raw = (searxng_url or get_searxng_url()).strip()
    if not raw:
        return []
    return [u.rstrip("/") for u in raw.split(";") if u.strip()]


def _normalize_results(
    results: list[dict[str, Any]], max_results: int
) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in results[:max_results]:
        title = str(item.get("title", ""))
        url = str(item.get("url", ""))
        snippet = str(item.get("content", item.get("snippet", "")))[:300]
        if title or url:
            normalized.append({"title": title, "url": url, "snippet": snippet})
    return normalized


async def _search_instance_json(
    base_url: str,
    query: str,
    max_results: int,
    *,
    language: str = "all",
    time_range: str | None = None,
    categories: str | None = None,
    timeout: float = 15.0,
) -> list[dict[str, str]]:
    params: dict[str, str] = {
        "q": query,
        "format": "json",
        "language": language,
    }
    if time_range:
        params["time_range"] = time_range
    if categories:
        params["categories"] = categories

    search_url = f"{base_url}/search?{urlencode(params)}"

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(
            search_url,
            headers={"Accept": "application/json"},
        )

        if resp.status_code in (403, 404) and SEARXNG_HTML_FALLBACK:
            log.info(
                "[searxng] JSON search blocked on %s — retrying without format=json",
                base_url,
            )
            fallback_params = {k: v for k, v in params.items() if k != "format"}
            resp = await client.get(
                f"{base_url}/search?{urlencode(fallback_params)}",
                headers={"Accept": "text/html"},
            )
            if resp.status_code != 200:
                resp.raise_for_status()
            return _parse_html_results(resp.text, max_results)

        resp.raise_for_status()
        data = resp.json()
        return _normalize_results(data.get("results", []), max_results)


def _parse_html_results(html: str, max_results: int) -> list[dict[str, str]]:
    """Best-effort HTML result extraction when JSON format is unavailable."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        log.warning("[searxng] beautifulsoup4 not installed — HTML fallback disabled")
        return []

    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, str]] = []
    for article in soup.select("article.result"):
        title_el = article.select_one("h3 a") or article.select_one("a")
        content_el = article.select_one("p.content") or article.select_one("p")
        if not title_el:
            continue
        results.append(
            {
                "title": title_el.get_text(strip=True),
                "url": title_el.get("href", ""),
                "snippet": content_el.get_text(strip=True)[:300] if content_el else "",
            }
        )
        if len(results) >= max_results:
            break
    return results


async def search_searxng(
    query: str,
    max_results: int = 5,
    *,
    searxng_url: str = "",
    language: str = "all",
    time_range: str | None = None,
    categories: str | None = None,
) -> list[dict[str, str]]:
    """Search via SearXNG. Returns list of {title, url, snippet}."""
    max_results = max(1, min(20, max_results))
    instances = parse_searxng_urls(searxng_url)
    if not instances:
        return []

    for base_url in instances:
        try:
            results = await _search_instance_json(
                base_url,
                query,
                max_results,
                language=language,
                time_range=time_range,
                categories=categories,
            )
            if results:
                return results
        except Exception as exc:
            log.warning("[searxng] Search failed on %s: %s", base_url, exc)

    return []
