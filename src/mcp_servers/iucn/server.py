"""IUCN Red List MCP server.

Provides conservation status and threat information for cetacean species
via the IUCN Red List API.

API: https://apiv3.iucnredlist.org/api/v3 (requires IUCN_API_KEY via ?token=)
"""

import os
import sys
import logging

from fastmcp import FastMCP

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from mcp_servers._http import (
    resilient_get,
    CircuitOpenError,
    RetryExhaustedError,
    raise_or_return_error,
)
from mcp_servers._security import sanitize_query

log = logging.getLogger(__name__)

mcp = FastMCP("iucn")

IUCN_API_BASE = "https://apiv3.iucnredlist.org/api/v3"
IUCN_API_KEY = os.environ.get("IUCN_API_KEY", "")


def _token_params() -> dict:
    """Return query params with the API token."""
    return {"token": IUCN_API_KEY}


@mcp.tool()
async def get_species_status(species_name: str) -> dict:
    """Get IUCN Red List conservation status for a species.

    Args:
        species_name: Species common or scientific name (e.g. 'Blue Whale',
            'Balaenoptera musculus').

    Returns conservation status, population trend, habitat info,
    and major threats.
    """
    if not IUCN_API_KEY:
        return {
            "error": "IUCN_API_KEY environment variable not set",
            "species": {},
        }

    safe_name = sanitize_query(species_name, max_len=200)
    if not safe_name:
        return {"error": "Empty species name after sanitization", "species": {}}

    # Try scientific name endpoint first
    url = f"{IUCN_API_BASE}/species/{safe_name}"
    params = _token_params()

    try:
        response = await resilient_get(url, params=params)
    except (CircuitOpenError, RetryExhaustedError) as exc:
        return raise_or_return_error(
            exc, "iucn", "get_species_status", species={}
        )

    if response.status_code != 200:
        return {
            "error": f"IUCN API returned {response.status_code}",
            "species": {},
        }

    data = response.json()
    results = data.get("result", [])

    if not results:
        return {
            "success": True,
            "message": f"No IUCN data found for '{safe_name}'",
            "species": {},
        }

    species_info = results[0]

    # Fetch threats for this species
    threats = []
    taxon_id = species_info.get("taxonid")
    if taxon_id:
        threats = await _fetch_threats(taxon_id)

    return {
        "success": True,
        "species": {
            "taxon_id": taxon_id,
            "scientific_name": species_info.get("scientific_name", ""),
            "common_name": species_info.get("main_common_name", ""),
            "kingdom": species_info.get("kingdom", ""),
            "phylum": species_info.get("phylum", ""),
            "class": species_info.get("class", ""),
            "order": species_info.get("order", ""),
            "family": species_info.get("family", ""),
            "category": species_info.get("category", ""),
            "population_trend": species_info.get("population_trend", ""),
            "marine_system": species_info.get("marine_system"),
            "freshwater_system": species_info.get("freshwater_system"),
            "terrestrial_system": species_info.get("terrestrial_system"),
        },
        "threats": threats,
    }


async def _fetch_threats(taxon_id: int) -> list:
    """Fetch threat details for a given taxon ID."""
    url = f"{IUCN_API_BASE}/threats/species/id/{taxon_id}"
    params = _token_params()
    try:
        response = await resilient_get(url, params=params)
    except (CircuitOpenError, RetryExhaustedError):
        log.warning("Failed to fetch threats for taxon %s", taxon_id)
        return []

    if response.status_code != 200:
        return []

    data = response.json()
    threats = []
    for t in data.get("result", []):
        threats.append({
            "code": t.get("code", ""),
            "title": t.get("title", ""),
            "timing": t.get("timing", ""),
            "severity": t.get("severity", ""),
            "score": t.get("score", ""),
        })
    return threats


@mcp.tool()
async def get_species_by_region(region: str = "global") -> dict:
    """List cetacean species and their IUCN status for a region.

    Args:
        region: IUCN region identifier (default 'global').
            Examples: 'global', 'europe', 'mediterranean'.

    Returns list of cetacean species with their conservation categories.
    """
    if not IUCN_API_KEY:
        return {
            "error": "IUCN_API_KEY environment variable not set",
            "species_list": [],
        }

    safe_region = sanitize_query(region, max_len=50)
    if not safe_region:
        safe_region = "global"

    # Use the comprehensive group endpoint for cetaceans
    url = f"{IUCN_API_BASE}/comp-group/getspecies/cetaceans"
    params = _token_params()
    params["region"] = safe_region

    try:
        response = await resilient_get(url, params=params)
    except (CircuitOpenError, RetryExhaustedError) as exc:
        return raise_or_return_error(
            exc, "iucn", "get_species_by_region", species_list=[]
        )

    if response.status_code != 200:
        return {
            "error": f"IUCN API returned {response.status_code}",
            "species_list": [],
        }

    data = response.json()
    results = data.get("result", [])

    species_list = []
    for sp in results:
        species_list.append({
            "taxon_id": sp.get("taxonid"),
            "scientific_name": sp.get("scientific_name", ""),
            "common_name": sp.get("main_common_name", ""),
            "family": sp.get("family", ""),
            "category": sp.get("category", ""),
            "population_trend": sp.get("population_trend", ""),
        })

    return {
        "success": True,
        "region": safe_region,
        "returned_count": len(species_list),
        "species_list": species_list,
    }


if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=9006)
