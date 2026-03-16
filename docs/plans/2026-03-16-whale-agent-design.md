# Whale Agent — Design Document

**Date:** 2026-03-16
**Status:** Approved
**Project:** https://project-resilience.github.io/platform/projects/whale_agent.html

## Overview

An agentic proof-of-concept that reduces whale-vessel collisions by providing dynamic risk maps, optimized shipping routes, and real-time alerts. Built on the Solace Agent Mesh (SAM) framework, forked from the MedExpert application pattern.

**Delivery format:** PoC/demo with full agentic decision-making
**Target stakeholders:** Environmental organizations, shipping companies, ship captains, insurance companies
**UN SDGs:** Goal 14 (Life Below Water), Goal 09 (Industry, Innovation, Infrastructure)

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Framework | Solace Agent Mesh (SAM) | Proven multi-agent orchestration, YAML-based agent config, A2A protocol, MCP tool support |
| Approach | Full SAM fork of MedExpert | Fastest path — reuse orchestrator protocol, gateway, tool registry, cold store learning |
| Map visualization | Deck.gl + MapLibre GL | Free, open-source, best-in-class geospatial visualization |
| LLM provider | Configurable via LiteLLM | Temperature-tiered model anchors in shared_config.yaml, swap providers without code changes |
| Data sources | Public APIs + mocked AIS | Real data for credibility, mocked vessel tracks where live data unavailable |
| Demo format | Chat interface + live map dashboard | Chat showcases agentic reasoning, dashboard shows real-time risk visualization |

---

## Section 1: Agent Architecture

### Orchestrator — "Whale Route Coordinator"

Adapts MedExpert's 7-step protocol for marine decision-making:

1. **SEED**: Load learned routing strategies from past sessions
2. **PLAN**: Decompose query via `query_decomposer` (routes to whale vs. shipping vs. environment specialists)
3. **DELEGATE**: Call relevant specialists in parallel
4. **COLLECT**: Gather risk data, validate coverage
5. **SYNTHESIZE**: Generate risk-assessed route recommendation with map data
6. **VERIFY+REVISE**: Fact-check risk levels against data sources
7. **PERSIST**: Save session signals to cold store

### Route-Focused Specialists (4)

| Agent | Role | Key Tools |
|-------|------|-----------|
| Route Optimizer | Computes safest/most efficient routes avoiding high-risk zones | route_calculator, fuel_estimator |
| Risk Assessor | Scores collision probability for route segments | risk_scorer, historical_incidents |
| Weather Analyst | Evaluates ocean/atmospheric conditions affecting whale presence | weather_fetcher, current_analyzer |
| Vessel Traffic Monitor | Analyzes shipping lane density and AIS data | ais_tracker, traffic_density |

### Whale-Focused Specialists (4)

| Agent | Role | Key Tools |
|-------|------|-----------|
| Whale Migration Tracker | Tracks seasonal migration patterns by species | migration_model, species_range |
| Habitat Analyst | Maps krill distribution, feeding grounds, breeding areas | habitat_mapper, krill_density |
| Species Identifier | Identifies at-risk species for a given region/season | species_lookup, conservation_status |
| Incident Analyst | Analyzes historical whale strike data and patterns | incident_db, trend_analyzer |

### Support Agents (2)

| Agent | Role |
|-------|------|
| Verifier | Cross-checks risk assessments against source data |
| Reviser | Corrects inaccuracies flagged by the verifier |

**Total: 11 agents** (1 orchestrator + 8 specialists + 2 support)

---

## Section 2: MCP Servers (Data Sources)

6 MCP servers wrapping public APIs, following MedExpert's FastMCP pattern:

| MCP Server | Data Source | What It Provides |
|------------|-------------|------------------|
| **noaa** | NOAA APIs (weather.gov, NDBC buoys) | Sea surface temperature, wave height, wind, ocean currents, forecasts |
| **whale-alert** | Whale Alert API (whalealert.org) | Real-time whale sighting reports with species, location, timestamp |
| **marine-cadastre** | Marine Cadastre / AIS data (marinecadastre.gov) | Historical vessel traffic density, shipping lanes, AIS positions |
| **open-meteo** | Open-Meteo Marine API (free, no key) | Marine weather forecasts, wave models, ocean temperature grids |
| **gbif** | GBIF Occurrence API (gbif.org) | Whale species occurrence records, geographic distributions, seasonal patterns |
| **iucn** | IUCN Red List API | Conservation status, population trends, threat assessments per species |

Each server: built with `fastmcp`, shared HTTP helpers with retry/rate limiting/circuit breakers, own port (9001-9006), auto-discovered by agents via YAML config.

**Mocked for PoC:**
- Real-time AIS vessel positions — generate realistic sample vessel tracks
- HubOcean — covered by NOAA + Open-Meteo ocean data

---

## Section 3: Custom Tools (Dynamic Tools)

### Core Decision Tools

| Tool | Purpose | Used By |
|------|---------|---------|
| `query_decomposer` | Breaks user queries into sub-tasks, routes to whale vs. route specialists | Orchestrator |
| `risk_scorer` | Calculates collision probability for a lat/lng grid cell given whale density + vessel traffic + season | Risk Assessor |
| `route_calculator` | Computes waypoint-based routes between ports, avoiding high-risk zones using weighted A* pathfinding | Route Optimizer |
| `fuel_estimator` | Estimates fuel impact of route diversions and speed reductions | Route Optimizer |

