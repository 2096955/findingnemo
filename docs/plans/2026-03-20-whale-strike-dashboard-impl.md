# Whale Strike Mitigation Dashboard — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Repurpose the Crucix OSINT dashboard into a whale strike mitigation terminal with an interactive **voyage planner** — user inputs origin/destination (e.g., Tokyo to London) and gets a Gemini-generated whale-safe, conflict-aware sea route drawn on the map with trade-off analysis.

**Architecture:** Skin the existing Crucix Jarvis dashboard (Approach A). Keep the Node.js server, sweep cycle, SSE, delta engine, and D3/Globe.GL map infrastructure. Replace OSINT panels with whale-specific equivalents + voyage planner UI. Re-enable ACLED conflict data for danger zone avoidance. LLM (Gemini) generates both route recommendations and dynamic voyage routes.

**Tech Stack:** Node.js 22+, Express, D3.js/TopoJSON (flat map), Globe.GL/Three.js (3D globe), Gemini API (via existing `lib/llm/gemini.mjs`), NOAA public APIs, ACLED conflict data, SSE for live updates.

---

## Task 1: Wire Gemini LLM into Crucix .env

**Files:**
- Modify: `crucix/.env`

**Step 1: Read the Gemini key from whales .env**

Run: `grep '^GEMINI_API_KEY_1=' ../../.env | head -1`

