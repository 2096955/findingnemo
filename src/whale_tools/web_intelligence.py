"""Web Intelligence — real-time situational awareness for shipping routes.

Searches the web for current events that could affect route safety: piracy,
armed conflicts, weather disasters, port closures, sanctions, and
environmental hazards.  Uses DuckDuckGo (no API key) as the primary search
engine, with an optional Brave Search fallback.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx
from google.adk.tools import ToolContext
from google.genai import types as adk_types

from solace_agent_mesh.agent.tools.dynamic_tool import DynamicTool

log = logging.getLogger(__name__)

BRAVE_SEARCH_API_KEY = os.environ.get("BRAVE_SEARCH_API_KEY", "")

THREAT_CATEGORIES = [
    "piracy",
    "armed_conflict",
    "weather_disaster",
    "port_closure",
    "sanctions",
    "environmental_hazard",
]

_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "piracy": [
        "piracy", "pirates", "hijack", "armed robbery at sea",
        "maritime security incident", "boarding", "pirate attack",
    ],
    "armed_conflict": [
        "military", "war", "missile", "attack", "houthi", "conflict zone",
        "naval strike", "drone strike", "warship", "blockade", "airstrike",
    ],
    "weather_disaster": [
        "cyclone", "typhoon", "hurricane", "tsunami", "storm surge",
        "tropical storm", "severe weather", "flooding", "monsoon",
    ],
    "port_closure": [
        "port closed", "port closure", "terminal shutdown", "port blockade",
        "port congestion", "dock strike", "labour strike", "harbor closed",
    ],
    "sanctions": [
        "sanctions", "embargo", "restricted vessels", "banned",
        "trade restriction", "export ban", "import ban",
    ],
    "environmental_hazard": [
        "oil spill", "contamination", "marine pollution", "algal bloom",
        "chemical spill", "toxic", "ecological disaster",
    ],
}


# ---------------------------------------------------------------------------
# Query generation
# ---------------------------------------------------------------------------

def _build_queries(
    route_description: str,
    regions: list[str] | None = None,
    categories: list[str] | None = None,
) -> list[str]:
    """Generate 2-4 targeted search queries from a route description."""
    now = datetime.now(timezone.utc)
    month_name = now.strftime("%B")
    year = now.year

    cats = categories or THREAT_CATEGORIES
    region_list = regions or []

    # Extract rough region hints from the route description if not provided
    if not region_list:
        # Simple extraction: split by common prepositions
        for word in [
            "Hormuz", "Suez", "Malacca", "Bab el-Mandeb", "Panama",
            "Cape Horn", "Good Hope", "Gulf of Aden", "Red Sea",
            "Arabian Sea", "Indian Ocean", "South China Sea",
            "Mediterranean", "Caribbean", "Pacific", "Atlantic",
        ]:
            if word.lower() in route_description.lower():
                region_list.append(word)

    queries = []

    # General route disruption query
    queries.append(
        f"{route_description} shipping route disruption {month_name} {year}"
    )

    # Category-specific queries per region
    cat_labels = {
        "piracy": "piracy alert",
        "armed_conflict": "military conflict shipping",
        "weather_disaster": "severe weather maritime",
        "port_closure": "port closure",
        "sanctions": "shipping sanctions",
        "environmental_hazard": "marine pollution",
    }

    for region in region_list[:3]:  # Cap at 3 regions
        for cat in cats[:2]:  # Cap at 2 categories per region
            label = cat_labels.get(cat, cat)
            queries.append(f"{region} {label} {month_name} {year}")

    # Always include a general maritime safety query
    if region_list:
        queries.append(
            f"maritime safety advisory {' '.join(region_list[:2])} {year}"
        )

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        key = q.lower()
        if key not in seen:
            seen.add(key)
            unique.append(q)

    return unique[:6]  # Hard cap at 6 queries


# ---------------------------------------------------------------------------
# Search engines (priority: Firecrawl → Brave → DuckDuckGo)
# ---------------------------------------------------------------------------

async def _search_firecrawl(query: str, max_results: int = 5) -> list[dict]:
    """Search via Firecrawl (corporate-proxy-friendly).  Returns list of
    {title, url, snippet}.  Requires FIRECRAWL_API_KEY env var."""
    firecrawl_key = os.environ.get("FIRECRAWL_API_KEY", "")
    if not firecrawl_key:
        return []
    try:
        from firecrawl import AsyncFirecrawlApp  # type: ignore[import-untyped]
    except ImportError:
        log.warning("[web_intelligence] firecrawl-py not installed")
        return []

    try:
        client = AsyncFirecrawlApp(api_key=firecrawl_key)
        raw = await client.search(query, params={"limit": max_results})
        results = raw if isinstance(raw, list) else raw.get("data", []) if isinstance(raw, dict) else []
        return [
            {
                "title": r.get("title", r.get("metadata", {}).get("title", "")),
                "url": r.get("url", r.get("sourceURL", "")),
                "snippet": r.get("description", r.get("markdown", ""))[:300],
            }
            for r in results
        ]
    except Exception as exc:
        log.warning("[web_intelligence] Firecrawl search failed: %s", exc)
        return []


async def _search_brave(
    query: str, api_key: str, max_results: int = 5
) -> list[dict]:
    """Call Brave Web Search API.  Returns list of {title, url, snippet}."""
    if not api_key:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": max_results},
                headers={
                    "X-Subscription-Token": api_key,
                    "Accept": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("description", ""),
                }
                for r in data.get("web", {}).get("results", [])[:max_results]
            ]
    except Exception as exc:
        log.warning("[web_intelligence] Brave fallback failed: %s", exc)
        return []


def _search_ddg(query: str, max_results: int = 5) -> list[dict]:
    """Search DuckDuckGo (last resort — may be blocked by corporate proxies)."""
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        log.warning("[web_intelligence] duckduckgo-search not installed")
        return []

    for attempt in range(3):
        try:
            with DDGS() as ddgs:
                raw = list(ddgs.text(query, max_results=max_results))
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", r.get("link", "")),
                    "snippet": r.get("body", r.get("snippet", "")),
                }
                for r in raw
            ]
        except Exception as exc:
            log.warning(
                "[web_intelligence] DDG attempt %d failed: %s", attempt + 1, exc
            )
    return []


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def _classify_alert(title: str, snippet: str) -> dict:
    """Classify a search result into a threat category and severity."""
    text = f"{title} {snippet}".lower()

    matched_cat = None
    match_count = 0
    for cat, keywords in _CATEGORY_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits > match_count:
            match_count = hits
            matched_cat = cat

    if not matched_cat or match_count == 0:
        return {"category": "unknown", "severity": "LOW", "relevant": False}

    # Severity: more keyword hits = higher severity
    if match_count >= 3:
        severity = "HIGH"
    elif match_count >= 2:
        severity = "MODERATE"
    else:
        severity = "LOW"

    # Boost severity for inherently dangerous categories
    if matched_cat in ("armed_conflict", "piracy") and severity == "MODERATE":
        severity = "HIGH"

    return {"category": matched_cat, "severity": severity, "relevant": True}


def _compute_threat_level(alerts: list[dict]) -> str:
    """Compute overall threat level from individual alerts."""
    if not alerts:
        return "LOW"
    severities = [a["severity"] for a in alerts]
    if "CRITICAL" in severities:
        return "CRITICAL"
    high_count = severities.count("HIGH")
    if high_count >= 2:
        return "HIGH"
    if high_count >= 1 or severities.count("MODERATE") >= 2:
        return "MODERATE"
    return "LOW"


# ---------------------------------------------------------------------------
# Main search function
# ---------------------------------------------------------------------------

async def search_web_intelligence(
    route_description: str,
    regions: list[str] | None = None,
    categories: list[str] | None = None,
    brave_api_key: str = "",
) -> dict:
    """Run web intelligence search and return structured threat assessment."""
    queries = _build_queries(route_description, regions, categories)
    log.info(
        "[web_intelligence] route=%r regions=%s queries=%d",
        route_description[:80], regions, len(queries),
    )

    all_results: list[dict] = []
    seen_urls: set[str] = set()
    engine_used = "none"

    for query in queries:
        # Priority: Firecrawl (corporate-friendly) → Brave → DuckDuckGo
        results = await _search_firecrawl(query, max_results=3)
        if results:
            engine_used = "firecrawl"
        if not results and brave_api_key:
            results = await _search_brave(query, brave_api_key, max_results=3)
            if results:
                engine_used = "brave"
        if not results:
            results = _search_ddg(query, max_results=3)
            if results:
                engine_used = "duckduckgo"

        for r in results:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_results.append(r)

    # Classify results
    alerts: list[dict] = []
    for r in all_results:
        classification = _classify_alert(r["title"], r["snippet"])
        if classification["relevant"]:
            alerts.append({
                "category": classification["category"],
                "severity": classification["severity"],
                "title": r["title"],
                "summary": r["snippet"][:300],
                "source_url": r["url"],
                "source_engine": engine_used,
            })

    # Sort by severity (CRITICAL > HIGH > MODERATE > LOW)
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MODERATE": 2, "LOW": 3}
    alerts.sort(key=lambda a: severity_order.get(a["severity"], 4))

    overall = _compute_threat_level(alerts)

    # Build advisory text
    if overall in ("CRITICAL", "HIGH"):
        advisory = (
            f"⚠️ {overall} THREAT LEVEL: Active threats detected along this "
            f"route. Review the alerts below and consider route diversions or "
            f"enhanced security measures."
        )
    elif overall == "MODERATE":
        advisory = (
            "MODERATE THREAT LEVEL: Some potential risks identified along "
            "this route. Monitor advisories and maintain heightened awareness."
        )
    else:
        advisory = (
            "LOW THREAT LEVEL: No significant current threats detected. "
            "Proceed with standard safety protocols."
        )

    return {
        "alerts": alerts[:15],  # Cap at 15 alerts
        "overall_threat_level": overall,
        "route_advisory": advisory,
        "regions_checked": regions or [],
        "categories_checked": categories or THREAT_CATEGORIES,
        "search_engine_used": engine_used,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_results_analyzed": len(all_results),
        "queries_run": len(queries),
    }


# ---------------------------------------------------------------------------
# DynamicTool
# ---------------------------------------------------------------------------

class WebIntelligenceTool(DynamicTool):
    """Searches the web for current events affecting shipping routes."""

    def __init__(self, tool_config: dict | None = None, **kwargs):
        super().__init__(tool_config=tool_config, **kwargs)
        cfg = tool_config or {}
        self._brave_api_key = cfg.get("brave_api_key", BRAVE_SEARCH_API_KEY)

    @property
    def tool_name(self) -> str:
        return "web_intelligence"

    @property
    def tool_description(self) -> str:
        return (
            "Searches the web for current events affecting a shipping route: "
            "piracy alerts, armed conflicts, weather disasters, port closures, "
            "sanctions, and environmental hazards.  Returns structured threat "
            "intelligence with severity levels and route advisories.  Call this "
            "before route planning to check for active disruptions."
        )

    @property
    def parameters_schema(self) -> adk_types.Schema:
        return adk_types.Schema(
            type=adk_types.Type.OBJECT,
            properties={
                "route_description": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description=(
                        "Description of the shipping route, e.g. "
                        "'Strait of Hormuz to Mumbai via Arabian Sea'"
                    ),
                ),
                "regions": adk_types.Schema(
                    type=adk_types.Type.ARRAY,
                    items=adk_types.Schema(type=adk_types.Type.STRING),
                    description=(
                        "Key regions/chokepoints along the route to check, "
                        "e.g. ['Strait of Hormuz', 'Arabian Sea', 'Mumbai']"
                    ),
                    nullable=True,
                ),
                "categories": adk_types.Schema(
                    type=adk_types.Type.ARRAY,
                    items=adk_types.Schema(type=adk_types.Type.STRING),
                    description=(
                        "Threat categories to focus on.  Options: piracy, "
                        "armed_conflict, weather_disaster, port_closure, "
                        "sanctions, environmental_hazard.  Default: all."
                    ),
                    nullable=True,
                ),
            },
            required=["route_description"],
        )

    async def _run_async_impl(
        self,
        args: dict,
        tool_context: Optional[ToolContext] = None,
        credential: Optional[str] = None,
    ) -> dict:
        try:
            return await search_web_intelligence(
                route_description=str(args.get("route_description", "")),
                regions=args.get("regions"),
                categories=args.get("categories"),
                brave_api_key=self._brave_api_key,
            )
        except Exception as exc:
            log.exception("[web_intelligence] Unexpected error: %s", exc)
            return {
                "alerts": [],
                "overall_threat_level": "UNKNOWN",
                "route_advisory": f"Web intelligence search failed: {exc}",
                "error": str(exc),
            }
