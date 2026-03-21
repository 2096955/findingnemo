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

// === RSS News Feed (global news for ticker) ===
const geoKeywords = {
  'Ukraine':[49,32],'Russia':[56,38],'China':[35,105],'Iran':[32,53],
  'Israel':[31.5,35],'Gaza':[31.4,34.4],'Syria':[35,38],'Iraq':[33,44],
  'Yemen':[15,48],'Lebanon':[34,36],'India':[20,78],'Japan':[36,138],
  'Korea':[37,127],'Taiwan':[23.5,121],'Philippines':[13,122],
  'UK':[54,-2],'France':[46,2],'Germany':[51,10],'Turkey':[39,35],
  'Africa':[0,20],'Nigeria':[10,8],'South Africa':[-30,25],'Egypt':[27,30],
  'Somalia':[5,46],'Sudan':[13,30],'US':[39,-98],'America':[39,-98],
  'Brazil':[-14,-51],'Mexico':[23,-102],'Australia':[-25,134],
  'Singapore':[1.35,103.8],'Indonesia':[-2,118],'Pakistan':[30,70],
  // Maritime-specific
  'Suez':[30,32.3],'Panama Canal':[9,-79.5],'Strait of Hormuz':[26.6,56.2],
  'Malacca':[2.5,101.8],'Bab el-Mandeb':[12.6,43.3],'Gibraltar':[36,-5.5],
  'Cape of Good Hope':[-34.4,18.5],'Red Sea':[20,38],'South China Sea':[14,114],
  'Arctic':[75,0],'Antarctic':[-75,0],'whale':[42,-70],'shipping':[40,-74],
  'maritime':[51.5,-0.1],'piracy':[5,46],'Navy':[38.9,-77],
};

function geoTagText(text) {
  if (!text) return null;
  for (const [keyword, [lat, lon]] of Object.entries(geoKeywords)) {
    if (text.includes(keyword)) return { lat, lon, region: keyword };
  }
  return null;
}

function sanitizeUrl(raw) {
  if (!raw) return undefined;
  try { const u = new URL(raw); return (u.protocol === 'http:' || u.protocol === 'https:') ? u.toString() : undefined; } catch { return undefined; }
}

async function fetchRSS(url, source) {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(8000) });
    const xml = await res.text();
    const items = [];
    const re = /<item>([\s\S]*?)<\/item>/g;
    let m;
    while ((m = re.exec(xml)) !== null) {
      const b = m[1];
      const title = (b.match(/<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?<\/title>/)?.[1] || '').trim();
      const link = sanitizeUrl((b.match(/<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?<\/link>/)?.[1] || '').trim());
      const pubDate = b.match(/<pubDate>(.*?)<\/pubDate>/)?.[1] || '';
      if (title && title !== source) items.push({ title, date: pubDate, source, url: link });
    }
    return items;
  } catch (e) {
    console.log(`[RSS] ${source} failed:`, e.message);
    return [];
  }
}

const RSS_GEO_FALLBACKS = {
  'SBS Australia': { lat: -35.3, lon: 149.1, region: 'Australia' },
  'Indian Express': { lat: 28.6, lon: 77.2, region: 'India' },
  'MercoPress': { lat: -34.9, lon: -56.2, region: 'South America' },
};

export async function fetchAllNews() {
  const feeds = [
    ['http://feeds.bbci.co.uk/news/world/rss.xml', 'BBC'],
    ['https://rss.nytimes.com/services/xml/rss/nyt/World.xml', 'NYT'],
    ['https://www.aljazeera.com/xml/rss/all.xml', 'Al Jazeera'],
    ['https://feeds.npr.org/1001/rss.xml', 'NPR'],
    ['https://rss.dw.com/rdf/rss-en-all', 'DW'],
    ['https://www.france24.com/en/rss', 'France 24'],
    ['https://rss.nytimes.com/services/xml/rss/nyt/AsiaPacific.xml', 'NYT Asia'],
    ['https://rss.nytimes.com/services/xml/rss/nyt/Africa.xml', 'NYT Africa'],
    ['http://feeds.bbci.co.uk/news/science_and_environment/rss.xml', 'BBC Science'],
  ];

  const results = await Promise.allSettled(feeds.map(([url, src]) => fetchRSS(url, src)));
  const all = results.filter(r => r.status === 'fulfilled').flatMap(r => r.value);

  const seen = new Set();
  const geoNews = [];
  for (const item of all) {
    const key = item.title.substring(0, 40).toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    const geo = geoTagText(item.title) || RSS_GEO_FALLBACKS[item.source];
    if (geo) {
      geoNews.push({
        headline: item.title.substring(0, 100),
        source: item.source, type: 'rss',
        timestamp: item.date, url: item.url,
        region: geo.region, urgent: false,
        lat: geo.lat + (Math.random() - 0.5) * 2,
        lon: geo.lon + (Math.random() - 0.5) * 2,
      });
    }
  }

  geoNews.sort((a, b) => new Date(b.timestamp || 0) - new Date(a.timestamp || 0));
  return geoNews.slice(0, 30);
}

