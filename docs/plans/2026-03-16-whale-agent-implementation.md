# Whale Agent Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a PoC agentic system that reduces whale-vessel collisions, with 11 agents, 6 MCP servers, custom tools, and a Deck.gl map dashboard — forked from the MedExpert/SAM architecture.

**Architecture:** Fork the MedExpert application structure on Solace Agent Mesh (SAM). Replace medical agents with whale-specific specialists, swap MCP servers for marine data sources, build custom tools for risk scoring and route optimization, and add a Deck.gl + MapLibre GL dashboard alongside the existing chat UI.

**Tech Stack:** Python 3.10+ (SAM framework, FastMCP, httpx, LiteLLM), React + Vite + TypeScript (frontend), Deck.gl + MapLibre GL (map visualization), Redis (hot memory), SQLite (cold store)

**Data Framework (Project Resilience):** All data and agent outputs must follow the Context / Actions / Outcomes decision pattern:
- **Context attributes**: Ship type, location, collision risk maps, vessel traffic, weather (air/ocean temp, currents), season, whale spotting areas, krill distribution
- **Available actions**: Dynamic route adjustments, protection area suggestions, speed reduction in high-risk zones, course modifications, situational awareness enhancement
- **Outcome metrics**: Crew safety maximization, whale strike minimization, fuel consumption reduction, delay minimization

Tools should produce structured C/A/O data that can be collected as tabular decision records for training predictors. The `cold_store` should persist historical decisions in this format.

---

## Phase 1: Project Scaffolding & Infrastructure

### Task 1: Initialize project structure and pyproject.toml

**Files:**
- Create: `whales/pyproject.toml`
- Create: `whales/.env.example`
- Create: `whales/src/whale_tools/__init__.py`
- Create: `whales/src/whale_common/__init__.py`
- Create: `whales/src/mcp_servers/__init__.py`

**Step 1: Create pyproject.toml**

```python
# whales/pyproject.toml
[project]
name = "whale-agent"
version = "0.1.0"
description = "Whale-vessel collision avoidance agent built on Solace Agent Mesh"
requires-python = ">=3.10"
dependencies = [
    "solace-agent-mesh>=1.16,<2.0",
    "fastmcp>=2.11,<3.0",
    "httpx>=0.27,<1.0",
    "redis[hiredis]>=5.0,<6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-mock",
    "respx>=0.21",
    "ruff",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = [".", "src"]

[tool.ruff]
line-length = 88

[tool.ruff.lint]
select = ["E", "W", "F", "I", "UP", "B", "C4", "SIM"]
ignore = ["E501", "B008"]
```

**Step 2: Create .env.example**

```bash
# whales/.env.example
# LLM provider (via LiteLLM — set one or more)
GEMINI_API_KEY=
ANTHROPIC_API_KEY=
OPENAI_API_KEY=

# Vertex AI (optional — for vertex_ai/ models)
GOOGLE_APPLICATION_CREDENTIALS=

# Data source API keys
WHALE_ALERT_API_KEY=          # whalealert.org
IUCN_API_KEY=                 # apiv3.iucnredlist.org
GBIF_USERNAME=                # gbif.org (optional, increases rate limit)
GBIF_PASSWORD=

# Infrastructure
REDIS_URL=redis://localhost:6379/0
SOLACE_DEV_MODE=true
```

**Step 3: Create __init__.py files for all Python packages**

```python
# whales/src/whale_tools/__init__.py
# whales/src/whale_common/__init__.py
# whales/src/mcp_servers/__init__.py
# (all empty)
```

**Step 4: Create directory structure**

```bash
mkdir -p configs/agents configs/gateways src/whale_tools src/whale_common src/mcp_servers
mkdir -p src/mcp_servers/noaa src/mcp_servers/whale_alert src/mcp_servers/marine_cadastre
mkdir -p src/mcp_servers/open_meteo src/mcp_servers/gbif src/mcp_servers/iucn
mkdir -p data scripts tests/unit tests/contract tests/integration
```

**Step 5: Commit**

```bash
git init
git add -A
git commit --signoff -m "feat: scaffold whale-agent project structure"
```

---

### Task 2: Create shared_config.yaml and constants

**Files:**
- Create: `whales/configs/shared_config.yaml`
- Create: `whales/src/whale_common/constants.py`

**Step 1: Write shared_config.yaml**

```yaml
# whales/configs/shared_config.yaml
shared_config:
  - broker_connection: &broker_connection
      dev_mode: ${SOLACE_DEV_MODE, true}
      broker_url: ${SOLACE_BROKER_URL, ws://localhost:8008}
      broker_username: ${SOLACE_BROKER_USERNAME, default}
      broker_password: ${SOLACE_BROKER_PASSWORD, default}
      broker_vpn: ${SOLACE_BROKER_VPN, default}
      temporary_queue: ${USE_TEMPORARY_QUEUES, true}

  # Temperature-tiered model anchors — configurable via LiteLLM
  - models:
    orchestrator: &orchestrator_model
      model: ${LLM_ORCHESTRATOR_MODEL, vertex_ai/gemini-2.5-flash}
      temperature: 0.2
      max_tokens: 16000
      parallel_tool_calls: true
      cache_strategy: "none"
      num_retries: 2

    specialist: &specialist_model
      model: ${LLM_SPECIALIST_MODEL, vertex_ai/gemini-2.5-flash}
      temperature: 0.3
      max_tokens: 12000
      parallel_tool_calls: true
      cache_strategy: "none"
      num_retries: 2

    verifier: &verifier_model
      model: ${LLM_VERIFIER_MODEL, vertex_ai/gemini-2.5-pro}
      temperature: 0.1
      max_tokens: 8000
      cache_strategy: "none"
      num_retries: 3

    reviser: &reviser_model
      model: ${LLM_REVISER_MODEL, vertex_ai/gemini-2.5-flash}
      temperature: 0.3
      max_tokens: 12000
      cache_strategy: "none"
      num_retries: 2

    general: &general_model
      model: ${LLM_GENERAL_MODEL, vertex_ai/gemini-2.5-flash}
      cache_strategy: "none"

  - services:
    session_service: &default_session_service
      type: "memory"

    artifact_service: &default_artifact_service
      type: "filesystem"
      base_path: "/tmp/whale-agent"
      artifact_scope: namespace
```

**Step 2: Write constants.py**

