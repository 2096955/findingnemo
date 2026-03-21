// Web Intelligence — conflict zones + maritime threats via Firecrawl search
// Ports the Python web_intelligence.py approach to Node.js for the Crucix sweep

import '../utils/env.mjs';

const FIRECRAWL_API_KEY = process.env.FIRECRAWL_API_KEY || '';
const FIRECRAWL_BASE = 'https://api.firecrawl.dev/v1';

const THREAT_CATEGORIES = {
  piracy: ['piracy', 'pirates', 'hijack', 'armed robbery at sea', 'maritime security incident', 'pirate attack'],
  armed_conflict: ['military', 'war', 'missile', 'attack', 'houthi', 'conflict zone', 'naval strike', 'drone strike', 'warship', 'blockade'],
  weather_disaster: ['cyclone', 'typhoon', 'hurricane', 'tsunami', 'storm surge', 'tropical storm', 'severe weather'],
  port_closure: ['port closed', 'port closure', 'terminal shutdown', 'strait closed', 'canal closed', 'waterway closed'],
  sanctions: ['sanctions', 'embargo', 'restricted vessels', 'trade restriction'],
  environmental_hazard: ['oil spill', 'contamination', 'marine pollution', 'chemical spill'],
};

const BOTTLENECK_STRAITS = ['hormuz', 'strait of hormuz'];

// Known maritime conflict/danger regions with coordinates
const REGION_COORDS = {
  'Red Sea': { lat: 20, lon: 38 },
  'Gulf of Aden': { lat: 12, lon: 45 },
  'Strait of Hormuz': { lat: 26.6, lon: 56.2 },
  'Bab el-Mandeb': { lat: 12.6, lon: 43.3 },
  'Gulf of Guinea': { lat: 3, lon: 3 },
  'Somali Basin': { lat: 5, lon: 50 },
  'South China Sea': { lat: 14, lon: 114 },
  'Malacca Strait': { lat: 2.5, lon: 101.8 },
  'Suez Canal': { lat: 30, lon: 32.3 },
  'Black Sea': { lat: 43, lon: 34 },
  'Bosphorus': { lat: 41.1, lon: 29.0 },
  'Mediterranean': { lat: 35, lon: 18 },
  'Caribbean': { lat: 15, lon: -72 },
  'Indian Ocean': { lat: -5, lon: 70 },
};

function buildQueries() {
  const now = new Date();
  const month = now.toLocaleString('en-US', { month: 'long' });
  const year = now.getFullYear();

  return [
    `maritime shipping route disruption ${month} ${year}`,
    `Red Sea Houthi shipping attack ${month} ${year}`,
    `Gulf of Guinea piracy alert ${month} ${year}`,
    `Strait of Hormuz military conflict shipping ${year}`,
    `Black Sea Bosphorus shipping conflict ${month} ${year}`,
    `maritime port closure ${month} ${year}`,
    `South China Sea naval incident ${year}`,
  ];
}

async function searchFirecrawl(query, maxResults = 3) {
  if (!FIRECRAWL_API_KEY) return [];

  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);

    const res = await fetch(`${FIRECRAWL_BASE}/search`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${FIRECRAWL_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query, limit: maxResults }),
      signal: controller.signal,
    });
    clearTimeout(timer);

    if (!res.ok) {
      console.log(`[WebIntel] Firecrawl search failed: HTTP ${res.status}`);
      return [];
    }

    const json = await res.json();
    const data = Array.isArray(json) ? json : json.data || [];
    return data.map(r => ({
      title: r.title || r.metadata?.title || '',
      url: r.url || r.sourceURL || '',
      snippet: (r.description || r.markdown || '').substring(0, 300),
    }));
  } catch (e) {
    console.log(`[WebIntel] Firecrawl error: ${e.message}`);
    return [];
  }
}

