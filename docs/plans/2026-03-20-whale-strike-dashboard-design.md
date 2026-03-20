# Whale Strike Mitigation Dashboard — Design Document

**Date:** 2026-03-20
**Status:** Approved
**Approach:** A — Skin existing Crucix Jarvis dashboard

---

## Summary

Repurpose the Crucix OSINT intelligence dashboard (crucix/) into a whale strike mitigation terminal. Strip all OSINT-specific panels (conflicts, fires, radiation, flights, economic indicators, social sentiment) and replace them with whale-specific data: NOAA cetacean distribution, migration corridors, shipping lane overlays, and LLM-powered route recommendations via Gemini.

## Backend Changes

### 1. LLM Configuration

Wire whales project Gemini keys into `crucix/.env`:

- `LLM_PROVIDER=gemini`
- `LLM_API_KEY=<GEMINI_API_KEY_1 from whales .env>`
- `LLM_MODEL=<GEMINI_MODEL from whales .env>`

Crucix's existing `lib/llm/gemini.mjs` handles the Gemini API — no changes needed to the LLM provider code.

### 2. New Data Source: `apis/sources/whales.mjs`

Primary data source for the dashboard. Returns:

- **NOAA cetacean data** — whale sighting/distribution from NOAA public APIs, species distribution, seasonal patterns, protected areas (Seasonal Management Areas, Dynamic Management Areas)
- **Migration corridors** — hardcoded known routes:
  - North Atlantic right whales (US East Coast, calving: Nov-Apr, feeding: May-Oct)
  - Blue whales (US West Coast, Jun-Nov)
  - Humpback whales (Pacific & Atlantic, seasonal)
  - Gray whales (Eastern Pacific, Dec-May southbound, Mar-Jun northbound)
  - Southern right whales (Southern Ocean, Jun-Oct calving)
- **Major shipping lanes** — global lanes that intersect whale habitat, with traffic density estimates
- **Historical strike data** — NOAA ship strike database (publicly available, aggregated stats)

### 3. LLM Risk Scoring (Gemini)

During each sweep cycle, Gemini receives current whale distribution + shipping lane data and produces:

- **Risk scores per zone** (1-10 scale)
- **Route recommendations** — specific adjustments with trade-off analysis:
  - Affected shipping lane
  - Recommended shift (distance, direction)
  - Risk reduction percentage
  - Cost impact (distance delta, fuel estimate)
  - Species being protected
  - Valid date range
- **Seasonal context** — calving season awareness, feeding aggregation, migration timing

### 4. Stripped Data Sources

Remove from sweep cycle:
- ACLED (conflicts)
- FIRMS (fires)
- Safecast (radiation)
- ADS-B/OpenSky (flights)
- FRED/BLS/EIA (economic)
- Reddit/Bluesky/Telegram (social)
- Patents, Space, Sanctions, WHO, GDELT, Treasury, USASpending, KiwiSDR, Comtrade, EPA

Keep and repurpose:
- `ships.mjs` — AIS chokepoints repurposed for shipping lane awareness
- `noaa.mjs` — repurposed for ocean/whale-relevant weather data
- New `whales.mjs` — primary whale data source

### 5. Synthesizer Changes (`dashboard/inject.mjs`)

Replace `synthesize()` to produce whale-specific dashboard data:
- `riskZones[]` — geo-polygons with risk scores, species, vessel density
- `migrationCorridors[]` — active corridors with species, direction, season
- `recommendations[]` — LLM-generated route adjustments
- `speciesStatus[]` — per-species activity (migrating/calving/feeding), sighting counts
- `protectedAreas[]` — active SMAs/DMAs with boundaries
- `shippingLanes[]` — major lanes with whale-intersection risk
- `metrics` — aggregate numbers for the metrics panel

## Frontend Changes

### Layout (3-column grid, same as current Jarvis)

#### Topbar
- Rebrand: "WHALE STRIKE MITIGATION TERMINAL"
- Regime chip: current global risk level ("HIGH RISK — CALVING SEASON" / "MODERATE" / "LOW")
- Region buttons: GLOBAL | N. ATLANTIC | N. PACIFIC | S. PACIFIC | INDIAN | SOUTHERN

#### Left Rail — Whale Activity
- **Species tracker**: monitored species list with activity status (migrating/calving/feeding), recent sighting count, risk dot (green/amber/red)
- **Migration status**: current season indicator, active corridors
- **Protected zones**: active SMAs/DMAs with status

#### Center — Map (hero)
- Keep D3 flat map + Globe.GL 3D toggle
- Overlay layers:
  - Whale migration corridors (animated dashed blue lines)
  - Shipping lanes (solid gray lines)
  - Risk zones (red/amber/green shaded polygons)
  - NOAA protected areas (hatched boundaries)
- Interactive popups: click risk zone for species, vessel density, risk score, recommended action
- Updated legend for whale symbology

#### Right Rail — Route Recommendations
- **Active recommendations**: LLM-generated route adjustments showing affected lane, recommended shift, risk reduction %, cost impact, species protected, valid dates
- **Recommendation status**: new / acknowledged / implemented
- **Seasonal briefing**: Gemini-generated monthly whale activity summary

#### Lower Panel Row
- **Risk metrics grid**: active risk zones, species in migration, vessels in risk areas, historical monthly strike average vs current, recommendation compliance rate
- **Source status**: NOAA, AIS, Gemini health indicators

### Styling
- Keep Jarvis dark aesthetic (perfect for maritime ops terminal)
- Color palette shifts:
  - Whale corridors: `#4fc3f7` (ocean blue)
  - Risk zones: existing `--danger` (red), `--warn` (amber), `--accent` (green)
  - Shipping lanes: `rgba(255,255,255,0.15)` (subtle gray)
  - Protected areas: `#b388ff` (purple, hatched)
- Boot sequence rebranded for whale strike terminal

## Files Changed

| File | Action |
|------|--------|
| `crucix/.env` | Configure LLM_PROVIDER, LLM_API_KEY, LLM_MODEL |
| `crucix/apis/sources/whales.mjs` | **New** — whale data source |
| `crucix/apis/briefing.mjs` | Strip OSINT sources, wire in whales.mjs |
| `crucix/dashboard/inject.mjs` | Replace synthesize() for whale data |
| `crucix/dashboard/public/jarvis.html` | Repurpose all panels for whale strike UI |
| `crucix/crucix.config.mjs` | Add whale-specific config options |
| `crucix/server.mjs` | Update Telegram/Discord commands for whale context |

## Out of Scope

- Real-time AIS WebSocket integration (future enhancement)
- Whale Alert API integration (not selected)
- User authentication / multi-tenant
- Mobile-specific responsive layout
- Historical trend charts / time-series analysis