// === Synthesize raw sweep data into whale dashboard format ===
export async function synthesize(data) {
  const whaleData = data.sources.Whales || {};
  const maritimeData = data.sources.Maritime || {};
  const noaaData = data.sources.NOAA || {};
  const acledData = data.sources.ACLED || {};
  const webIntelData = data.sources.WebIntelligence || {};

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

  // WebIntelligence alerts (firecrawl) — merge into conflict zones
  const webAlerts = webIntelData.alerts || [];
  for (const alert of webAlerts) {
    if (alert.lat != null && alert.lon != null) {
      conflictZones.push({
        lat: alert.lat,
        lon: alert.lon,
        type: alert.category || 'conflict',
        country: alert.region || 'Unknown',
        fatalities: 0,
        date: webIntelData.timestamp,
        location: alert.region || '',
        severity: alert.severity,
        title: alert.title,
        summary: alert.summary,
        sourceUrl: alert.sourceUrl,
        source: 'firecrawl',
      });
    }
  }

  const conflictSummary = {
    totalEvents: (acledData.totalEvents || 0) + webAlerts.length,
    totalFatalities: acledData.totalFatalities || 0,
    byRegion: acledData.byRegion || {},
    zones: conflictZones,
    webIntel: {
      totalAlerts: webAlerts.length,
      overallThreatLevel: webIntelData.overallThreatLevel || 'UNKNOWN',
      alerts: webAlerts,
    },
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

  // Fetch global news for ticker (with 20s timeout to prevent sweep hang)
  let newsFeed = [];
  try {
    const newsTimeout = new Promise((_, reject) => setTimeout(() => reject(new Error('News fetch timeout (20s)')), 20000));
    newsFeed = await Promise.race([fetchAllNews(), newsTimeout]);
    console.log(`[Crucix] Fetched ${newsFeed.length} news items for ticker`);
  } catch (e) {
    console.log('[Crucix] News feed fetch failed (non-fatal):', e.message);
  }

  // Also use as the news array (for map markers)
  const news = newsFeed.filter(n => n.lat && n.lon).map(n => ({
    title: n.headline, source: n.source, date: n.timestamp, url: n.url,
    lat: n.lat, lon: n.lon, region: n.region,
  }));

  const health = Object.entries(data.sources).map(([name, src]) => ({
    n: name, err: Boolean(src.error), stale: Boolean(src.stale),
  }));

  // === Compatibility layer: provide safe defaults for original Crucix fields ===
  // The jarvis.html frontend references D.air, D.thermal, etc. — provide empty/stub
  // versions so existing render functions don't crash, while whale data overlays on top.
  const acledCompat = {
    totalEvents: acledData.totalEvents || 0,
    totalFatalities: acledData.totalFatalities || 0,
    byRegion: acledData.byRegion || {},
    topCountries: acledData.topCountries || {},
    deadliestEvents: acledData.deadliestEvents || [],
  };

  const V2 = {
    meta: data.crucix,
    // --- Whale-specific ---
    corridors,
    riskZones,
    shippingLanes,
    protectedAreas,
    sightings,
    speciesStatus,
    historicalStrikes,
    weatherAlerts,
    conflictSummary,
    metrics,
    globalRisk,
    riskReason,
    health,
    recommendations: [],
    recommendationsSource: 'disabled',
    // --- Original Crucix compat (safe stubs so jarvis.html doesn't crash) ---
    air: [],
    thermal: [],
    sdr: { total: 0, online: 0, receivers: [], zones: [] },
    nuke: [],
    fred: [],
    tg: { posts: 0, urgent: [], topPosts: [], channels: [] },
    who: [],
    news,
    newsFeed,
    chokepoints,
    acled: acledCompat,
    treasury: { totalDebt: '0' },
    space: null,
    ideas: [],
    ideasSource: 'disabled',
    tSignals: [],
    bls: [],
    gscpi: null,
    markets: {},
    noaa: { alerts: [] },
    epa: { stations: [] },
    gdelt: { geoPoints: [] },
    energy: {},
    delta: null,
  };

  return V2;
}

// generateIdeas is now generateRecommendations — but LLM handles this in server.mjs
export function generateIdeas() { return []; }

// fetchAllNews is now defined at top of file with RSS feeds

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