function classifyAlert(title, snippet) {
  const text = `${title} ${snippet}`.toLowerCase();

  let matchedCat = null;
  let matchCount = 0;
  for (const [cat, keywords] of Object.entries(THREAT_CATEGORIES)) {
    const hits = keywords.filter(kw => text.includes(kw)).length;
    if (hits > matchCount) {
      matchCount = hits;
      matchedCat = cat;
    }
  }

  if (!matchedCat || matchCount === 0) {
    return { category: 'unknown', severity: 'LOW', relevant: false };
  }

  let severity = matchCount >= 3 ? 'HIGH' : matchCount >= 2 ? 'MODERATE' : 'LOW';
  if ((matchedCat === 'armed_conflict' || matchedCat === 'piracy') && severity === 'MODERATE') {
    severity = 'HIGH';
  }

  // Boost to CRITICAL for bottleneck strait closures
  if (BOTTLENECK_STRAITS.some(s => text.includes(s))) {
    if (['closed', 'closure', 'blocked', 'blockade', 'shutdown'].some(sig => text.includes(sig))) {
      severity = 'CRITICAL';
    }
  }

  return { category: matchedCat, severity, relevant: true };
}

function geoTagAlert(title, snippet) {
  const text = `${title} ${snippet}`.toLowerCase();
  for (const [region, coords] of Object.entries(REGION_COORDS)) {
    if (text.includes(region.toLowerCase())) {
      return { ...coords, region };
    }
  }
  // Fallback keyword matching
  const fallbacks = {
    'yemen': REGION_COORDS['Gulf of Aden'],
    'houthi': REGION_COORDS['Red Sea'],
    'somalia': REGION_COORDS['Somali Basin'],
    'iran': REGION_COORDS['Strait of Hormuz'],
    'china': REGION_COORDS['South China Sea'],
    'nigeria': REGION_COORDS['Gulf of Guinea'],
    'ukraine': REGION_COORDS['Black Sea'],
    'russia': REGION_COORDS['Black Sea'],
    'bosphorus': { lat: 41.1, lon: 29.0, region: 'Bosphorus' },
    'turkey': { lat: 41.1, lon: 29.0, region: 'Bosphorus' },
    'suez': REGION_COORDS['Suez Canal'],
    'panama': { lat: 9, lon: -79.5, region: 'Panama Canal' },
  };
  for (const [kw, coords] of Object.entries(fallbacks)) {
    if (text.includes(kw)) return { ...coords, region: coords.region || kw };
  }
  return null;
}

export async function briefing() {
  if (!FIRECRAWL_API_KEY) {
    return {
      source: 'WebIntelligence',
      timestamp: new Date().toISOString(),
      status: 'no_api_key',
      message: 'Set FIRECRAWL_API_KEY in .env for web-based conflict zone detection',
      alerts: [],
      overallThreatLevel: 'UNKNOWN',
    };
  }

  const queries = buildQueries();
  console.log(`[WebIntel] Running ${queries.length} queries via Firecrawl...`);

  const allResults = [];
  const seenUrls = new Set();

  const batches = await Promise.allSettled(
    queries.map(q => searchFirecrawl(q, 3))
  );

  for (const batch of batches) {
    if (batch.status !== 'fulfilled') continue;
    for (const r of batch.value) {
      if (r.url && !seenUrls.has(r.url)) {
        seenUrls.add(r.url);
        allResults.push(r);
      }
    }
  }

  console.log(`[WebIntel] ${allResults.length} unique results from ${queries.length} queries`);

  const alerts = [];
  for (const r of allResults) {
    const classification = classifyAlert(r.title, r.snippet);
    if (!classification.relevant) continue;

    const geo = geoTagAlert(r.title, r.snippet);
    alerts.push({
      category: classification.category,
      severity: classification.severity,
      title: r.title,
      summary: r.snippet.substring(0, 200),
      sourceUrl: r.url,
      lat: geo?.lat || null,
      lon: geo?.lon || null,
      region: geo?.region || 'Unknown',
    });
  }

  // Sort by severity
  const order = { CRITICAL: 0, HIGH: 1, MODERATE: 2, LOW: 3 };
  alerts.sort((a, b) => (order[a.severity] || 4) - (order[b.severity] || 4));

  const severities = alerts.map(a => a.severity);
  const overallThreatLevel = severities.includes('CRITICAL') ? 'CRITICAL'
    : severities.filter(s => s === 'HIGH').length >= 2 ? 'HIGH'
    : severities.includes('HIGH') ? 'MODERATE'
    : 'LOW';

  return {
    source: 'WebIntelligence',
    timestamp: new Date().toISOString(),
    totalResults: allResults.length,
    totalAlerts: alerts.length,
    overallThreatLevel,
    alerts: alerts.slice(0, 15),
  };
}

if (process.argv[1]?.endsWith('web_intelligence.mjs')) {
  const data = await briefing();
  console.log(JSON.stringify(data, null, 2));
}