```python
# whales/src/whale_common/constants.py
"""Whale Agent constants — API URLs, port mappings, domain routing."""

# MCP server ports
MCP_PORTS = {
    "noaa": 9001,
    "whale_alert": 9002,
    "marine_cadastre": 9003,
    "open_meteo": 9004,
    "gbif": 9005,
    "iucn": 9006,
}

# API base URLs
NOAA_WEATHER_BASE_URL = "https://api.weather.gov"
NOAA_NDBC_BASE_URL = "https://www.ndbc.noaa.gov/data/realtime2"
WHALE_ALERT_BASE_URL = "https://www.whalealert.org/api/v1"
MARINE_CADASTRE_BASE_URL = "https://marinecadastre.gov/ais"
OPEN_METEO_MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
GBIF_API_BASE_URL = "https://api.gbif.org/v1"
IUCN_API_BASE_URL = "https://apiv3.iucnredlist.org/api/v3"

# Whale taxon keys for GBIF queries (order Cetacea)
CETACEA_TAXON_KEY = 733  # GBIF taxon key for order Cetacea

# Common whale species and IUCN status
WHALE_SPECIES = {
    "blue_whale": {"scientific": "Balaenoptera musculus", "iucn": "EN"},
    "humpback_whale": {"scientific": "Megaptera novaeangliae", "iucn": "LC"},
    "north_atlantic_right_whale": {"scientific": "Eubalaena glacialis", "iucn": "CR"},
    "fin_whale": {"scientific": "Balaenoptera physalus", "iucn": "VU"},
    "gray_whale": {"scientific": "Eschrichtius robustus", "iucn": "LC"},
    "sperm_whale": {"scientific": "Physeter macrocephalus", "iucn": "VU"},
    "bowhead_whale": {"scientific": "Balaena mysticetus", "iucn": "LC"},
    "sei_whale": {"scientific": "Balaenoptera borealis", "iucn": "EN"},
    "minke_whale": {"scientific": "Balaenoptera acutorostrata", "iucn": "LC"},
}

# Domain → Agent routing for query decomposer
DOMAIN_AGENT_ROUTING = {
    "route_optimization": {
        "agent": "RouteOptimizer",
        "keywords": [
            "route", "path", "navigate", "waypoint", "shipping lane",
            "port", "voyage", "course", "detour", "diversion",
            "shortest", "safest", "optimal", "efficient",
        ],
    },
    "risk_assessment": {
        "agent": "RiskAssessor",
        "keywords": [
            "risk", "collision", "strike", "probability", "danger",
            "hazard", "threat", "impact", "likelihood", "score",
        ],
    },
    "weather": {
        "agent": "WeatherAnalyst",
        "keywords": [
            "weather", "storm", "wind", "wave", "current", "temperature",
            "forecast", "sea state", "swell", "visibility", "fog",
            "climate", "ocean", "marine weather",
        ],
    },
    "vessel_traffic": {
        "agent": "VesselTrafficMonitor",
        "keywords": [
            "vessel", "ship", "traffic", "ais", "tanker", "cargo",
            "container", "fleet", "density", "lane", "shipping",
            "maritime", "port", "harbor",
        ],
    },
    "whale_migration": {
        "agent": "WhaleMigrationTracker",
        "keywords": [
            "migration", "migration pattern", "seasonal", "breeding",
            "calving", "feeding ground", "migratory", "range",
            "movement", "corridor", "pathway",
        ],
    },
    "habitat": {
        "agent": "HabitatAnalyst",
        "keywords": [
            "habitat", "krill", "plankton", "feeding", "prey",
            "ecosystem", "environment", "upwelling", "nutrient",
            "biodiversity", "marine habitat",
        ],
    },
    "species": {
        "agent": "SpeciesIdentifier",
        "keywords": [
            "species", "whale", "cetacean", "baleen", "toothed",
            "endangered", "conservation", "population", "iucn",
            "protected", "threatened", "vulnerable",
        ],
    },
    "incidents": {
        "agent": "IncidentAnalyst",
        "keywords": [
            "incident", "strike", "collision", "historical", "accident",
            "record", "database", "trend", "fatality", "injury",
            "mortality", "report",
        ],
    },
}
```

**Step 3: Commit**

```bash
git add configs/shared_config.yaml src/whale_common/constants.py
git commit --signoff -m "feat: add shared config and whale domain constants"
```

---

### Task 3: Copy and adapt shared HTTP/security utilities from MedExpert

**Files:**
- Create: `whales/src/mcp_servers/_http.py`
- Create: `whales/src/mcp_servers/_security.py`

**Step 1: Copy _http.py verbatim from MedExpert**

Copy `medexpert/src/mcp_servers/_http.py` to `whales/src/mcp_servers/_http.py`. This provides `resilient_get()`, `resilient_post()`, `CircuitBreaker`, `structured_error_response()`, `raise_or_return_error()`. No changes needed — it's domain-agnostic.

**Step 2: Copy _security.py from MedExpert, adapt**

Copy `medexpert/src/mcp_servers/_security.py` to `whales/src/mcp_servers/_security.py`. Keep `sanitize_query()` and `validate_allowed_url()`. Remove SoQL-specific functions (`escape_soql`, `escape_sql_string`) — whale MCP servers use REST APIs, not SoQL.

**Step 3: Write tests for copied utilities**

Create: `whales/tests/unit/test_http.py`

```python
import pytest
from mcp_servers._http import CircuitBreaker, CircuitState, structured_error_response

def test_circuit_breaker_stays_closed_on_success():
    cb = CircuitBreaker(failure_threshold=3)
    assert cb.allow_request("https://api.example.com") is True
    cb.record_success("https://api.example.com")
    assert cb.allow_request("https://api.example.com") is True

def test_circuit_breaker_opens_after_threshold():
    cb = CircuitBreaker(failure_threshold=3)
    for _ in range(3):
        cb.record_failure("https://api.example.com")
    assert cb.allow_request("https://api.example.com") is False

def test_structured_error_response_includes_required_fields():
    err = structured_error_response(Exception("test"), "noaa", "get_weather")
    assert err["success"] is False
    assert err["server"] == "noaa"
    assert err["tool"] == "get_weather"
    assert "error_category" in err
```

**Step 4: Run tests**

```bash
cd whales && pytest tests/unit/test_http.py -v
```
Expected: 3 PASS

**Step 5: Commit**

```bash
git add src/mcp_servers/_http.py src/mcp_servers/_security.py tests/unit/test_http.py
git commit --signoff -m "feat: add resilient HTTP client and security utilities"
```

---

## Phase 2: MCP Servers (Data Sources)

### Task 4: Build NOAA MCP server

**Files:**
- Create: `whales/src/mcp_servers/noaa/server.py`
- Create: `whales/tests/unit/test_noaa_server.py`

