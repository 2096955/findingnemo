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