### Data Processing Tools

| Tool | Purpose | Used By |
|------|---------|---------|
| `migration_model` | Returns expected whale density by species/region/month from historical occurrence data | Migration Tracker |
| `habitat_mapper` | Maps feeding/breeding hotspots from GBIF + NOAA environmental data | Habitat Analyst |
| `traffic_density` | Aggregates AIS data into shipping lane density heatmaps | Vessel Traffic Monitor |
| `incident_analyzer` | Queries and summarizes historical whale strike records | Incident Analyst |

### Shared Infrastructure Tools (adapted from MedExpert)

| Tool | Purpose |
|------|---------|
| `memory_plane` | Redis/dict-backed shared state during a session (risk maps, route candidates, whale data) |
| `cold_store` | SQLite cross-session learning (successful route patterns, seasonal risk calibrations) |
| `report_generator` | Synthesizes specialist findings into a structured route recommendation with risk summary |
| `map_renderer` | Generates Deck.gl-compatible GeoJSON layers (risk heatmap, route polylines, whale sighting markers) |

---

## Section 4: Frontend & Dashboard

### Chat View (adapted from MedExpert)
- Conversational interface for route planning queries
- Streaming agent responses via SSE
- Inline map previews when agents produce route recommendations

### Dashboard View (new)
- Full-screen Deck.gl + MapLibre GL map with layer toggles:
  - **Risk Heatmap Layer** — Color-coded collision probability grid (red/yellow/green)
  - **Whale Sightings Layer** — Markers from Whale Alert data, filterable by species
  - **Shipping Lanes Layer** — AIS traffic density visualization
  - **Route Layer** — Animated arc showing recommended route vs. standard route
  - **Migration Corridors Layer** — Seasonal whale migration paths
- Sidebar panel with:
  - Route input (origin port, destination port, date)
  - Season/species filters
  - Risk summary stats (collision probability %, fuel impact, delay estimate)
  - Active alerts (speed reduction zones, course adjustment recommendations)
- Real-time updates via SAM gateway SSE stream

### Navigation
- Tab-based switching between Chat and Dashboard
- Shared session — routes planned in chat appear on dashboard, and vice versa

### Tech
- React + Vite (existing MedExpert setup)
- `@deck.gl/react` + `react-map-gl` + `maplibre-gl`
- No additional backend — everything flows through SAM gateway

---

## Section 5: Project Structure

```
whales/
├── configs/
│   ├── agents/
│   │   ├── orchestrator.yaml
│   │   ├── route_optimizer.yaml
│   │   ├── risk_assessor.yaml
│   │   ├── weather_analyst.yaml
│   │   ├── vessel_traffic_monitor.yaml
│   │   ├── whale_migration_tracker.yaml
│   │   ├── habitat_analyst.yaml
│   │   ├── species_identifier.yaml
│   │   ├── incident_analyst.yaml
│   │   ├── verifier.yaml
│   │   └── reviser.yaml
│   ├── gateways/
│   │   └── webui.yaml
│   └── shared_config.yaml
├── src/
│   ├── whale_tools/
│   │   ├── query_decomposer.py
│   │   ├── risk_scorer.py
│   │   ├── route_calculator.py
│   │   ├── fuel_estimator.py
│   │   ├── migration_model.py
│   │   ├── habitat_mapper.py
│   │   ├── traffic_density.py
│   │   ├── incident_analyzer.py
│   │   ├── memory_plane.py
│   │   ├── cold_store.py
│   │   ├── report_generator.py
│   │   └── map_renderer.py
│   ├── mcp_servers/
│   │   ├── noaa/server.py
│   │   ├── whale_alert/server.py
│   │   ├── marine_cadastre/server.py
│   │   ├── open_meteo/server.py
│   │   ├── gbif/server.py
│   │   └── iucn/server.py
│   └── whale_common/
│       ├── constants.py
│       └── geo_utils.py
├── client/webui/frontend/
│   └── src/
│       ├── components/
│       │   ├── Chat/
│       │   └── Dashboard/
│       │       ├── MapView.tsx
│       │       ├── RiskHeatmapLayer.tsx
│       │       ├── WhaleMarkerLayer.tsx
│       │       ├── ShippingLaneLayer.tsx
│       │       ├── RouteLayer.tsx
│       │       ├── MigrationCorridorLayer.tsx
│       │       └── Sidebar.tsx
│       └── App.tsx
├── scripts/
│   ├── dev.sh
│   ├── start_mcp_servers.sh
│   └── start_agents.sh
├── data/
│   ├── sample_ais_tracks.json
│   └── whale_cold.db
├── pyproject.toml
├── .env.example
└── README.md
```

### Deployment (PoC)
- **Local dev**: `bash scripts/dev.sh` — starts MCP servers, all agents via `sam run` (DevBroker), and Vite frontend
- **Single container**: One Docker image runs everything (DevBroker, 11 agents, 6 MCP servers, gateway)

### What We Fork vs. Build New

| From MedExpert (adapt) | Build New |
|------------------------|-----------|
| Orchestrator protocol structure | 8 whale specialist agent configs |
| Verifier + Reviser agents | 12 custom whale tools |
| Memory plane + cold store tools | 6 MCP servers |
| Gateway config | Dashboard frontend (Deck.gl) |
| Dev/deploy scripts | Route calculation logic |
| React chat UI shell | GeoJSON map renderer |