**Step 1: Write the failing test**

```python
# whales/tests/unit/test_noaa_server.py
import pytest
import respx
import httpx

@pytest.fixture
def mock_noaa_forecast():
    return {
        "properties": {
            "periods": [
                {
                    "number": 1,
                    "name": "Tonight",
                    "temperature": 55,
                    "windSpeed": "10 mph",
                    "shortForecast": "Partly Cloudy",
                }
            ]
        }
    }

@respx.mock
@pytest.mark.asyncio
async def test_get_marine_forecast(mock_noaa_forecast):
    from mcp_servers.noaa.server import get_marine_forecast
    respx.get("https://api.weather.gov/gridpoints/SEW/124,67/forecast").mock(
        return_value=httpx.Response(200, json=mock_noaa_forecast)
    )
    result = await get_marine_forecast(grid_office="SEW", grid_x=124, grid_y=67)
    assert result["success"] is True
    assert len(result["periods"]) > 0
```

**Step 2: Run test to verify it fails**

```bash
cd whales && pytest tests/unit/test_noaa_server.py -v
```
Expected: FAIL — module not found

**Step 3: Write NOAA MCP server**

```python
# whales/src/mcp_servers/noaa/server.py
"""NOAA Weather & Ocean Data MCP server.

Provides marine weather forecasts, buoy observations, and ocean
conditions from NOAA APIs. Free, no API key required.
"""

import os
import sys
import logging

from fastmcp import FastMCP

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from mcp_servers._http import resilient_get, CircuitOpenError, RetryExhaustedError, raise_or_return_error
from mcp_servers._security import sanitize_query

log = logging.getLogger(__name__)

mcp = FastMCP("noaa")

WEATHER_API_BASE = "https://api.weather.gov"
NDBC_BASE = "https://www.ndbc.noaa.gov/data/realtime2"


@mcp.tool()
async def get_marine_forecast(
    grid_office: str, grid_x: int, grid_y: int
) -> dict:
    """Get marine weather forecast from NOAA Weather API.

    Args:
        grid_office: NWS grid office code (e.g., "SEW" for Seattle)
        grid_x: Grid X coordinate
        grid_y: Grid Y coordinate

    Returns forecast periods with temperature, wind, and conditions.
    """
    url = f"{WEATHER_API_BASE}/gridpoints/{grid_office}/{grid_x},{grid_y}/forecast"
    headers = {"User-Agent": "WhaleAgent/1.0", "Accept": "application/geo+json"}

    try:
        response = await resilient_get(url, headers=headers)
    except (CircuitOpenError, RetryExhaustedError) as exc:
        return raise_or_return_error(exc, "noaa", "get_marine_forecast", periods=[])

    if response.status_code != 200:
        return {"success": False, "error": f"NOAA API returned {response.status_code}", "periods": []}

    data = response.json()
    periods = []
    for p in data.get("properties", {}).get("periods", [])[:12]:
        periods.append({
            "name": p.get("name", ""),
            "temperature": p.get("temperature"),
            "temperature_unit": p.get("temperatureUnit", "F"),
            "wind_speed": p.get("windSpeed", ""),
            "wind_direction": p.get("windDirection", ""),
            "forecast": p.get("shortForecast", ""),
            "detailed": p.get("detailedForecast", ""),
        })

    return {"success": True, "grid": f"{grid_office}/{grid_x},{grid_y}", "periods": periods}


@mcp.tool()
async def get_buoy_data(station_id: str) -> dict:
    """Get real-time ocean observations from an NDBC buoy station.

    Args:
        station_id: NDBC buoy station ID (e.g., "46029" for Columbia River Bar)

    Returns wave height, water temperature, wind, and pressure data.
    """
    safe_id = sanitize_query(station_id, max_len=10)
    url = f"{NDBC_BASE}/{safe_id}.txt"

    try:
        response = await resilient_get(url)
    except (CircuitOpenError, RetryExhaustedError) as exc:
        return raise_or_return_error(exc, "noaa", "get_buoy_data", observations=[])

    if response.status_code != 200:
        return {"success": False, "error": f"NDBC returned {response.status_code}", "observations": []}

    lines = response.text.strip().split("\n")
    if len(lines) < 3:
        return {"success": False, "error": "No buoy data available", "observations": []}

    headers_line = lines[0].split()
    observations = []
    for line in lines[2:7]:  # Latest 5 observations
        values = line.split()
        if len(values) >= 13:
            observations.append({
                "datetime": f"{values[0]}-{values[1]}-{values[2]} {values[3]}:{values[4]}",
                "wind_direction_deg": values[5],
                "wind_speed_mps": values[6],
                "gust_mps": values[7],
                "wave_height_m": values[8],
                "dominant_wave_period_s": values[9],
                "pressure_hpa": values[12],
            })

    return {"success": True, "station_id": safe_id, "observations": observations}


if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=9001)
```

**Step 4: Run test to verify it passes**

```bash
cd whales && pytest tests/unit/test_noaa_server.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add src/mcp_servers/noaa/ tests/unit/test_noaa_server.py
git commit --signoff -m "feat: add NOAA weather and buoy MCP server"
```

---

### Task 5: Build Open-Meteo Marine MCP server

**Files:**
- Create: `whales/src/mcp_servers/open_meteo/server.py`
- Create: `whales/tests/unit/test_open_meteo_server.py`

**Step 1: Write the failing test**

```python
# whales/tests/unit/test_open_meteo_server.py
import pytest
import respx
import httpx

@respx.mock
@pytest.mark.asyncio
async def test_get_marine_conditions():
    from mcp_servers.open_meteo.server import get_marine_conditions
    respx.get("https://marine-api.open-meteo.com/v1/marine").mock(
        return_value=httpx.Response(200, json={
            "hourly": {
                "time": ["2026-03-16T00:00"],
                "wave_height": [2.1],
                "wave_period": [8.5],
                "swell_wave_height": [1.8],
                "ocean_current_velocity": [0.3],
            }
        })
    )
    result = await get_marine_conditions(latitude=47.6, longitude=-122.3)
    assert result["success"] is True
    assert len(result["hourly_data"]) > 0
```

**Step 2: Run test to verify failure, then implement**

