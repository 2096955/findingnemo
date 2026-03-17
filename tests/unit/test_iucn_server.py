"""Tests for the IUCN Red List MCP server."""

import sys
import os
import pytest
import respx
import httpx
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from mcp_servers.iucn import server as iucn_module

get_species_status = iucn_module.get_species_status.fn
get_species_by_region = iucn_module.get_species_by_region.fn


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SPECIES_RESPONSE = {
    "result": [
        {
            "taxonid": 2477,
            "scientific_name": "Balaenoptera musculus",
            "main_common_name": "Blue Whale",
            "kingdom": "ANIMALIA",
            "phylum": "CHORDATA",
            "class": "MAMMALIA",
            "order": "CETARTIODACTYLA",
            "family": "BALAENOPTERIDAE",
            "category": "EN",
            "population_trend": "Increasing",
            "marine_system": True,
            "freshwater_system": False,
            "terrestrial_system": False,
        }
    ]
}

THREATS_RESPONSE = {
    "result": [
        {
            "code": "5.4.4",
            "title": "Fishing & harvesting aquatic resources - Unintentional effects: large scale",
            "timing": "Ongoing",
            "severity": "Unknown",
            "score": "Low Impact",
        },
        {
            "code": "9.6",
            "title": "Pollution - Excess energy (noise, light)",
            "timing": "Ongoing",
            "severity": "Unknown",
            "score": "Low Impact",
        },
    ]
}

REGION_RESPONSE = {
    "result": [
        {
            "taxonid": 2477,
            "scientific_name": "Balaenoptera musculus",
            "main_common_name": "Blue Whale",
            "family": "BALAENOPTERIDAE",
            "category": "EN",
            "population_trend": "Increasing",
        },
        {
            "taxonid": 13006,
            "scientific_name": "Megaptera novaeangliae",
            "main_common_name": "Humpback Whale",
            "family": "BALAENOPTERIDAE",
            "category": "LC",
            "population_trend": "Increasing",
        },
    ]
}


# ---------------------------------------------------------------------------
# Tests: get_species_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_species_status_success():
    with patch.object(iucn_module, "IUCN_API_KEY", "test-key-123"):
        with respx.mock:
            respx.get(
                "https://apiv3.iucnredlist.org/api/v3/species/Balaenoptera musculus"
            ).mock(return_value=httpx.Response(200, json=SPECIES_RESPONSE))

            respx.get(
                "https://apiv3.iucnredlist.org/api/v3/threats/species/id/2477"
            ).mock(return_value=httpx.Response(200, json=THREATS_RESPONSE))

            result = await get_species_status("Balaenoptera musculus")

    assert result["success"] is True
    sp = result["species"]
    assert sp["scientific_name"] == "Balaenoptera musculus"
    assert sp["common_name"] == "Blue Whale"
    assert sp["category"] == "EN"
    assert sp["population_trend"] == "Increasing"
    assert sp["marine_system"] is True

    assert len(result["threats"]) == 2
    assert result["threats"][0]["title"].startswith("Fishing")


@pytest.mark.asyncio
async def test_get_species_status_no_api_key():
    with patch.object(iucn_module, "IUCN_API_KEY", ""):
        result = await get_species_status("Blue Whale")

    assert "error" in result
    assert "IUCN_API_KEY" in result["error"]


@pytest.mark.asyncio
async def test_get_species_status_not_found():
    with patch.object(iucn_module, "IUCN_API_KEY", "test-key-123"):
        with respx.mock:
            respx.get(
                "https://apiv3.iucnredlist.org/api/v3/species/Nonexistus bogus"
            ).mock(return_value=httpx.Response(200, json={"result": []}))

            result = await get_species_status("Nonexistus bogus")

    assert result["success"] is True
    assert result["species"] == {}
    assert "No IUCN data" in result["message"]


# ---------------------------------------------------------------------------
# Tests: get_species_by_region
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_species_by_region_success():
    with patch.object(iucn_module, "IUCN_API_KEY", "test-key-123"):
        with respx.mock:
            respx.get(
                "https://apiv3.iucnredlist.org/api/v3/comp-group/getspecies/cetaceans"
            ).mock(return_value=httpx.Response(200, json=REGION_RESPONSE))

            result = await get_species_by_region("global")

    assert result["success"] is True
    assert result["region"] == "global"
    assert result["returned_count"] == 2

    assert result["species_list"][0]["common_name"] == "Blue Whale"
    assert result["species_list"][1]["category"] == "LC"


@pytest.mark.asyncio
async def test_get_species_by_region_no_api_key():
    with patch.object(iucn_module, "IUCN_API_KEY", ""):
        result = await get_species_by_region()

    assert "error" in result
    assert result["species_list"] == []
