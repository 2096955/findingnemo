"""Tests for the GBIF Occurrence MCP server."""

import sys
import os
import pytest
import respx
import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from mcp_servers.gbif import server as gbif_module

search_whale_occurrences = gbif_module.search_whale_occurrences.fn


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GBIF_RESPONSE = {
    "count": 1250,
    "results": [
        {
            "key": 100001,
            "species": "Balaenoptera musculus",
            "scientificName": "Balaenoptera musculus (Linnaeus, 1758)",
            "decimalLatitude": 34.12,
            "decimalLongitude": -119.80,
            "eventDate": "2025-08-15",
            "year": 2025,
            "country": "US",
            "basisOfRecord": "HUMAN_OBSERVATION",
            "datasetName": "iNaturalist Research-grade Observations",
            "institutionCode": "iNaturalist",
        },
        {
            "key": 100002,
            "species": "Megaptera novaeangliae",
            "scientificName": "Megaptera novaeangliae (Borowski, 1781)",
            "decimalLatitude": 34.05,
            "decimalLongitude": -119.65,
            "eventDate": "2025-07-20",
            "year": 2025,
            "country": "US",
            "basisOfRecord": "HUMAN_OBSERVATION",
            "datasetName": "eBird Observation Dataset",
            "institutionCode": "CLO",
        },
    ],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_whale_occurrences_success():
    with respx.mock:
        respx.get("https://api.gbif.org/v1/occurrence/search").mock(
            return_value=httpx.Response(200, json=GBIF_RESPONSE)
        )

        result = await search_whale_occurrences(
            species_name="Balaenoptera musculus",
            latitude=34.0,
            longitude=-119.5,
        )

    assert result["success"] is True
    assert result["total_count"] == 1250
    assert result["returned_count"] == 2
    assert result["species_filter"] == "Balaenoptera musculus"

    first = result["occurrences"][0]
    assert first["gbif_id"] == 100001
    assert first["species"] == "Balaenoptera musculus"
    assert first["latitude"] == 34.12
    assert first["country"] == "US"


@pytest.mark.asyncio
async def test_search_whale_occurrences_no_filters():
    with respx.mock:
        respx.get("https://api.gbif.org/v1/occurrence/search").mock(
            return_value=httpx.Response(200, json=GBIF_RESPONSE)
        )

        result = await search_whale_occurrences()

    assert result["success"] is True
    assert result["species_filter"] is None


@pytest.mark.asyncio
async def test_search_whale_occurrences_api_error():
    """Non-retryable HTTP error returns a structured error dict."""
    with respx.mock:
        respx.get("https://api.gbif.org/v1/occurrence/search").mock(
            return_value=httpx.Response(400, json={"error": "Bad request"})
        )

        result = await search_whale_occurrences()

    assert "error" in result
    assert result["occurrences"] == []


@pytest.mark.asyncio
async def test_search_whale_occurrences_invalid_latitude():
    result = await search_whale_occurrences(latitude=100.0, longitude=0.0)
    assert "error" in result
    assert "Latitude" in result["error"]


@pytest.mark.asyncio
async def test_search_whale_occurrences_limit_clamped():
    with respx.mock:
        respx.get("https://api.gbif.org/v1/occurrence/search").mock(
            return_value=httpx.Response(200, json=GBIF_RESPONSE)
        )

        result = await search_whale_occurrences(limit=999)

    assert result["success"] is True
    # The limit is clamped internally to 300 but the response contains 2 results
    assert result["returned_count"] == 2