```python
# whales/src/mcp_servers/open_meteo/server.py
"""Open-Meteo Marine Weather MCP server.

Free marine weather API — no API key needed. Provides wave height,
swell, ocean temperature, and current data for any coordinates.
"""

import os
import sys
import logging

from fastmcp import FastMCP

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from mcp_servers._http import resilient_get, CircuitOpenError, RetryExhaustedError, raise_or_return_error

log = logging.getLogger(__name__)

mcp = FastMCP("open_meteo")

MARINE_API_URL = "https://marine-api.open-meteo.com/v1/marine"


@mcp.tool()
async def get_marine_conditions(
    latitude: float, longitude: float, forecast_days: int = 3
) -> dict:
    """Get marine weather conditions for a location.

    Args:
        latitude: Latitude (-90 to 90)
        longitude: Longitude (-180 to 180)
        forecast_days: Number of forecast days (1-7, default 3)

    Returns hourly wave height, swell, period, and current data.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "wave_height,wave_period,swell_wave_height,swell_wave_period,ocean_current_velocity,ocean_current_direction",
        "forecast_days": min(forecast_days, 7),
    }

    try:
        response = await resilient_get(MARINE_API_URL, params=params)
    except (CircuitOpenError, RetryExhaustedError) as exc:
        return raise_or_return_error(exc, "open_meteo", "get_marine_conditions", hourly_data=[])

    if response.status_code != 200:
        return {"success": False, "error": f"Open-Meteo returned {response.status_code}", "hourly_data": []}

    data = response.json()
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])

    hourly_data = []
    for i, t in enumerate(times[:72]):  # Cap at 72 hours
        hourly_data.append({
            "time": t,
            "wave_height_m": hourly.get("wave_height", [None])[i] if i < len(hourly.get("wave_height", [])) else None,
            "wave_period_s": hourly.get("wave_period", [None])[i] if i < len(hourly.get("wave_period", [])) else None,
            "swell_height_m": hourly.get("swell_wave_height", [None])[i] if i < len(hourly.get("swell_wave_height", [])) else None,
            "current_velocity_ms": hourly.get("ocean_current_velocity", [None])[i] if i < len(hourly.get("ocean_current_velocity", [])) else None,
        })

    return {
        "success": True,
        "latitude": latitude,
        "longitude": longitude,
        "hourly_data": hourly_data,
    }


if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=9004)
```

**Step 3: Run tests, commit**

```bash
cd whales && pytest tests/unit/test_open_meteo_server.py -v
git add src/mcp_servers/open_meteo/ tests/unit/test_open_meteo_server.py
git commit --signoff -m "feat: add Open-Meteo marine weather MCP server"
```

---

### Task 6: Build Whale Alert MCP server

**Files:**
- Create: `whales/src/mcp_servers/whale_alert/server.py`
- Create: `whales/tests/unit/test_whale_alert_server.py`

**Step 1: Write test, then implement**

```python
# whales/src/mcp_servers/whale_alert/server.py
"""Whale Alert MCP server.

Provides real-time whale sighting data from the Whale Alert API.
Requires WHALE_ALERT_API_KEY environment variable.
"""

import os
import sys
import logging
import time

from fastmcp import FastMCP

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from mcp_servers._http import resilient_get, CircuitOpenError, RetryExhaustedError, raise_or_return_error
from mcp_servers._security import sanitize_query

log = logging.getLogger(__name__)

mcp = FastMCP("whale_alert")

API_BASE = "https://www.whalealert.org/api/v1"
API_KEY = os.environ.get("WHALE_ALERT_API_KEY", "")


@mcp.tool()
async def get_whale_sightings(
    latitude: float,
    longitude: float,
    radius_km: float = 100.0,
    hours_back: int = 72,
) -> dict:
    """Get recent whale sighting reports near a location.

    Args:
        latitude: Center latitude
        longitude: Center longitude
        radius_km: Search radius in kilometers (max 500)
        hours_back: How many hours back to search (max 168 = 7 days)
    """
    if not API_KEY:
        return {"success": False, "error": "WHALE_ALERT_API_KEY not set", "sightings": []}

    end_time = int(time.time())
    start_time = end_time - (min(hours_back, 168) * 3600)

    url = f"{API_BASE}/events"
    params = {
        "apiKey": API_KEY,
        "since": start_time,
        "until": end_time,
        "near": f"{latitude},{longitude}",
        "radius": min(radius_km, 500),
    }

    try:
        response = await resilient_get(url, params=params)
    except (CircuitOpenError, RetryExhaustedError) as exc:
        return raise_or_return_error(exc, "whale_alert", "get_whale_sightings", sightings=[])

    if response.status_code != 200:
        return {"success": False, "error": f"Whale Alert API returned {response.status_code}", "sightings": []}

    data = response.json()
    sightings = []
    for event in data.get("events", [])[:50]:
        sightings.append({
            "id": event.get("id"),
            "type": event.get("type"),
            "species": event.get("species"),
            "latitude": event.get("latitude"),
            "longitude": event.get("longitude"),
            "number_observed": event.get("number"),
            "timestamp": event.get("eventDate"),
            "description": event.get("description", ""),
        })

    return {
        "success": True,
        "center": {"lat": latitude, "lng": longitude},
        "radius_km": radius_km,
        "sighting_count": len(sightings),
        "sightings": sightings,
    }


if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=9002)
```

**Step 2: Test, commit**

```bash
cd whales && pytest tests/unit/test_whale_alert_server.py -v
git add src/mcp_servers/whale_alert/ tests/unit/test_whale_alert_server.py
git commit --signoff -m "feat: add Whale Alert sightings MCP server"
```

---

### Task 7: Build GBIF Occurrence MCP server

**Files:**
- Create: `whales/src/mcp_servers/gbif/server.py`
- Create: `whales/tests/unit/test_gbif_server.py`

Follow same pattern. Key tool: `search_whale_occurrences(species_name, latitude, longitude, radius_km, year)` querying `https://api.gbif.org/v1/occurrence/search` with `taxonKey=733` (Cetacea). Port 9005.

**Step 1: Implement and test, then commit**

```bash
git commit --signoff -m "feat: add GBIF whale occurrence MCP server"
```

---

### Task 8: Build IUCN Red List MCP server

**Files:**
- Create: `whales/src/mcp_servers/iucn/server.py`
- Create: `whales/tests/unit/test_iucn_server.py`

Key tool: `get_species_status(species_name)` querying IUCN API. Port 9006.

```bash
git commit --signoff -m "feat: add IUCN Red List conservation status MCP server"
```

---

### Task 9: Build Marine Cadastre (AIS mock data) MCP server

**Files:**
- Create: `whales/src/mcp_servers/marine_cadastre/server.py`
- Create: `whales/data/sample_ais_tracks.json`
- Create: `whales/tests/unit/test_marine_cadastre_server.py`