(We need the actual key value — it's GEMINI_API_KEY_1 from the whales root .env)

**Step 2: Configure crucix/.env**

Set these three values in `crucix/.env`:

```
LLM_PROVIDER=gemini
LLM_API_KEY=<value from GEMINI_API_KEY_1>
LLM_MODEL=gemini-2.0-flash
```

The model should match `GEMINI_MODEL` from the whales `.env` (currently `gemini-2.0-flash`).

**Step 3: Verify LLM starts**

Run: `cd crucix && node -e "import('./crucix.config.mjs').then(c => console.log('LLM:', c.default.llm.provider, c.default.llm.model))"`

Expected: `LLM: gemini gemini-2.0-flash`

**Step 4: Commit**

```bash
git add crucix/.env
git commit -m "feat: wire Gemini LLM keys into Crucix config"
```

---

## Task 2: Create whale data source (`apis/sources/whales.mjs`)

**Files:**
- Create: `crucix/apis/sources/whales.mjs`
- Reference: `crucix/apis/sources/ships.mjs` (for pattern), `crucix/apis/sources/noaa.mjs` (for NOAA fetch pattern)

**Step 1: Write the whale data source**

Create `crucix/apis/sources/whales.mjs` with:

```javascript
// Whale Strike Mitigation — NOAA cetacean data + migration corridors + shipping lanes
// Primary data source for the whale strike dashboard

import { safeFetch } from '../utils/fetch.mjs';

// === Known whale migration corridors ===
const MIGRATION_CORRIDORS = [
  {
    id: 'narw-east-coast',
    species: 'North Atlantic Right Whale',
    scientificName: 'Eubalaena glacialis',
    status: 'Critically Endangered',
    route: [
      { lat: 30.5, lon: -80.5, label: 'Calving Grounds (FL/GA)' },
      { lat: 35.0, lon: -75.0, label: 'Mid-Atlantic Transit' },
      { lat: 40.5, lon: -70.0, label: 'Cape Cod Feeding' },
      { lat: 42.5, lon: -66.0, label: 'Bay of Fundy' },
      { lat: 47.0, lon: -60.0, label: 'Gulf of St. Lawrence' },
    ],
    calvingSeason: { start: 11, end: 4 }, // Nov-Apr
    feedingSeason: { start: 5, end: 10 }, // May-Oct
    peakRiskMonths: [1, 2, 3, 4, 11, 12],
    estimatedPopulation: 350,
  },
  {
    id: 'blue-west-coast',
    species: 'Blue Whale',
    scientificName: 'Balaenoptera musculus',
    status: 'Endangered',
    route: [
      { lat: 20.0, lon: -110.0, label: 'Baja California (Winter)' },
      { lat: 28.0, lon: -118.0, label: 'Southern California Bight' },
      { lat: 34.0, lon: -120.5, label: 'Santa Barbara Channel' },
      { lat: 37.5, lon: -123.0, label: 'Gulf of the Farallones' },
      { lat: 42.0, lon: -125.0, label: 'Oregon Coast' },
      { lat: 48.0, lon: -126.0, label: 'Vancouver Island' },
    ],
    calvingSeason: null,
    feedingSeason: { start: 6, end: 11 }, // Jun-Nov
    peakRiskMonths: [6, 7, 8, 9, 10],
    estimatedPopulation: 2500,
  },
  {
    id: 'humpback-atlantic',
    species: 'Humpback Whale (N. Atlantic)',
    scientificName: 'Megaptera novaeangliae',
    status: 'Least Concern',
    route: [
      { lat: 19.0, lon: -69.0, label: 'Caribbean Breeding' },
      { lat: 28.0, lon: -72.0, label: 'Bahamas Transit' },
      { lat: 38.0, lon: -73.0, label: 'Mid-Atlantic' },
      { lat: 42.0, lon: -68.0, label: 'Stellwagen Bank' },
      { lat: 48.0, lon: -56.0, label: 'Newfoundland Feeding' },
      { lat: 64.0, lon: -22.0, label: 'Iceland Feeding' },
    ],
    calvingSeason: { start: 1, end: 3 },
    feedingSeason: { start: 5, end: 10 },
    peakRiskMonths: [4, 5, 6, 10, 11],
    estimatedPopulation: 12000,
  },
  {
    id: 'gray-eastern-pacific',
    species: 'Gray Whale',
    scientificName: 'Eschrichtius robustus',
    status: 'Least Concern',
    route: [
      { lat: 23.0, lon: -110.0, label: 'Baja Calving Lagoons' },
      { lat: 33.0, lon: -118.0, label: 'Southern California' },
      { lat: 38.0, lon: -123.5, label: 'Central California' },
      { lat: 46.0, lon: -124.5, label: 'Oregon/Washington' },
      { lat: 58.0, lon: -155.0, label: 'Alaska Feeding' },
      { lat: 65.0, lon: -170.0, label: 'Bering Sea' },
    ],
    calvingSeason: { start: 12, end: 2 },
    feedingSeason: { start: 5, end: 10 },
    peakRiskMonths: [3, 4, 5, 11, 12],
    estimatedPopulation: 14500,
  },
  {
    id: 'southern-right',
    species: 'Southern Right Whale',
    scientificName: 'Eubalaena australis',
    status: 'Least Concern',
    route: [
      { lat: -34.0, lon: 18.5, label: 'South Africa Coast' },
      { lat: -38.5, lon: 145.0, label: 'SE Australia' },
      { lat: -42.0, lon: -65.0, label: 'Patagonia' },
      { lat: -46.0, lon: 168.0, label: 'New Zealand' },
      { lat: -55.0, lon: -40.0, label: 'Southern Ocean Feeding' },
    ],
    calvingSeason: { start: 6, end: 10 },
    feedingSeason: { start: 11, end: 4 },
    peakRiskMonths: [6, 7, 8, 9],
    estimatedPopulation: 15000,
  },
  {
    id: 'humpback-pacific',
    species: 'Humpback Whale (N. Pacific)',
    scientificName: 'Megaptera novaeangliae',
    status: 'Least Concern',
    route: [
      { lat: 20.5, lon: -156.5, label: 'Hawaii Breeding' },
      { lat: 35.0, lon: -140.0, label: 'Pacific Transit' },
      { lat: 48.0, lon: -125.0, label: 'Pacific Northwest' },
      { lat: 57.0, lon: -136.0, label: 'SE Alaska Feeding' },
      { lat: 60.0, lon: -150.0, label: 'Gulf of Alaska' },
    ],
    calvingSeason: { start: 12, end: 3 },
    feedingSeason: { start: 5, end: 11 },
    peakRiskMonths: [4, 5, 11, 12],
    estimatedPopulation: 22000,
  },
];

// === Major shipping lanes that intersect whale habitat ===
const SHIPPING_LANES = [
  {
    id: 'us-east-coast-tsz',
    name: 'US East Coast Traffic Separation Zone',
    risk: 'critical',
    intersectedSpecies: ['North Atlantic Right Whale', 'Humpback Whale (N. Atlantic)'],
    segments: [
      { from: { lat: 30.0, lon: -81.0 }, to: { lat: 36.0, lon: -75.5 } },
      { from: { lat: 36.0, lon: -75.5 }, to: { lat: 40.5, lon: -73.5 } },
      { from: { lat: 40.5, lon: -73.5 }, to: { lat: 42.3, lon: -70.0 } },
    ],
    vesselDensity: 'very-high',
  },
  {
    id: 'santa-barbara-channel',
    name: 'Santa Barbara Channel TSS',
    risk: 'high',
    intersectedSpecies: ['Blue Whale', 'Humpback Whale (N. Pacific)', 'Gray Whale'],
    segments: [
      { from: { lat: 33.8, lon: -119.8 }, to: { lat: 34.2, lon: -119.3 } },
      { from: { lat: 34.2, lon: -119.3 }, to: { lat: 34.0, lon: -118.5 } },
    ],
    vesselDensity: 'high',
  },
  {
    id: 'sf-approach',
    name: 'San Francisco Approach',
    risk: 'high',
    intersectedSpecies: ['Blue Whale', 'Gray Whale', 'Humpback Whale (N. Pacific)'],
    segments: [
      { from: { lat: 37.5, lon: -123.5 }, to: { lat: 37.8, lon: -122.5 } },
    ],
    vesselDensity: 'high',
  },
  {
    id: 'boston-approach',
    name: 'Boston Traffic Separation Scheme',
    risk: 'critical',
    intersectedSpecies: ['North Atlantic Right Whale', 'Humpback Whale (N. Atlantic)'],
    segments: [
      { from: { lat: 42.0, lon: -70.5 }, to: { lat: 42.4, lon: -70.8 } },
      { from: { lat: 42.4, lon: -70.8 }, to: { lat: 42.5, lon: -70.2 } },
    ],
    vesselDensity: 'very-high',
  },
  {
    id: 'cape-good-hope',
    name: 'Cape of Good Hope Route',
    risk: 'moderate',
    intersectedSpecies: ['Southern Right Whale'],
    segments: [
      { from: { lat: -34.0, lon: 17.0 }, to: { lat: -34.5, lon: 18.5 } },
      { from: { lat: -34.5, lon: 18.5 }, to: { lat: -33.5, lon: 26.0 } },
    ],
    vesselDensity: 'moderate',
  },
  {
    id: 'panama-pacific-approach',
    name: 'Panama Canal Pacific Approach',
    risk: 'moderate',
    intersectedSpecies: ['Humpback Whale (N. Pacific)'],
    segments: [
      { from: { lat: 8.0, lon: -80.0 }, to: { lat: 9.0, lon: -79.5 } },
    ],
    vesselDensity: 'high',
  },
  {
    id: 'hawaii-lanes',
    name: 'Hawaii Inter-Island / Great Circle Routes',
    risk: 'high',
    intersectedSpecies: ['Humpback Whale (N. Pacific)'],
    segments: [
      { from: { lat: 20.0, lon: -157.0 }, to: { lat: 21.5, lon: -158.5 } },
      { from: { lat: 21.0, lon: -157.5 }, to: { lat: 35.0, lon: -140.0 } },
    ],
    vesselDensity: 'moderate',
  },
  {
    id: 'strait-of-gibraltar-med',
    name: 'Strait of Gibraltar / Mediterranean Approach',
    risk: 'moderate',
    intersectedSpecies: ['Sperm Whale', 'Fin Whale'],
    segments: [
      { from: { lat: 35.9, lon: -5.8 }, to: { lat: 36.1, lon: -5.3 } },
      { from: { lat: 36.1, lon: -5.3 }, to: { lat: 37.0, lon: -1.0 } },
    ],
    vesselDensity: 'very-high',
  },
];

// === Known protected areas (Seasonal Management Areas + Dynamic Management Areas) ===
const PROTECTED_AREAS = [
  { id: 'sma-southeast', name: 'Southeast US SMA', lat: 31.0, lon: -80.5, radiusKm: 40, season: { start: 11, end: 4 }, species: 'North Atlantic Right Whale', type: 'SMA' },
  { id: 'sma-mid-atlantic', name: 'Mid-Atlantic SMA', lat: 37.0, lon: -75.5, radiusKm: 35, season: { start: 11, end: 4 }, species: 'North Atlantic Right Whale', type: 'SMA' },
  { id: 'sma-great-south-channel', name: 'Great South Channel SMA', lat: 41.0, lon: -69.0, radiusKm: 50, season: { start: 4, end: 7 }, species: 'North Atlantic Right Whale', type: 'SMA' },
  { id: 'sma-cape-cod-bay', name: 'Cape Cod Bay SMA', lat: 41.8, lon: -70.2, radiusKm: 30, season: { start: 1, end: 5 }, species: 'North Atlantic Right Whale', type: 'SMA' },
  { id: 'sma-race-point', name: 'Race Point SMA', lat: 42.1, lon: -70.3, radiusKm: 20, season: { start: 3, end: 4 }, species: 'North Atlantic Right Whale', type: 'SMA' },
  { id: 'sanctuary-stellwagen', name: 'Stellwagen Bank NMS', lat: 42.3, lon: -70.3, radiusKm: 25, season: null, species: 'Humpback Whale', type: 'Sanctuary' },
  { id: 'sanctuary-channel-islands', name: 'Channel Islands NMS', lat: 34.0, lon: -119.5, radiusKm: 30, season: null, species: 'Blue Whale', type: 'Sanctuary' },
  { id: 'sanctuary-monterey', name: 'Monterey Bay NMS', lat: 36.8, lon: -122.0, radiusKm: 40, season: null, species: 'Blue Whale', type: 'Sanctuary' },
  { id: 'sanctuary-farallones', name: 'Greater Farallones NMS', lat: 37.9, lon: -123.2, radiusKm: 35, season: null, species: 'Humpback Whale', type: 'Sanctuary' },
  { id: 'sanctuary-hawaii', name: 'Hawaiian Islands Humpback NMS', lat: 20.7, lon: -156.5, radiusKm: 50, season: { start: 11, end: 5 }, species: 'Humpback Whale', type: 'Sanctuary' },
];

// === Historical strike data (aggregated from NOAA ship strike database) ===
const HISTORICAL_STRIKES = {
  annualAverage: 20,
  peakMonths: [4, 5, 6, 10, 11],
  topSpecies: [
    { species: 'North Atlantic Right Whale', avgPerYear: 4.2, lethalityRate: 0.44 },
    { species: 'Humpback Whale', avgPerYear: 5.1, lethalityRate: 0.25 },
    { species: 'Fin Whale', avgPerYear: 3.8, lethalityRate: 0.38 },
    { species: 'Blue Whale', avgPerYear: 1.5, lethalityRate: 0.35 },
    { species: 'Gray Whale', avgPerYear: 2.4, lethalityRate: 0.20 },
  ],
  topLocations: [
    { name: 'US East Coast', lat: 38.0, lon: -74.0, strikesPerYear: 8.5 },
    { name: 'US West Coast', lat: 36.0, lon: -122.0, strikesPerYear: 4.2 },
    { name: 'Hawaii', lat: 20.5, lon: -156.5, strikesPerYear: 1.8 },
    { name: 'Mediterranean', lat: 38.0, lon: 5.0, strikesPerYear: 2.1 },
    { name: 'South Africa', lat: -34.0, lon: 18.5, strikesPerYear: 1.2 },
  ],
};

// === Utility: determine current season activity per corridor ===
function getCorridorActivity(corridor) {
  const month = new Date().getMonth() + 1;
  const inCalving = corridor.calvingSeason &&
    (corridor.calvingSeason.start <= corridor.calvingSeason.end
      ? month >= corridor.calvingSeason.start && month <= corridor.calvingSeason.end
      : month >= corridor.calvingSeason.start || month <= corridor.calvingSeason.end);
  const inFeeding = corridor.feedingSeason &&
    (corridor.feedingSeason.start <= corridor.feedingSeason.end
      ? month >= corridor.feedingSeason.start && month <= corridor.feedingSeason.end
      : month >= corridor.feedingSeason.start || month <= corridor.feedingSeason.end);
  const peakRisk = corridor.peakRiskMonths.includes(month);

  let activity = 'low';
  if (inCalving) activity = 'calving';
  else if (inFeeding) activity = 'feeding';
  else if (peakRisk) activity = 'migrating';

  return { activity, inCalving, inFeeding, peakRisk };
}

function isAreaActive(area) {
  if (!area.season) return true; // year-round sanctuary
  const month = new Date().getMonth() + 1;
  const { start, end } = area.season;
  return start <= end
    ? month >= start && month <= end
    : month >= start || month <= end;
}

// === NOAA cetacean sighting data (public API) ===
async function fetchNOAACetacean() {
  try {
    // NOAA OBIS (Ocean Biodiversity Information System) — whale observations
    const res = await safeFetch(
      'https://api.obis.org/v3/occurrence?scientificname=Cetacea&size=100&sortby=date_mid&order=desc',
      { timeout: 15000 }
    );
    if (!res?.results?.length) return [];
    return res.results.slice(0, 50).map(r => ({
      species: r.scientificName || 'Unknown cetacean',
      lat: r.decimalLatitude,
      lon: r.decimalLongitude,
      date: r.date_mid || r.eventDate,
      dataset: r.dataset_id,
    })).filter(r => r.lat != null && r.lon != null);
  } catch (e) {
    console.log('[Whales] OBIS fetch failed:', e.message);
    return [];
  }
}

// === Main briefing export ===
export async function briefing() {
  const month = new Date().getMonth() + 1;
  const sightings = await fetchNOAACetacean();

  const corridorStatus = MIGRATION_CORRIDORS.map(c => ({
    ...c,
    ...getCorridorActivity(c),
  }));

  const activeAreas = PROTECTED_AREAS.map(a => ({
    ...a,
    active: isAreaActive(a),
  }));

  // Compute risk zones from corridor/lane intersections
  const riskZones = [];
  for (const lane of SHIPPING_LANES) {
    for (const corridor of corridorStatus) {
      const intersects = lane.intersectedSpecies.some(s =>
        corridor.species.includes(s) || s.includes(corridor.species.split(' (')[0])
      );
      if (!intersects) continue;

      // Find approximate intersection center
      const laneCenter = lane.segments.reduce(
        (acc, seg) => ({
          lat: acc.lat + (seg.from.lat + seg.to.lat) / 2,
          lon: acc.lon + (seg.from.lon + seg.to.lon) / 2,
        }),
        { lat: 0, lon: 0 }
      );
      laneCenter.lat /= lane.segments.length;
      laneCenter.lon /= lane.segments.length;

      const riskLevel = corridor.peakRisk ? (lane.risk === 'critical' ? 10 : 8)
        : corridor.activity !== 'low' ? (lane.risk === 'critical' ? 7 : 5)
        : (lane.risk === 'critical' ? 4 : 2);

      riskZones.push({
        id: `${lane.id}-${corridor.id}`,
        lat: laneCenter.lat,
        lon: laneCenter.lon,
        riskScore: riskLevel,
        species: corridor.species,
        shippingLane: lane.name,
        activity: corridor.activity,
        vesselDensity: lane.vesselDensity,
      });
    }
  }

  return {
    source: 'Whale Strike Intelligence',
    timestamp: new Date().toISOString(),
    month,
    sightings,
    corridors: corridorStatus,
    shippingLanes: SHIPPING_LANES,
    protectedAreas: activeAreas,
    riskZones,
    historicalStrikes: HISTORICAL_STRIKES,
    activeCorridors: corridorStatus.filter(c => c.activity !== 'low').length,
    activeProtectedAreas: activeAreas.filter(a => a.active).length,
    totalRiskZones: riskZones.length,
    highRiskZones: riskZones.filter(z => z.riskScore >= 7).length,
  };
}

if (process.argv[1]?.endsWith('whales.mjs')) {
  const data = await briefing();
  console.log(JSON.stringify(data, null, 2));
}
```

**Step 2: Test the data source standalone**

Run: `cd crucix && node apis/sources/whales.mjs`

Expected: JSON output with corridors, shipping lanes, risk zones, and OBIS sightings. The OBIS API may return empty if rate-limited — that's fine, the hardcoded data should always be present.

**Step 3: Commit**

```bash
git add crucix/apis/sources/whales.mjs
git commit -m "feat: add whale data source with migration corridors, shipping lanes, risk zones"
```

---

## Task 3: Replace briefing orchestrator (`apis/briefing.mjs`)

**Files:**
- Modify: `crucix/apis/briefing.mjs`

**Step 1: Replace the briefing orchestrator**

Replace the entire content of `crucix/apis/briefing.mjs` with:

```javascript
#!/usr/bin/env node

// Whale Strike Intelligence — runs whale + maritime + conflict sources in parallel
// Replaces the original 27-source OSINT sweep

import './utils/env.mjs';
import { pathToFileURL } from 'node:url';

import { briefing as whales } from './sources/whales.mjs';
import { briefing as ships } from './sources/ships.mjs';
import { briefing as noaa } from './sources/noaa.mjs';
import { briefing as acled } from './sources/acled.mjs';

const SOURCE_TIMEOUT_MS = 30_000;

export async function runSource(name, fn, ...args) {
  const start = Date.now();
  let timer;
  try {
    const dataPromise = fn(...args);
    const timeoutPromise = new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(`Source ${name} timed out after ${SOURCE_TIMEOUT_MS / 1000}s`)), SOURCE_TIMEOUT_MS);
    });
    const data = await Promise.race([dataPromise, timeoutPromise]);
    return { name, status: 'ok', durationMs: Date.now() - start, data };
  } catch (e) {
    return { name, status: 'error', durationMs: Date.now() - start, error: e.message };
  } finally {
    clearTimeout(timer);
  }
}

export async function fullBriefing() {
  console.error('[Crucix] Starting whale intelligence sweep — 4 sources...');
  const start = Date.now();

  const allPromises = [
    runSource('Whales', whales),
    runSource('Maritime', ships),
    runSource('NOAA', noaa),
    runSource('ACLED', acled),
  ];

  const results = await Promise.allSettled(allPromises);
  const sources = results.map(r => r.status === 'fulfilled' ? r.value : { status: 'failed', error: r.reason?.message });
  const totalMs = Date.now() - start;

  const output = {
    crucix: {
      version: '2.0.0-whales',
      timestamp: new Date().toISOString(),
      totalDurationMs: totalMs,
      sourcesQueried: sources.length,
      sourcesOk: sources.filter(s => s.status === 'ok').length,
      sourcesFailed: sources.filter(s => s.status !== 'ok').length,
    },
    sources: Object.fromEntries(
      sources.filter(s => s.status === 'ok').map(s => [s.name, s.data])
    ),
    errors: sources.filter(s => s.status !== 'ok').map(s => ({ name: s.name, error: s.error })),
    timing: Object.fromEntries(
      sources.map(s => [s.name, { status: s.status, ms: s.durationMs }])
    ),
  };

  console.error(`[Crucix] Sweep complete in ${totalMs}ms — ${output.crucix.sourcesOk}/${sources.length} sources returned data`);
  return output;
}

const entryHref = process.argv[1] ? pathToFileURL(process.argv[1]).href : null;
if (entryHref && import.meta.url === entryHref) {
  const data = await fullBriefing();
  console.log(JSON.stringify(data, null, 2));
}
```

**Step 2: Test the sweep**

Run: `cd crucix && node apis/briefing.mjs 2>&1 | head -20`

Expected: JSON output with Whales, Maritime, NOAA, and ACLED source data. Should complete in <15 seconds.

**Step 3: Commit**

```bash
git add crucix/apis/briefing.mjs
git commit -m "feat: replace OSINT sweep with whale intelligence sources"
```

---

## Task 4: Replace synthesizer (`dashboard/inject.mjs`)

**Files:**
- Modify: `crucix/dashboard/inject.mjs`

**Step 1: Replace the synthesizer**

Replace the entire content of `crucix/dashboard/inject.mjs` with:

```javascript
#!/usr/bin/env node
// Whale Strike Dashboard Data Synthesizer
// Reads sweep data and synthesizes into whale-specific dashboard format

import { existsSync, readFileSync, writeFileSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';
import { exec } from 'child_process';
import config from '../crucix.config.mjs';
import { createLLMProvider } from '../lib/llm/index.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');

// === Synthesize raw sweep data into whale dashboard format ===
export async function synthesize(data) {
  const whaleData = data.sources.Whales || {};
  const maritimeData = data.sources.Maritime || {};
  const noaaData = data.sources.NOAA || {};
  const acledData = data.sources.ACLED || {};

  // ACLED conflict zones — used for voyage planner avoidance
  const conflictZones = [];
  const acledEvents = acledData.deadliestEvents || [];
  // Group nearby events into zones
  for (const evt of acledEvents) {
    if (evt.lat == null || evt.lon == null) continue;
    conflictZones.push({
      lat: evt.lat,
      lon: evt.lon,
      type: evt.type,
      country: evt.country,
      fatalities: evt.fatalities || 0,
      date: evt.date,
      location: evt.location,
    });
  }
  const conflictSummary = {
    totalEvents: acledData.totalEvents || 0,
    totalFatalities: acledData.totalFatalities || 0,
    byRegion: acledData.byRegion || {},
    zones: conflictZones,
  };

  const corridors = (whaleData.corridors || []).map(c => ({
    id: c.id,
    species: c.species,
    status: c.status,
    activity: c.activity,
    peakRisk: c.peakRisk,
    estimatedPopulation: c.estimatedPopulation,
    route: c.route || [],
  }));

  const riskZones = (whaleData.riskZones || []).map(z => ({
    id: z.id,
    lat: z.lat,
    lon: z.lon,
    riskScore: z.riskScore,
    species: z.species,
    shippingLane: z.shippingLane,
    activity: z.activity,
    vesselDensity: z.vesselDensity,
  }));

  const shippingLanes = (whaleData.shippingLanes || []).map(l => ({
    id: l.id,
    name: l.name,
    risk: l.risk,
    intersectedSpecies: l.intersectedSpecies,
    segments: l.segments,
    vesselDensity: l.vesselDensity,
  }));

  const protectedAreas = (whaleData.protectedAreas || []).map(a => ({
    id: a.id,
    name: a.name,
    lat: a.lat,
    lon: a.lon,
    radiusKm: a.radiusKm,
    species: a.species,
    type: a.type,
    active: a.active,
  }));

  const sightings = (whaleData.sightings || []).slice(0, 50);
  const historicalStrikes = whaleData.historicalStrikes || {};

  const chokepoints = Object.values(maritimeData.chokepoints || {}).map(c => ({
    label: c.label || c.name, note: c.note || '', lat: c.lat || 0, lon: c.lon || 0,
  }));

  const weatherAlerts = {
    totalAlerts: noaaData.totalSevereAlerts || 0,
    alerts: (noaaData.topAlerts || []).filter(a => a.lat != null && a.lon != null).slice(0, 10).map(a => ({
      event: a.event, severity: a.severity, headline: a.headline?.substring(0, 120),
      lat: a.lat, lon: a.lon,
    })),
  };

  // Species summary
  const speciesStatus = corridors.map(c => ({
    species: c.species,
    activity: c.activity,
    peakRisk: c.peakRisk,
    population: c.estimatedPopulation,
    status: c.status,
    sightings: sightings.filter(s =>
      s.species?.toLowerCase().includes(c.species.split(' (')[0].split(' ').slice(-1)[0].toLowerCase())
    ).length,
  }));

  // Metrics
  const metrics = {
    activeRiskZones: riskZones.filter(z => z.riskScore >= 5).length,
    highRiskZones: riskZones.filter(z => z.riskScore >= 7).length,
    speciesInMigration: corridors.filter(c => c.activity !== 'low').length,
    activeProtectedAreas: protectedAreas.filter(a => a.active).length,
    recentSightings: sightings.length,
    historicalMonthlyAvg: historicalStrikes.annualAverage ? (historicalStrikes.annualAverage / 12).toFixed(1) : '--',
  };

  // Compute global risk level
  const maxRisk = Math.max(...riskZones.map(z => z.riskScore), 0);
  const globalRisk = maxRisk >= 8 ? 'CRITICAL' : maxRisk >= 6 ? 'HIGH' : maxRisk >= 4 ? 'MODERATE' : 'LOW';
  const riskReason = corridors.find(c => c.activity === 'calving')
    ? 'CALVING SEASON'
    : corridors.filter(c => c.peakRisk).length > 2
    ? 'PEAK MIGRATION'
    : corridors.filter(c => c.activity !== 'low').length > 0
    ? 'ACTIVE MIGRATION'
    : 'LOW SEASON';

  const health = Object.entries(data.sources).map(([name, src]) => ({
    n: name, err: Boolean(src.error), stale: Boolean(src.stale),
  }));

  const V2 = {
    meta: data.crucix,
    corridors,
    riskZones,
    shippingLanes,
    protectedAreas,
    sightings,
    speciesStatus,
    historicalStrikes,
    chokepoints,
    weatherAlerts,
    conflictSummary,
    metrics,
    globalRisk,
    riskReason,
    health,
    recommendations: [],
    recommendationsSource: 'disabled',
  };

  return V2;
}

// generateIdeas is now generateRecommendations — but LLM handles this in server.mjs
export function generateIdeas() { return []; }

// fetchAllNews removed — not needed for whale dashboard
export async function fetchAllNews() { return []; }

// === CLI Mode ===
async function cliInject() {
  const data = JSON.parse(readFileSync(join(ROOT, 'runs/latest.json'), 'utf8'));
  const V2 = await synthesize(data);
  const json = JSON.stringify(V2);
  console.log('--- Whale Strike Synthesis ---');
  console.log('Size:', json.length, 'bytes | Risk Zones:', V2.riskZones.length,
    '| Corridors:', V2.corridors.length, '| Sightings:', V2.sightings.length);
  console.log('Global Risk:', V2.globalRisk, '|', V2.riskReason);

  const htmlPath = join(ROOT, 'dashboard/public/jarvis.html');
  let html = readFileSync(htmlPath, 'utf8');
  html = html.replace(/^(let|const) D = .*;\s*$/m, () => 'let D = ' + json + ';');
  writeFileSync(htmlPath, html);
  console.log('Data injected into jarvis.html!');
}

const isMain = process.argv[1]
  && fileURLToPath(import.meta.url).replace(/\\/g, '/') === process.argv[1].replace(/\\/g, '/');
if (isMain) {
  await cliInject();
}
```

**Step 2: Commit**

```bash
git add crucix/dashboard/inject.mjs
git commit -m "feat: replace OSINT synthesizer with whale strike data synthesizer"
```

---

## Task 5: Update server.mjs for whale context

**Files:**
- Modify: `crucix/server.mjs`

**Step 1: Update the LLM ideas generation to whale recommendations**

In `crucix/server.mjs`, replace the LLM ideas section (lines ~337-359, inside `runSweepCycle()`) and the startup banner. Key changes:

1. Replace the LLM ideas block with a whale route recommendations generator
2. Update the startup banner from "CRUCIX INTELLIGENCE ENGINE" to "WHALE STRIKE MITIGATION ENGINE"
3. Update console log messages
4. Update the `/brief` Telegram/Discord command for whale context

The LLM ideas block (currently lines 337-359) should be replaced with:

```javascript
    // 5. LLM-powered route recommendations
    if (llmProvider?.isConfigured) {
      try {
        console.log('[Crucix] Generating LLM route recommendations...');
        const prompt = buildWhaleRecommendationPrompt(synthesized);
        const result = await llmProvider.complete(
          'You are a maritime safety analyst specializing in whale strike mitigation. Generate route recommendations in valid JSON array format.',
          prompt,
          { maxTokens: 4096, timeout: 60000 }
        );
        try {
          const jsonMatch = result.text.match(/\[[\s\S]*\]/);
          if (jsonMatch) {
            synthesized.recommendations = JSON.parse(jsonMatch[0]);
            synthesized.recommendationsSource = 'llm';
            console.log(`[Crucix] LLM generated ${synthesized.recommendations.length} route recommendations`);
          }
        } catch (parseErr) {
          console.error('[Crucix] LLM recommendation parse failed:', parseErr.message);
          synthesized.recommendations = [];
          synthesized.recommendationsSource = 'llm-failed';
        }
      } catch (llmErr) {
        console.error('[Crucix] LLM recommendations failed (non-fatal):', llmErr.message);
        synthesized.recommendations = [];
        synthesized.recommendationsSource = 'llm-failed';
      }
    }
```

Add this helper function before `runSweepCycle()`:

```javascript
function buildWhaleRecommendationPrompt(data) {
  const highRisk = data.riskZones.filter(z => z.riskScore >= 6);
  const activeCorridors = data.corridors.filter(c => c.activity !== 'low');
  return `Current whale strike risk assessment:
- Global risk: ${data.globalRisk} (${data.riskReason})
- ${highRisk.length} high-risk zones active
- ${activeCorridors.length} migration corridors active: ${activeCorridors.map(c => `${c.species} (${c.activity})`).join(', ')}
- Month: ${new Date().toLocaleString('en-US', { month: 'long' })}

High-risk zones:
${highRisk.map(z => `- ${z.shippingLane}: risk ${z.riskScore}/10, ${z.species} (${z.activity}), vessel density: ${z.vesselDensity}`).join('\n')}

Generate 3-5 route recommendations as a JSON array. Each object must have:
- "lane": affected shipping lane name
- "action": specific recommendation (e.g., "Shift 5nm south", "Reduce speed to 10 knots")
- "riskReduction": estimated risk reduction percentage (number)
- "costImpact": brief cost description (e.g., "+2nm distance, ~15 min delay")
- "species": species being protected
- "validDates": when this recommendation applies (e.g., "March-May 2026")
- "priority": "critical" | "high" | "moderate"

Focus on actionable, specific recommendations with realistic trade-offs.`;
}
```

Also update the startup banner (lines ~400-411):

```javascript
  console.log(`
  ╔══════════════════════════════════════════════╗
  ║       WHALE STRIKE MITIGATION ENGINE         ║
  ║     Route Safety · 4 Sources · Voyage Plan   ║
  ╠══════════════════════════════════════════════╣
  ║  Dashboard:  http://localhost:${port}${' '.repeat(14 - String(port).length)}║
  ║  Health:     http://localhost:${port}/api/health${' '.repeat(4 - String(port).length)}║
  ║  Refresh:    Every ${config.refreshIntervalMinutes} min${' '.repeat(20 - String(config.refreshIntervalMinutes).length)}║
  ║  LLM:        ${(config.llm.provider || 'disabled').padEnd(31)}║
  ╚══════════════════════════════════════════════╝
  `);
```

Replace `synthesized.ideas` references with `synthesized.recommendations` and update console logs similarly.

**Step 2: Commit**

```bash
git add crucix/server.mjs
git commit -m "feat: update server for whale strike context — LLM recommendations, banner"
```

---

## Task 6: Replace jarvis.html frontend

**Files:**
- Modify: `crucix/dashboard/public/jarvis.html`

This is the largest task. The HTML is ~1769 lines. We need to replace the entire `<script>` section (rendering functions) and the CSS classes for new panel types. Keep all the map infrastructure (D3, Globe.GL, Three.js) and boot sequence.

**Step 1: Update CSS — add whale-specific styles**

Add these new CSS classes (after the existing styles, before `</style>`):

```css
/* WHALE STRIKE SPECIFIC */
.whale-corridor{fill:none;stroke:rgba(79,195,247,0.6);stroke-width:2;stroke-dasharray:8 4}
.whale-corridor.active{stroke:rgba(79,195,247,0.9);animation:dash-flow 3s linear infinite}
.shipping-lane-line{fill:none;stroke:rgba(255,255,255,0.15);stroke-width:1.5}
.risk-zone-circle{fill-opacity:0.15;stroke-width:1.5}
.risk-zone-circle.critical{fill:rgba(255,95,99,0.2);stroke:rgba(255,95,99,0.6)}
.risk-zone-circle.high{fill:rgba(255,184,76,0.2);stroke:rgba(255,184,76,0.6)}
.risk-zone-circle.moderate{fill:rgba(100,240,200,0.15);stroke:rgba(100,240,200,0.4)}
.protected-area{fill:none;stroke:rgba(179,136,255,0.5);stroke-width:1.5;stroke-dasharray:4 2}
.protected-area.active{fill:rgba(179,136,255,0.08)}
.species-row{display:flex;align-items:center;justify-content:space-between;padding:8px;border:1px solid rgba(255,255,255,0.04);background:rgba(255,255,255,0.02);margin-bottom:4px}
.species-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.species-dot.calving{background:#ff5f63;box-shadow:0 0 6px rgba(255,95,99,0.6)}
.species-dot.feeding{background:#64f0c8;box-shadow:0 0 6px rgba(100,240,200,0.4)}
.species-dot.migrating{background:#ffb84c;box-shadow:0 0 6px rgba(255,184,76,0.4)}
.species-dot.low{background:rgba(106,138,130,0.4)}
.rec-card{padding:10px;border:1px solid rgba(79,195,247,0.15);background:rgba(79,195,247,0.03);margin-bottom:6px}
.rec-card.critical{border-left:3px solid var(--danger)}
.rec-card.high{border-left:3px solid var(--warn)}
.rec-card.moderate{border-left:3px solid var(--accent)}
.rec-priority{font-family:var(--mono);font-size:9px;letter-spacing:0.1em;text-transform:uppercase;padding:2px 6px;border:1px solid;display:inline-block;margin-bottom:4px}
.rec-priority.critical{color:var(--danger);border-color:rgba(255,95,99,0.3)}
.rec-priority.high{color:var(--warn);border-color:rgba(255,184,76,0.3)}
.rec-priority.moderate{color:var(--accent);border-color:rgba(100,240,200,0.3)}
.rec-lane{font-size:12px;font-weight:600;margin-bottom:3px}
.rec-action{font-size:11px;line-height:1.4;color:var(--accent2)}
.rec-meta{font-family:var(--mono);font-size:9px;color:var(--dim);margin-top:4px;display:flex;gap:8px;flex-wrap:wrap}
.whale-sighting{fill:rgba(79,195,247,0.7);stroke:rgba(79,195,247,0.3);stroke-width:0.5}
```

**Step 2: Replace the rendering JavaScript**

Replace the entire `<script>` content starting from `// === DATA ===` through the end of the file. The key functions to replace:

- `renderTopbar()` — rebrand to "WHALE STRIKE TERMINAL", show global risk level instead of "WARTIME STAGFLATION RISK", region buttons become ocean basins
- `renderLeftRail()` — species tracker + migration status + protected zones (replace sensor grid, nuclear watch, risk gauges, space watch)
- `renderRight()` — route recommendations + seasonal briefing (replace OSINT feed + sentiment)
- `renderLower()` — risk metrics grid + source health (replace ticker, delta, macro, ideas panels)
- `renderMap()` / `drawFlatMap()` / Globe data — render whale corridors, shipping lanes, risk zones, protected areas, sightings instead of conflicts/fires/flights
- `renderMapLegend()` — whale-specific legend items
- Boot sequence text — whale strike themed

The full JavaScript replacement is ~800 lines. Key rendering changes:

**renderTopbar**: Brand = "WHALE STRIKE MONITOR", regime chip = `${D.globalRisk} — ${D.riskReason}`, regions = `['global','nAtlantic','nPacific','sPacific','indian','southern']`

**renderLeftRail**: Three panels:
1. Species Tracker — loop `D.speciesStatus`, show species name, activity dot, sighting count
2. Migration Status — show active corridors count, current month context
3. Protected Zones — loop `D.protectedAreas`, show active/inactive status

**Map overlays** (in `drawFlatMap` / globe data):
1. Shipping lanes (gray lines from segment data)
2. Migration corridors (blue dashed animated lines from route waypoints)
3. Risk zones (colored circles at zone lat/lon, radius proportional to risk score)
4. Protected areas (purple dashed circles)
5. Whale sightings (small blue dots)

**renderRight**: Two panels:
1. Route Recommendations — loop `D.recommendations`, show priority badge, lane, action, risk reduction, cost, species, dates
2. Source Status — loop `D.health`

**renderLower**: Single metrics panel with `D.metrics` values.

This is the most code-heavy task. The implementing agent should follow the existing Crucix rendering pattern (innerHTML template literals, D3 for map overlays, Globe.GL for 3D points/arcs).

**Step 3: Commit**

```bash
git add crucix/dashboard/public/jarvis.html
git commit -m "feat: replace Jarvis frontend with whale strike mitigation dashboard"
```

---

## Task 6a: Add voyage planner API endpoint (`/api/route`)

**Files:**
- Modify: `crucix/server.mjs`

**Step 1: Add the route planning endpoint**

Add this endpoint to server.mjs, after the existing `/api/health` endpoint (around line 277):

```javascript
// API: voyage route planner — LLM generates whale-safe, conflict-aware route
app.use(express.json());

app.post('/api/route', async (req, res) => {
  const { origin, destination } = req.body;
  if (!origin || !destination) {
    return res.status(400).json({ error: 'origin and destination are required' });
  }
  if (!llmProvider?.isConfigured) {
    return res.status(503).json({ error: 'LLM not configured — route planning requires Gemini' });
  }

  console.log(`[Crucix] Route request: ${origin} → ${destination}`);
  const startTime = Date.now();

  try {
    const whaleContext = currentData ? buildRouteAvoidanceContext(currentData) : 'No current data available.';

    const systemPrompt = `You are a maritime route planning specialist. You generate sea routes between ports that avoid whale migration corridors, conflict zones, and other maritime hazards. Return ONLY valid JSON — no markdown, no explanation outside the JSON.`;

    const userPrompt = `Plan a sea route from ${origin} to ${destination}.

AVOIDANCE ZONES (current as of ${new Date().toISOString()}):

${whaleContext}

Return a JSON object with this exact structure:
{
  "origin": { "name": "Port Name, Country", "lat": number, "lon": number },
  "destination": { "name": "Port Name, Country", "lat": number, "lon": number },
  "waypoints": [
    { "lat": number, "lon": number, "label": "description of this waypoint", "note": "why routed here" }
  ],
  "standardRoute": {
    "distanceNm": number,
    "estimatedDays": number,
    "riskLevel": "high" | "moderate" | "low"
  },
  "safeRoute": {
    "distanceNm": number,
    "estimatedDays": number,
    "riskLevel": "high" | "moderate" | "low",
    "distancePenaltyNm": number,
    "timePenaltyDays": number
  },
  "avoidedZones": [
    { "name": "zone name", "type": "whale" | "conflict", "reason": "brief explanation" }
  ],
  "warnings": ["any relevant warnings"],
  "seasonalNotes": "current seasonal context for whale activity along this route"
}

Rules:
- Waypoints must be in navigable ocean/sea (not on land)
- Include 8-15 waypoints for a realistic route
- Compare the whale-safe route against the standard great-circle/canal route
- Factor in current month (${new Date().toLocaleString('en-US', { month: 'long', year: 'numeric' })}) for seasonal whale activity
- Use major shipping canals (Suez, Panama) when they shorten the route significantly
- Avoid conflict zones from ACLED data
- Waypoints should trace a plausible sea path (follow coastlines, pass through straits correctly)`;

    const result = await llmProvider.complete(systemPrompt, userPrompt, {
      maxTokens: 4096,
      timeout: 90000,
    });

    const jsonMatch = result.text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) {
      return res.status(500).json({ error: 'LLM did not return valid route JSON' });
    }

    const route = JSON.parse(jsonMatch[0]);
    route.computedIn = Date.now() - startTime;
    route.model = result.model;

    console.log(`[Crucix] Route computed: ${origin} → ${destination} in ${route.computedIn}ms — ${route.waypoints?.length || 0} waypoints`);

    res.json(route);
  } catch (err) {
    console.error('[Crucix] Route planning failed:', err.message);
    res.status(500).json({ error: err.message });
  }
});
```

**Step 2: Add the avoidance context builder**

Add this helper function near `buildWhaleRecommendationPrompt`:

```javascript
function buildRouteAvoidanceContext(data) {
  const sections = [];

  // Whale migration corridors
  const activeCorridors = (data.corridors || []).filter(c => c.activity !== 'low');
  if (activeCorridors.length) {
    sections.push('WHALE MIGRATION CORRIDORS (avoid or slow to <10 knots):');
    for (const c of activeCorridors) {
      const waypoints = c.route.map(r => `${r.lat},${r.lon}`).join(' → ');
      sections.push(`- ${c.species} (${c.activity}): ${waypoints}`);
    }
  }

  // Risk zones
  const highRisk = (data.riskZones || []).filter(z => z.riskScore >= 6);
  if (highRisk.length) {
    sections.push('\nHIGH-RISK WHALE STRIKE ZONES:');
    for (const z of highRisk) {
      sections.push(`- ${z.shippingLane} (${z.lat},${z.lon}): risk ${z.riskScore}/10, ${z.species}`);
    }
  }

  // Conflict zones from ACLED
  const conflicts = data.conflictSummary?.zones || [];
  if (conflicts.length) {
    sections.push('\nCONFLICT/DANGER ZONES (avoid entirely):');
    for (const z of conflicts.slice(0, 15)) {
      sections.push(`- ${z.country}, ${z.location || ''} (${z.lat},${z.lon}): ${z.type}, ${z.fatalities} fatalities`);
    }
  }

  // Protected areas
  const activeAreas = (data.protectedAreas || []).filter(a => a.active);
  if (activeAreas.length) {
    sections.push('\nPROTECTED MARINE AREAS (speed restriction zones):');
    for (const a of activeAreas) {
      sections.push(`- ${a.name} (${a.lat},${a.lon}): ${a.species}, radius ${a.radiusKm}km`);
    }
  }

  return sections.join('\n');
}
```

**Step 3: Commit**

```bash
git add crucix/server.mjs
git commit -m "feat: add /api/route voyage planner endpoint with LLM route generation"
```

---

## Task 6b: Add voyage planner UI to frontend

**Files:**
- Modify: `crucix/dashboard/public/jarvis.html`

**Step 1: Add voyage planner CSS**

Add these styles alongside the whale-specific CSS:

```css
/* VOYAGE PLANNER */
.voyage-panel{border:1px solid rgba(68,204,255,0.2);background:rgba(68,204,255,0.03);padding:12px}
.voyage-inputs{display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap}
.voyage-input{flex:1;min-width:120px;padding:8px 10px;border:1px solid var(--border);background:rgba(255,255,255,0.04);color:var(--text);font-family:var(--mono);font-size:11px;letter-spacing:0.04em;outline:none;transition:border-color 0.2s}
.voyage-input:focus{border-color:var(--accent2)}
.voyage-input::placeholder{color:var(--dim)}
.voyage-btn{padding:8px 16px;border:1px solid var(--accent2);background:rgba(68,204,255,0.1);color:var(--accent2);font-family:var(--mono);font-size:11px;font-weight:600;letter-spacing:0.1em;text-transform:uppercase;cursor:pointer;transition:all 0.2s;white-space:nowrap}
.voyage-btn:hover{background:var(--accent2);color:var(--bg)}
.voyage-btn:disabled{opacity:0.4;cursor:not-allowed}
.voyage-btn:disabled:hover{background:rgba(68,204,255,0.1);color:var(--accent2)}
.voyage-loading{display:flex;align-items:center;gap:8px;font-family:var(--mono);font-size:10px;color:var(--accent2);padding:8px 0}
.voyage-loading .spin{width:14px;height:14px;border:2px solid rgba(68,204,255,0.2);border-top-color:var(--accent2);border-radius:50%;animation:spin 0.8s linear infinite}
.voyage-result{margin-top:10px;padding:10px;border:1px solid rgba(100,240,200,0.15);background:rgba(100,240,200,0.03)}
.voyage-compare{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px}
.voyage-col{padding:8px;border:1px solid rgba(255,255,255,0.06);background:rgba(255,255,255,0.02)}
.voyage-col h4{font-family:var(--mono);font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:var(--dim);margin-bottom:6px}
.voyage-col.safe{border-color:rgba(100,240,200,0.15)}
.voyage-col.standard{border-color:rgba(255,95,99,0.15)}
.voyage-stat{font-family:var(--mono);font-size:12px;font-weight:600;margin-bottom:4px}
.voyage-stat .label{font-size:9px;color:var(--dim);font-weight:400;display:block;margin-bottom:2px}
.voyage-avoided{margin-top:8px}
.avoided-item{display:flex;align-items:center;gap:6px;padding:4px 0;font-size:10px;border-bottom:1px solid rgba(255,255,255,0.04)}
.avoided-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0}
.avoided-dot.whale{background:var(--accent2)}
.avoided-dot.conflict{background:var(--danger)}
.voyage-route-line{fill:none;stroke:rgba(100,240,200,0.8);stroke-width:2.5;stroke-linecap:round}
.voyage-route-line.animated{stroke-dasharray:12 6;animation:dash-flow 2s linear infinite}
.voyage-waypoint{fill:rgba(100,240,200,0.9);stroke:rgba(100,240,200,0.3);stroke-width:1}
.voyage-standard-line{fill:none;stroke:rgba(255,95,99,0.3);stroke-width:1.5;stroke-dasharray:4 4}
```

**Step 2: Add voyage planner to the topbar or center panel**

Add the voyage planner inputs above the map (inside the center column, before the map container). The HTML structure:

```html
<div class="voyage-panel" id="voyagePanel">
  <div class="sec-head"><h3>VOYAGE PLANNER</h3><span class="badge">LLM ROUTE</span></div>
  <div class="voyage-inputs">
    <input type="text" class="voyage-input" id="voyageOrigin" placeholder="Origin port (e.g., Tokyo)">
    <input type="text" class="voyage-input" id="voyageDest" placeholder="Destination port (e.g., London)">
    <button class="voyage-btn" id="voyageBtn" onclick="planVoyage()">PLAN ROUTE</button>
  </div>
  <div id="voyageStatus"></div>
  <div id="voyageResult"></div>
</div>
```

**Step 3: Add voyage planner JavaScript**

Add the route planning logic to the `<script>` section:

```javascript
let currentVoyageRoute = null;

async function planVoyage() {
  const origin = document.getElementById('voyageOrigin').value.trim();
  const dest = document.getElementById('voyageDest').value.trim();
  if (!origin || !dest) return;

  const btn = document.getElementById('voyageBtn');
  const status = document.getElementById('voyageStatus');
  const result = document.getElementById('voyageResult');

  btn.disabled = true;
  status.innerHTML = '<div class="voyage-loading"><div class="spin"></div>COMPUTING WHALE-SAFE ROUTE VIA GEMINI...</div>';
  result.innerHTML = '';

  try {
    const res = await fetch('/api/route', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ origin, destination: dest }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(err.error || `HTTP ${res.status}`);
    }

    const route = await res.json();
    currentVoyageRoute = route;

    status.innerHTML = `<div style="font-family:var(--mono);font-size:10px;color:var(--accent)">ROUTE COMPUTED IN ${(route.computedIn / 1000).toFixed(1)}s — ${route.waypoints?.length || 0} WAYPOINTS</div>`;

    // Render comparison
    const sr = route.standardRoute || {};
    const safe = route.safeRoute || {};
    const avoided = route.avoidedZones || [];

    result.innerHTML = `
      <div class="voyage-result">
        <div style="font-family:var(--mono);font-size:11px;font-weight:600;margin-bottom:6px">
          ${route.origin?.name || origin} → ${route.destination?.name || dest}
        </div>
        ${route.seasonalNotes ? `<div style="font-size:10px;color:var(--accent2);margin-bottom:8px;line-height:1.4">${route.seasonalNotes}</div>` : ''}
        <div class="voyage-compare">
          <div class="voyage-col standard">
            <h4>Standard Route</h4>
            <div class="voyage-stat"><span class="label">Distance</span>${sr.distanceNm || '--'} nm</div>
            <div class="voyage-stat"><span class="label">Est. Time</span>${sr.estimatedDays || '--'} days</div>
            <div class="voyage-stat"><span class="label">Risk</span><span style="color:var(--danger)">${(sr.riskLevel || '--').toUpperCase()}</span></div>
          </div>
          <div class="voyage-col safe">
            <h4>Whale-Safe Route</h4>
            <div class="voyage-stat"><span class="label">Distance</span>${safe.distanceNm || '--'} nm</div>
            <div class="voyage-stat"><span class="label">Est. Time</span>${safe.estimatedDays || '--'} days</div>
            <div class="voyage-stat"><span class="label">Risk</span><span style="color:var(--accent)">${(safe.riskLevel || '--').toUpperCase()}</span></div>
            <div class="voyage-stat" style="color:var(--warn)"><span class="label">Penalty</span>+${safe.distancePenaltyNm || 0} nm / +${safe.timePenaltyDays || 0} days</div>
          </div>
        </div>
        ${avoided.length ? `
          <div class="voyage-avoided">
            <div style="font-family:var(--mono);font-size:9px;color:var(--dim);margin:8px 0 4px;letter-spacing:0.1em">AVOIDED ZONES</div>
            ${avoided.map(z => `
              <div class="avoided-item">
                <div class="avoided-dot ${z.type}"></div>
                <span style="font-weight:500">${z.name}</span>
                <span style="color:var(--dim);margin-left:auto">${z.reason}</span>
              </div>
            `).join('')}
          </div>
        ` : ''}
        ${(route.warnings || []).length ? `
          <div style="margin-top:8px;padding:6px 8px;border:1px solid rgba(255,184,76,0.2);background:rgba(255,184,76,0.04);font-family:var(--mono);font-size:9px;color:var(--warn);line-height:1.5">
            ${route.warnings.join('<br>')}
          </div>
        ` : ''}
      </div>
    `;

    // Draw the route on the map
    drawVoyageRoute(route);

  } catch (err) {
    status.innerHTML = `<div style="font-family:var(--mono);font-size:10px;color:var(--danger)">ROUTE FAILED: ${err.message}</div>`;
  } finally {
    btn.disabled = false;
  }
}

function drawVoyageRoute(route) {
  if (!route?.waypoints?.length) return;

  const waypoints = [
    route.origin,
    ...route.waypoints,
    route.destination,
  ].filter(w => w?.lat != null && w?.lon != null);

  if (isFlat && flatG) {
    // Remove previous route
    flatG.selectAll('.voyage-route').remove();
    flatG.selectAll('.voyage-waypoint-dot').remove();
    flatG.selectAll('.voyage-standard').remove();

    // Draw standard route (straight line, dashed red) for comparison
    if (route.origin && route.destination) {
      flatG.append('line')
        .attr('class', 'voyage-standard voyage-standard-line')
        .attr('x1', flatProjection([route.origin.lon, route.origin.lat])[0])
        .attr('y1', flatProjection([route.origin.lon, route.origin.lat])[1])
        .attr('x2', flatProjection([route.destination.lon, route.destination.lat])[0])
        .attr('y2', flatProjection([route.destination.lon, route.destination.lat])[1]);
    }

    // Draw safe route (animated green line through waypoints)
    const lineGen = d3.line()
      .x(d => flatProjection([d.lon, d.lat])[0])
      .y(d => flatProjection([d.lon, d.lat])[1])
      .curve(d3.curveCardinal.tension(0.5));

    flatG.append('path')
      .attr('class', 'voyage-route voyage-route-line animated')
      .attr('d', lineGen(waypoints));

    // Draw waypoint dots
    flatG.selectAll('.voyage-waypoint-dot')
      .data(waypoints)
      .enter().append('circle')
      .attr('class', 'voyage-waypoint-dot voyage-waypoint')
      .attr('cx', d => flatProjection([d.lon, d.lat])[0])
      .attr('cy', d => flatProjection([d.lon, d.lat])[1])
      .attr('r', (d, i) => (i === 0 || i === waypoints.length - 1) ? 5 : 3)
      .append('title')
      .text(d => d.label || d.name || '');

  } else if (globe) {
    // Globe mode — use arcs for the route
    const arcs = [];
    for (let i = 0; i < waypoints.length - 1; i++) {
      arcs.push({
        startLat: waypoints[i].lat,
        startLng: waypoints[i].lon,
        endLat: waypoints[i + 1].lat,
        endLng: waypoints[i + 1].lon,
        color: 'rgba(100,240,200,0.9)',
        stroke: 1.5,
        label: waypoints[i].label || '',
      });
    }
    // Add to existing arcs
    const existingArcs = globe.arcsData() || [];
    globe.arcsData([...existingArcs.filter(a => !a._voyage), ...arcs.map(a => ({ ...a, _voyage: true }))]);

    // Add origin/destination as prominent points
    const routePoints = [waypoints[0], waypoints[waypoints.length - 1]].map(w => ({
      lat: w.lat, lng: w.lon, size: 0.6, color: 'rgba(100,240,200,1)',
      alt: 0.02, popHead: w.name || w.label, popText: '', popMeta: 'Route endpoint',
      _voyage: true,
    }));
    const existingPoints = globe.pointsData() || [];
    globe.pointsData([...existingPoints.filter(p => !p._voyage), ...routePoints]);

    // Pan to route midpoint
    const mid = waypoints[Math.floor(waypoints.length / 2)];
    globe.pointOfView({ lat: mid.lat, lng: mid.lon, altitude: 1.5 }, 1000);
  }
}
```

The `drawVoyageRoute` function handles both flat map (D3 path + circles) and globe mode (Globe.GL arcs + points). The green animated line is the whale-safe route; the red dashed line shows the standard direct route for comparison.

**Step 4: Wire Enter key and clear function**

```javascript
// Allow Enter key to trigger route planning
document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && (e.target.id === 'voyageOrigin' || e.target.id === 'voyageDest')) {
    planVoyage();
  }
});
```

**Step 5: Commit**

```bash
git add crucix/dashboard/public/jarvis.html
git commit -m "feat: add interactive voyage planner UI with LLM route generation and map drawing"
```

---

## Task 7: Update boot sequence + loading page

**Files:**
- Modify: `crucix/dashboard/public/jarvis.html` (boot section in HTML)
- Modify: `crucix/dashboard/public/loading.html`

**Step 1: Update boot sequence text**

In the boot sequence JavaScript (the `bootSequence` function), change the boot lines from OSINT-themed to whale strike themed:

```javascript
const bootLines = [
  { text: 'INITIALIZING WHALE STRIKE MITIGATION SYSTEM', class: '' },
  { text: 'CONNECTING NOAA CETACEAN DATABASE... ', class: 'ok', suffix: 'OK' },
  { text: 'LOADING MIGRATION CORRIDORS... ', class: 'count', suffix: `${D?.corridors?.length || 6} SPECIES` },
  { text: 'MAPPING SHIPPING LANES... ', class: 'count', suffix: `${D?.shippingLanes?.length || 8} ROUTES` },
  { text: 'COMPUTING RISK ZONES... ', class: 'count', suffix: `${D?.riskZones?.length || 0} INTERSECTIONS` },
  { text: 'LLM ROUTE ANALYSIS... ', class: 'ok', suffix: D?.recommendationsSource === 'llm' ? 'ACTIVE' : 'STANDBY' },
];
```

Change the logo text from "CRUCIX" to "WHALE STRIKE" and the boot final from "TERMINAL ACTIVE" to "MONITORING ACTIVE".

**Step 2: Update loading.html**

Update `crucix/dashboard/public/loading.html` to say "Whale Strike Mitigation Engine" instead of "Crucix Intelligence Engine".

**Step 3: Commit**

```bash
git add crucix/dashboard/public/jarvis.html crucix/dashboard/public/loading.html
git commit -m "feat: rebrand boot sequence and loading page for whale strike terminal"
```

---

## Task 8: End-to-end test — start server and verify

**Files:** None (verification only)

**Step 1: Kill any existing Crucix process**

Run: `taskkill /F /IM node.exe 2>/dev/null; sleep 2`

(Only kill if Crucix is still running from earlier)

**Step 2: Start the server**

Run: `cd crucix && node server.mjs`

Expected:
- Banner shows "WHALE STRIKE MITIGATION ENGINE"
- LLM shows "gemini (gemini-2.0-flash)" (if keys configured correctly)
- Sweep starts with 4 sources (Whales, Maritime, NOAA, ACLED)
- Dashboard loads at http://localhost:3117

**Step 3: Verify dashboard**

- Open http://localhost:3117 in browser
- Boot sequence should show whale-themed messages
- Map should show whale corridors (blue dashed lines), shipping lanes (gray), risk zones (colored circles), conflict zones (red)
- Left rail should show species tracker
- Right rail should show route recommendations (after LLM completes)
- **Voyage planner**: Type "Tokyo" and "London" in the inputs, click PLAN ROUTE
  - Should show loading spinner while Gemini computes
  - Should draw green animated route on map avoiding whale corridors and conflict zones
  - Should show standard vs. whale-safe route comparison
  - Should list avoided zones

**Step 4: Verify health endpoint**

Run: `curl -s http://localhost:3117/api/health | python -m json.tool`

Expected: JSON with version "2.0.0-whales", 4 sources queried.

**Step 5: Verify route API directly**

Run: `curl -s -X POST http://localhost:3117/api/route -H "Content-Type: application/json" -d '{"origin":"Tokyo","destination":"London"}' | python -m json.tool | head -30`

Expected: JSON with waypoints, standardRoute, safeRoute, avoidedZones.

**Step 5: Commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: address issues found during end-to-end testing"
```

---

## Summary

| Task | Description | Est. Lines Changed |
|------|------------|-------------------|
| 1 | Wire Gemini keys | 3 lines in .env |
| 2 | Create whales.mjs data source | ~350 new lines |
| 3 | Replace briefing.mjs (+ re-enable ACLED) | ~65 lines (full replace) |
| 4 | Replace inject.mjs (+ conflict zones) | ~200 lines (full replace) |
| 5 | Update server.mjs (recommendations + banner) | ~80 lines modified |
| 6 | Replace jarvis.html frontend (whale panels) | ~800 lines modified |
| 6a | Add `/api/route` voyage planner endpoint | ~120 new lines in server.mjs |
| 6b | Add voyage planner UI + map route drawing | ~250 new lines in jarvis.html |
| 7 | Update boot + loading | ~30 lines |
| 8 | End-to-end test (dashboard + voyage planner) | 0 (verification) |
