"""GBIF Occurrence MCP server.

Provides whale occurrence records from the Global Biodiversity Information
Facility (GBIF) to support historical whale distribution analysis.

API: https://api.gbif.org/v1/occurrence/search (free, optional auth)
Uses taxonKey=733 (order Cetacea) as base filter.
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

mcp = FastMCP("gbif")

GBIF_API_BASE = "https://api.gbif.org/v1"
CETACEA_TAXON_KEY = 733  # Order Cetacea


@mcp.tool()
async def search_whale_occurrences(
    species_name: str = None,
    latitude: float = None,
    longitude: float = None,
    radius_km: float = 200,
    year: int = None,
    limit: int = 50,
) -> dict:
    """Search GBIF for whale occurrence records.

    Args:
        species_name: Optional species name to filter (e.g. 'Balaenoptera musculus').
        latitude: Optional center latitude for geographic filter.
        longitude: Optional center longitude for geographic filter.
        radius_km: Search radius in km when lat/lng provided (default 200).
        year: Optional year filter.
        limit: Maximum number of records to return (default 50, max 300).

    Returns occurrence records with species, location, date, and dataset info.
    """
    limit = max(1, min(300, limit))
    radius_km = max(1.0, min(5000.0, radius_km))

    params = {
        "taxonKey": str(CETACEA_TAXON_KEY),
        "limit": str(limit),
        "hasCoordinate": "true",
    }

    if species_name:
        safe_name = sanitize_query(species_name, max_len=200)
        if safe_name:
            params["scientificName"] = safe_name

    if latitude is not None and longitude is not None:
        if not (-90 <= latitude <= 90):
            return {
                "error": "Latitude must be between -90 and 90",
                "occurrences": [],
            }
        if not (-180 <= longitude <= 180):
            return {
                "error": "Longitude must be between -180 and 180",
                "occurrences": [],
            }
        # GBIF uses decimalLatitude/decimalLongitude with a distance filter
        params["decimalLatitude"] = str(latitude)
        params["decimalLongitude"] = str(longitude)
        params["geoDistance"] = f"{latitude},{longitude},{radius_km}km"

    if year is not None:
        params["year"] = str(year)

    url = f"{GBIF_API_BASE}/occurrence/search"

    try:
        response = await resilient_get(url, params=params)
    except (CircuitOpenError, RetryExhaustedError) as exc:
        return raise_or_return_error(
            exc, "gbif", "search_whale_occurrences", occurrences=[]
        )

    if response.status_code != 200:
        return {
            "error": f"GBIF API returned {response.status_code}",
            "occurrences": [],
        }

    data = response.json()
    results_raw = data.get("results", [])

    occurrences = []
    for rec in results_raw:
        occurrences.append({
            "gbif_id": rec.get("key"),
            "species": rec.get("species", rec.get("scientificName", "")),
            "scientific_name": rec.get("scientificName", ""),
            "latitude": rec.get("decimalLatitude"),
            "longitude": rec.get("decimalLongitude"),
            "event_date": rec.get("eventDate", ""),
            "year": rec.get("year"),
            "country": rec.get("country", ""),
            "basis_of_record": rec.get("basisOfRecord", ""),
            "dataset_name": rec.get("datasetName", ""),
            "institution_code": rec.get("institutionCode", ""),
        })

    return {
        "success": True,
        "total_count": data.get("count", 0),
        "returned_count": len(occurrences),
        "species_filter": species_name,
        "occurrences": occurrences,
    }


if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=9005)