This server provides mock AIS vessel traffic data for the PoC. Key tools: `get_vessel_traffic(latitude, longitude, radius_km)`, `get_shipping_lane_density(bbox)`. Uses sample data from `data/sample_ais_tracks.json`. Port 9003.

Generate realistic sample AIS data covering major shipping lanes (US West Coast, US East Coast, English Channel).

```bash
git commit --signoff -m "feat: add Marine Cadastre AIS mock data MCP server"
```

---

### Task 10: Create MCP server startup script

**Files:**
- Create: `whales/scripts/start_mcp_servers.sh`

```bash
#!/usr/bin/env bash
# Start all MCP servers for Whale Agent
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "Starting Whale Agent MCP servers..."

python -m mcp_servers.noaa.server &
python -m mcp_servers.whale_alert.server &
python -m mcp_servers.marine_cadastre.server &
python -m mcp_servers.open_meteo.server &
python -m mcp_servers.gbif.server &
python -m mcp_servers.iucn.server &

echo "All 6 MCP servers started (ports 9001-9006)"
wait
```

```bash
chmod +x scripts/start_mcp_servers.sh
git add scripts/start_mcp_servers.sh
git commit --signoff -m "feat: add MCP server startup script"
```

---

## Phase 3: Custom Dynamic Tools

### Task 11: Build query_decomposer tool

**Files:**
- Create: `whales/src/whale_tools/query_decomposer.py`
- Create: `whales/tests/unit/test_query_decomposer.py`

Adapt MedExpert's `query_decomposer.py`. Replace `DOMAIN_AGENT_ROUTING` import to use `whale_common.constants`. Replace medical agents with whale agents. Keep the same DynamicTool pattern: class `QueryDecomposerTool(DynamicTool)` with `tool_name`, `tool_description`, `parameters_schema`, `_run_async_impl`. Keep LLM decomposition + keyword fallback. Update the LLM system prompt to route whale/marine questions.

Reference: `medexpert/src/lifesci_tools/query_decomposer.py`

```bash
git commit --signoff -m "feat: add query decomposer for whale domain routing"
```

---

### Task 12: Build memory_plane tool (adapt from MedExpert)

**Files:**
- Create: `whales/src/whale_tools/memory_plane.py`
- Create: `whales/tests/unit/test_memory_plane.py`

Copy MedExpert's `memory_plane.py` and adapt: rename namespaces from medical to whale domain ("evidence" → "evidence", "intermediate" → "intermediate", "citations" → "citations" — keep the same namespace names since they're generic). Change `cold_db_path` default to `data/whale_cold.db`.

Reference: `medexpert/src/lifesci_tools/memory_plane.py`

```bash
git commit --signoff -m "feat: add memory plane tool (Redis hot store + SQLite cold store)"
```

---

### Task 13: Build risk_scorer tool

**Files:**
- Create: `whales/src/whale_tools/risk_scorer.py`
- Create: `whales/tests/unit/test_risk_scorer.py`

**Step 1: Write the failing test**

```python
# whales/tests/unit/test_risk_scorer.py
import pytest

@pytest.mark.asyncio
async def test_risk_scorer_basic():
    from whale_tools.risk_scorer import RiskScorerTool
    tool = RiskScorerTool()
    result = await tool._run_async_impl(
        args={
            "latitude": 47.6,
            "longitude": -122.3,
            "month": 3,
            "whale_density": 0.7,
            "vessel_traffic_density": 0.5,
            "vessel_speed_knots": 15.0,
        },
        tool_context=None,
    )
    assert "collision_risk_score" in result
    assert 0.0 <= result["collision_risk_score"] <= 1.0
    assert "risk_level" in result
```

**Step 2: Implement**

```python
# whales/src/whale_tools/risk_scorer.py
"""Collision Risk Scorer — calculates whale-vessel collision probability.

Uses a weighted formula combining whale density, vessel traffic density,
vessel speed, and seasonal factors. Returns a 0-1 risk score with
human-readable risk level.
"""

import logging
from typing import Optional

from google.adk.tools import ToolContext
from google.genai import types as adk_types
from solace_agent_mesh.agent.tools.dynamic_tool import DynamicTool

log = logging.getLogger(__name__)

# Speed risk thresholds (knots)
_SPEED_BREAKPOINTS = [(10, 0.2), (14, 0.5), (18, 0.8), (25, 1.0)]

# Seasonal whale activity multipliers by month (1-indexed)
_SEASONAL_MULTIPLIERS = {
    1: 0.6, 2: 0.7, 3: 0.9, 4: 1.0, 5: 0.9, 6: 0.7,
    7: 0.5, 8: 0.4, 9: 0.5, 10: 0.7, 11: 0.8, 12: 0.7,
}


def _speed_risk(speed_knots: float) -> float:
    """Map vessel speed to risk factor (0-1)."""
    for threshold, risk in _SPEED_BREAKPOINTS:
        if speed_knots <= threshold:
            return risk
    return 1.0


class RiskScorerTool(DynamicTool):
    """Calculates collision probability for a given location and conditions."""

    @property
    def tool_name(self) -> str:
        return "risk_scorer"

    @property
    def tool_description(self) -> str:
        return (
            "Calculates whale-vessel collision risk score (0-1) for a given "
            "lat/lng based on whale density, vessel traffic, speed, and season."
        )

    @property
    def parameters_schema(self) -> adk_types.Schema:
        return adk_types.Schema(
            type=adk_types.Type.OBJECT,
            properties={
                "latitude": adk_types.Schema(type=adk_types.Type.NUMBER, description="Latitude"),
                "longitude": adk_types.Schema(type=adk_types.Type.NUMBER, description="Longitude"),
                "month": adk_types.Schema(type=adk_types.Type.INTEGER, description="Month (1-12)"),
                "whale_density": adk_types.Schema(type=adk_types.Type.NUMBER, description="Whale density (0-1)"),
                "vessel_traffic_density": adk_types.Schema(type=adk_types.Type.NUMBER, description="Vessel traffic density (0-1)"),
                "vessel_speed_knots": adk_types.Schema(type=adk_types.Type.NUMBER, description="Vessel speed in knots"),
            },
            required=["latitude", "longitude", "month", "whale_density", "vessel_traffic_density", "vessel_speed_knots"],
        )

    async def _run_async_impl(
        self, args: dict, tool_context: Optional[ToolContext] = None, credential: Optional[str] = None,
    ) -> dict:
        lat = args["latitude"]
        lng = args["longitude"]
        month = args["month"]
        whale_density = max(0.0, min(1.0, args["whale_density"]))
        traffic_density = max(0.0, min(1.0, args["vessel_traffic_density"]))
        speed = args["vessel_speed_knots"]

        seasonal = _SEASONAL_MULTIPLIERS.get(month, 0.5)
        speed_factor = _speed_risk(speed)

        # Weighted collision risk
        score = (
            0.35 * whale_density * seasonal
            + 0.25 * traffic_density
            + 0.25 * speed_factor
            + 0.15 * whale_density * traffic_density  # interaction term
        )
        score = round(max(0.0, min(1.0, score)), 3)

        if score >= 0.7:
            risk_level = "HIGH"
            recommendation = "Reduce speed to < 10 knots and consider route diversion"
        elif score >= 0.4:
            risk_level = "MODERATE"
            recommendation = "Reduce speed to < 14 knots and increase lookout vigilance"
        else:
            risk_level = "LOW"
            recommendation = "Continue with standard precautions"

        return {
            "latitude": lat,
            "longitude": lng,
            "month": month,
            "collision_risk_score": score,
            "risk_level": risk_level,
            "recommendation": recommendation,
            "factors": {
                "whale_density_contribution": round(0.35 * whale_density * seasonal, 3),
                "traffic_contribution": round(0.25 * traffic_density, 3),
                "speed_contribution": round(0.25 * speed_factor, 3),
                "interaction_contribution": round(0.15 * whale_density * traffic_density, 3),
            },
        }
```

**Step 3: Run tests, commit**

```bash
cd whales && pytest tests/unit/test_risk_scorer.py -v
git add src/whale_tools/risk_scorer.py tests/unit/test_risk_scorer.py
git commit --signoff -m "feat: add whale-vessel collision risk scorer tool"
```

---

### Task 14: Build route_calculator tool

**Files:**
- Create: `whales/src/whale_tools/route_calculator.py`
- Create: `whales/tests/unit/test_route_calculator.py`

Implements weighted A* pathfinding over an ocean grid. Avoids high-risk zones. Returns waypoints as GeoJSON LineString. Key method: `_run_async_impl(args)` takes `origin_lat`, `origin_lng`, `dest_lat`, `dest_lng`, `risk_grid` (list of `{lat, lng, risk_score}`). Returns `{"waypoints": [...], "total_distance_nm": float, "estimated_risk_score": float, "geojson": {...}}`.

```bash
git commit --signoff -m "feat: add route calculator with A* pathfinding"
```

---

### Task 15: Build map_renderer tool

**Files:**
- Create: `whales/src/whale_tools/map_renderer.py`
- Create: `whales/tests/unit/test_map_renderer.py`

Generates Deck.gl-compatible GeoJSON for the frontend. Takes agent outputs (risk scores, routes, sightings) and returns structured layer data. Key outputs: `risk_heatmap_layer` (H3 hexagons), `route_layer` (LineString), `sighting_markers_layer` (FeatureCollection of Points), `shipping_lanes_layer`.

```bash
git commit --signoff -m "feat: add map renderer for Deck.gl layer generation"
```

---

### Task 16: Build remaining tools (fuel_estimator, migration_model, habitat_mapper, traffic_density, incident_analyzer, report_generator, cold_store)

**Files:**
- Create: `whales/src/whale_tools/fuel_estimator.py`
- Create: `whales/src/whale_tools/migration_model.py`
- Create: `whales/src/whale_tools/habitat_mapper.py`
- Create: `whales/src/whale_tools/traffic_density.py`
- Create: `whales/src/whale_tools/incident_analyzer.py`
- Create: `whales/src/whale_tools/report_generator.py`
- Create: `whales/src/whale_tools/cold_store.py`

Each follows the DynamicTool pattern from Task 13. Implement with basic logic — the PoC doesn't need production-grade algorithms, just enough to demonstrate agent collaboration.

- **fuel_estimator**: Given route distance and speed changes, estimates fuel delta.
- **migration_model**: Returns whale density by species/region/month from GBIF occurrence patterns.
- **habitat_mapper**: Maps feeding/breeding hotspots from environmental data.
- **traffic_density**: Aggregates AIS sample data into density grids.
- **incident_analyzer**: Returns historical whale strike statistics (hardcoded sample data for PoC).
- **report_generator**: Synthesizes specialist findings into a structured route recommendation (LLM-powered, like MedExpert's).
- **cold_store**: SQLite cross-session learning (adapt from MedExpert's cold_store.py — replace medical tables with `session_outcomes`, `route_patterns`, `risk_calibrations`, `seasonal_strategies`).

```bash
git commit --signoff -m "feat: add remaining whale specialist tools"
```

---

## Phase 4: Agent Configuration (YAML)

### Task 17: Create all 11 agent YAML configs

**Files:**
- Create: `whales/configs/agents/orchestrator.yaml`
- Create: `whales/configs/agents/route_optimizer.yaml`
- Create: `whales/configs/agents/risk_assessor.yaml`
- Create: `whales/configs/agents/weather_analyst.yaml`
- Create: `whales/configs/agents/vessel_traffic_monitor.yaml`
- Create: `whales/configs/agents/whale_migration_tracker.yaml`
- Create: `whales/configs/agents/habitat_analyst.yaml`
- Create: `whales/configs/agents/species_identifier.yaml`
- Create: `whales/configs/agents/incident_analyst.yaml`
- Create: `whales/configs/agents/verifier.yaml`
- Create: `whales/configs/agents/reviser.yaml`

Follow the MedExpert YAML pattern exactly. Each agent config has:

```yaml
log:
  stdout_log_level: INFO
  log_file_level: INFO
  log_file: <agent_name>.log

!include ../shared_config.yaml

apps:
  - name: <agent_name>_app
    app_base_path: .
    app_module: solace_agent_mesh.agent.sac.app
    broker:
      <<: *broker_connection

    app_config:
      namespace: ${NAMESPACE}
      supports_streaming: true
      agent_name: "<AgentName>"
      display_name: "<Display Name>"
      model: *<model_tier>

      instruction: |
        <agent-specific prompt>

      tools:
        <tool definitions>

      session_service: *default_session_service
      artifact_service: *default_artifact_service
      max_llm_calls_per_task: <limit>

      agent_card:
        description: "<description>"
        defaultInputModes: ["text"]
        defaultOutputModes: ["text"]
        skills: [...]

      agent_card_publishing: { interval_seconds: 10 }
      agent_discovery: { enabled: true }
      inter_agent_communication:
        allow_list: <agents this one can talk to>
        request_timeout_seconds: 120
```

**Orchestrator** gets `max_llm_calls_per_task: 50`, `protocol_enforcement: true`, and its allow_list includes all 10 other agents. Specialists get `max_llm_calls_per_task: 15`.

**Tool assignment per agent:**

| Agent | MCP Tools | Dynamic Tools |
|-------|-----------|---------------|
| Orchestrator | — | query_decomposer, memory_plane, report_generator, map_renderer |
| Route Optimizer | — | route_calculator, fuel_estimator, memory_plane |
| Risk Assessor | marine_cadastre (9003) | risk_scorer, memory_plane |
| Weather Analyst | noaa (9001), open_meteo (9004) | memory_plane |
| Vessel Traffic Monitor | marine_cadastre (9003) | traffic_density, memory_plane |
| Whale Migration Tracker | gbif (9005) | migration_model, memory_plane |
| Habitat Analyst | noaa (9001), open_meteo (9004), gbif (9005) | habitat_mapper, memory_plane |
| Species Identifier | iucn (9006), gbif (9005) | memory_plane |
| Incident Analyst | — | incident_analyzer, memory_plane |
| Verifier | — | memory_plane (read_only: true) |
| Reviser | — | memory_plane, report_generator |

```bash
git add configs/agents/
git commit --signoff -m "feat: add all 11 agent YAML configurations"
```

---

### Task 18: Create gateway YAML config

**Files:**
- Create: `whales/configs/gateways/webui.yaml`

```yaml
# Whale Agent - Web UI Gateway Configuration

log:
  stdout_log_level: INFO
  log_file_level: INFO
  log_file: webui.log

!include ../shared_config.yaml

apps:
  - name: whale_agent_webui_app
    app_base_path: .
    app_module: solace_agent_mesh.gateway.http_sse.app
    broker:
      <<: *broker_connection

    app_config:
      namespace: ${NAMESPACE}
      session_secret_key: "${SESSION_SECRET_KEY}"

      artifact_service: *default_artifact_service
      session_service:
        type: "sql"
        database_url: "sqlite:///whale_agent_webui.db"
        default_behavior: "PERSISTENT"

      model: *general_model
      fastapi_host: 0.0.0.0
      fastapi_port: 8080
      cors_allowed_origins:
        - "http://localhost:3000"
        - "http://127.0.0.1:3000"
      cors_allow_credentials: true

      enable_embed_resolution: true
      sse_max_queue_size: 200

      system_purpose: >
        Whale Agent is an AI-powered maritime safety system that helps reduce
        whale-vessel collisions. It provides risk-assessed shipping routes,
        real-time whale sighting data, and dynamic risk maps. Ask about safe
        routes between ports, current whale activity, or collision risk for
        specific areas.

      response_format: >
        Responses should be formatted in Markdown. Use headers, bullet points,
        and bold text. Include risk scores, distance estimates, and species
        data when available. When providing route recommendations, include
        a summary of risk factors and fuel impact.

      frontend_welcome_message: "Welcome to Whale Agent! Ask me to plan a safe shipping route, check whale activity in an area, or assess collision risk for your voyage."
      frontend_bot_name: "Whale Agent"
      frontend_collect_feedback: true
      frontend_use_authorization: false

      background_tasks:
        default_timeout_ms: 3600000
```

```bash
git add configs/gateways/webui.yaml
git commit --signoff -m "feat: add web UI gateway configuration"
```

---

## Phase 5: Dev Scripts & Startup

### Task 19: Create dev.sh one-command setup

**Files:**
- Create: `whales/scripts/dev.sh`
- Create: `whales/scripts/start_agents.sh`

```bash
#!/usr/bin/env bash
# whales/scripts/dev.sh — One-command dev setup for Whale Agent
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Parse flags
SKIP_MCP=false
NO_FRONTEND=false
RESET=false
for arg in "$@"; do
  case $arg in
    --skip-mcp) SKIP_MCP=true ;;
    --no-frontend) NO_FRONTEND=true ;;
    --reset) RESET=true ;;
  esac
done

if [ "$RESET" = true ]; then
  echo "Resetting environment..."
  rm -rf .venv .env
  echo "Reset complete. Re-run without --reset."
  exit 0
fi

# Create venv if needed
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python -m venv .venv
fi

source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate

# Install deps
pip install -e ".[dev]" --quiet

# Create .env if missing
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "Created .env from template — fill in your API keys"
fi

# Source env vars
set -a && source .env && set +a

# Start MCP servers
if [ "$SKIP_MCP" = false ]; then
  echo "Starting MCP servers..."
  bash scripts/start_mcp_servers.sh &
  sleep 3
fi

# Start agents + gateway
echo "Starting agents and gateway..."
bash scripts/start_agents.sh &

# Start frontend
if [ "$NO_FRONTEND" = false ] && [ -d "client/webui/frontend" ]; then
  echo "Starting frontend dev server..."
  cd client/webui/frontend && npm run dev &
fi

echo ""
echo "Whale Agent is running!"
echo "  Gateway: http://localhost:8080"
echo "  Frontend: http://localhost:3000"
echo ""

wait
```

**start_agents.sh:**

```bash
#!/usr/bin/env bash
# Start all Whale Agent agents + gateway via sam run
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

CONFIG_FILES=""
for f in configs/agents/*.yaml; do
  CONFIG_FILES="$CONFIG_FILES $f"
done
CONFIG_FILES="$CONFIG_FILES configs/gateways/webui.yaml"

echo "Starting sam run with all configs..."
sam run $CONFIG_FILES
```

```bash
chmod +x scripts/dev.sh scripts/start_agents.sh
git add scripts/
git commit --signoff -m "feat: add dev.sh and startup scripts"
```

---

## Phase 6: Frontend — Chat + Dashboard

### Task 20: Fork MedExpert frontend and set up Deck.gl dependencies

**Files:**
- Copy: `client/webui/frontend/` from MedExpert
- Modify: `client/webui/frontend/package.json` — add Deck.gl deps

**Step 1: Copy MedExpert frontend**

```bash
cp -r /c/Users/2096955/Downloads/MedExpert/solace-agent-mesh/client whales/client
```

**Step 2: Add Deck.gl dependencies**

```bash
cd whales/client/webui/frontend
npm install @deck.gl/core @deck.gl/layers @deck.gl/geo-layers @deck.gl/react react-map-gl maplibre-gl
```

**Step 3: Commit**

```bash
git add client/
git commit --signoff -m "feat: fork MedExpert frontend and add Deck.gl dependencies"
```

---

### Task 21: Build MapView dashboard component

**Files:**
- Create: `whales/client/webui/frontend/src/components/Dashboard/MapView.tsx`
- Create: `whales/client/webui/frontend/src/components/Dashboard/index.ts`

```typescript
// whales/client/webui/frontend/src/components/Dashboard/MapView.tsx
import React, { useState, useCallback } from 'react';
import Map from 'react-map-gl/maplibre';
import DeckGL from '@deck.gl/react';
import { HeatmapLayer, ScatterplotLayer, PathLayer } from '@deck.gl/layers';
import 'maplibre-gl/dist/maplibre-gl.css';

const INITIAL_VIEW_STATE = {
  latitude: 37.8,
  longitude: -122.4,
  zoom: 4,
  pitch: 30,
  bearing: 0,
};

interface MapViewProps {
  riskData?: Array<{ lat: number; lng: number; risk: number }>;
  sightings?: Array<{ lat: number; lng: number; species: string; count: number }>;
  routes?: Array<{ path: [number, number][] }>;
  shippingLanes?: Array<{ path: [number, number][] }>;
}

export function MapView({ riskData = [], sightings = [], routes = [], shippingLanes = [] }: MapViewProps) {
  const [viewState, setViewState] = useState(INITIAL_VIEW_STATE);

  const layers = [
    // Risk heatmap
    new HeatmapLayer({
      id: 'risk-heatmap',
      data: riskData,
      getPosition: (d: any) => [d.lng, d.lat],
      getWeight: (d: any) => d.risk,
      radiusPixels: 60,
      intensity: 1,
      threshold: 0.1,
      colorRange: [
        [65, 182, 196],   // low risk (teal)
        [127, 205, 187],
        [199, 233, 180],
        [255, 255, 204],
        [254, 178, 76],
        [240, 59, 32],    // high risk (red)
      ],
    }),

    // Whale sightings
    new ScatterplotLayer({
      id: 'whale-sightings',
      data: sightings,
      getPosition: (d: any) => [d.lng, d.lat],
      getRadius: (d: any) => Math.max(d.count * 500, 1000),
      getFillColor: [0, 128, 255, 180],
      getLineColor: [0, 0, 0, 255],
      lineWidthMinPixels: 1,
      pickable: true,
    }),

    // Shipping lanes
    new PathLayer({
      id: 'shipping-lanes',
      data: shippingLanes,
      getPath: (d: any) => d.path,
      getColor: [128, 128, 128, 100],
      getWidth: 2000,
      widthMinPixels: 1,
    }),

    // Recommended route
    new PathLayer({
      id: 'recommended-route',
      data: routes,
      getPath: (d: any) => d.path,
      getColor: [0, 200, 83, 255],
      getWidth: 3000,
      widthMinPixels: 2,
    }),
  ];

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <DeckGL
        viewState={viewState}
        onViewStateChange={({ viewState: vs }: any) => setViewState(vs)}
        layers={layers}
        controller={true}
      >
        <Map
          mapStyle="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
        />
      </DeckGL>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add client/webui/frontend/src/components/Dashboard/
git commit --signoff -m "feat: add Deck.gl MapView dashboard component"
```

---

### Task 22: Build Sidebar component

**Files:**
- Create: `whales/client/webui/frontend/src/components/Dashboard/Sidebar.tsx`

Route input form (origin port, destination port, date), season/species filters, risk summary stats, active alerts panel. Communicates with the SAM gateway SSE endpoint.

```bash
git commit --signoff -m "feat: add dashboard sidebar with route input and risk summary"
```

---

### Task 23: Build remaining map layer components

**Files:**
- Create: `whales/client/webui/frontend/src/components/Dashboard/RiskHeatmapLayer.tsx`
- Create: `whales/client/webui/frontend/src/components/Dashboard/WhaleMarkerLayer.tsx`
- Create: `whales/client/webui/frontend/src/components/Dashboard/ShippingLaneLayer.tsx`
- Create: `whales/client/webui/frontend/src/components/Dashboard/RouteLayer.tsx`
- Create: `whales/client/webui/frontend/src/components/Dashboard/MigrationCorridorLayer.tsx`

Extract layer definitions from MapView into dedicated components with toggle controls.

```bash
git commit --signoff -m "feat: add individual map layer components with toggles"
```

---

### Task 24: Integrate Dashboard into App with tab navigation

**Files:**
- Modify: `whales/client/webui/frontend/src/App.tsx`

Add tab-based navigation (Chat | Dashboard). The chat view uses the existing SAM WebUI chat component. The dashboard view shows the MapView + Sidebar. Shared session state so routes planned in chat appear on the dashboard.

```bash
git commit --signoff -m "feat: add tab navigation between Chat and Dashboard views"
```

---

## Phase 7: Integration & Testing

### Task 25: Write integration test for orchestrator → specialist delegation

**Files:**
- Create: `whales/tests/integration/test_orchestrator_flow.py`

Test that the orchestrator correctly decomposes a query, delegates to specialists, collects results, synthesizes a route recommendation, and verifies it.

```bash
git commit --signoff -m "test: add orchestrator integration test"
```

---

### Task 26: Write end-to-end smoke test

**Files:**
- Create: `whales/tests/integration/test_e2e_smoke.py`

Start the full stack (MCP servers + agents + gateway), send a test query via HTTP, verify response contains risk score, route, and map data.

```bash
git commit --signoff -m "test: add end-to-end smoke test"
```

---

### Task 27: Run full test suite and fix any issues

```bash
cd whales
pytest tests/ -v --tb=short
ruff check src/ tests/
ruff format src/ tests/
```

Fix any failures. Commit.

```bash
git commit --signoff -m "fix: resolve test failures and lint issues"
```

---

## Phase 8: Documentation & Polish

### Task 28: Create CLAUDE.md

**Files:**
- Create: `whales/CLAUDE.md`

Document: project overview, build commands, architecture, agent roles, tool system, MCP servers, testing conventions, deployment. Follow the MedExpert CLAUDE.md structure.

```bash
git commit --signoff -m "docs: add CLAUDE.md project guide"
```

---

### Task 29: Final review and cleanup

Run the full stack manually. Verify:
1. Chat interface responds to "What's the safest route from Seattle to Anchorage in March?"
2. Dashboard shows risk heatmap, whale sightings, and route overlay
3. All 11 agents appear in the SAM gateway's agent discovery
4. MCP servers respond on ports 9001-9006

Fix any issues found. Final commit.

```bash
git commit --signoff -m "chore: final PoC cleanup and polish"
```
