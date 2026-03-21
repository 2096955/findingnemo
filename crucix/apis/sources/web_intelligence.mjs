// Web Intelligence — conflict zones + maritime threats via Tavily (primary) / Firecrawl (fallback)
// Always returns hardcoded baseline zones even if both APIs fail

import '../utils/env.mjs';

const TAVILY_API_KEY = process.env.TAVILY_API_KEY || '';
const FIRECRAWL_API_KEY = process.env.FIRECRAWL_API_KEY || '';
const FIRECRAWL_BASE = 'https://api.firecrawl.dev/v1';
const TAVILY_BASE = 'https://api.tavily.com';

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

// === Hardcoded baseline conflict zones — always present ===
const BASELINE_ZONES = [
  {
    category: 'armed_conflict', severity: 'HIGH',
    title: 'Red Sea / Houthi Threat Zone',
    summary: 'Ongoing Houthi attacks on commercial shipping in the Red Sea and Gulf of Aden. Multiple vessels targeted with missiles and drones.',
    lat: 15, lon: 42, region: 'Red Sea',
  },
  {
    category: 'armed_conflict', severity: 'HIGH',
    title: 'Black Sea Conflict Zone',
    summary: 'Russia-Ukraine conflict creates maritime danger. Drone attacks, floating mines, and restricted navigation in the western Black Sea.',
    lat: 43, lon: 34, region: 'Black Sea',
  },
  {
    category: 'armed_conflict', severity: 'MODERATE',
    title: 'Bosphorus / Turkish Straits Transit Risk',
    summary: 'Increased transit uncertainty through the Turkish Straits due to Black Sea conflict spillover and inspection delays.',
    lat: 41.1, lon: 29.0, region: 'Bosphorus',
  },
  {
    category: 'armed_conflict', severity: 'MODERATE',
    title: 'Strait of Hormuz Tension',
    summary: 'Ongoing Iran-related tensions affecting tanker traffic. Periodic vessel seizures and military confrontations.',
    lat: 26.6, lon: 56.2, region: 'Strait of Hormuz',
  },
  {
    category: 'piracy', severity: 'MODERATE',
    title: 'Gulf of Guinea Piracy Zone',
    summary: 'Persistent piracy and armed robbery against ships off West Africa, particularly near Nigeria and Cameroon.',
    lat: 3, lon: 3, region: 'Gulf of Guinea',
  },
  {
    category: 'piracy', severity: 'MODERATE',
    title: 'Somali Basin / Gulf of Aden',
    summary: 'Resurgence of Somali piracy linked to Houthi disruption of naval patrols. Increased risk for slower vessels.',
    lat: 5, lon: 50, region: 'Somali Basin',
  },
  {
    category: 'armed_conflict', severity: 'LOW',
    title: 'South China Sea Disputed Waters',
    summary: 'Territorial disputes and military build-up. Occasional confrontations near Spratly Islands and Scarborough Shoal.',
    lat: 14, lon: 114, region: 'South China Sea',
  },
  {
    category: 'armed_conflict', severity: 'LOW',
    title: 'Suez Canal Disruption Risk',
    summary: 'Reduced Suez Canal traffic due to Red Sea diversions. Potential for canal restrictions or blockages.',
    lat: 30, lon: 32.3, region: 'Suez Canal',
  },
];

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

// === Tavily Search (primary) ===
async function searchTavily(query, maxResults = 3) {
  if (!TAVILY_API_KEY) return [];

  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);

    const res = await fetch(`${TAVILY_BASE}/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        api_key: TAVILY_API_KEY,
        query,
        max_results: maxResults,
        search_depth: 'basic',
        include_answer: false,
      }),
      signal: controller.signal,
    });
    clearTimeout(timer);

    if (!res.ok) {
      console.log(`[WebIntel] Tavily search failed: HTTP ${res.status}`);
      return [];
    }

    const json = await res.json();
    const results = json.results || [];
    return results.map(r => ({
      title: r.title || '',
      url: r.url || '',
      snippet: (r.content || '').substring(0, 300),
    }));
  } catch (e) {
    console.log(`[WebIntel] Tavily error: ${e.message}`);
    return [];
  }
}

// === Firecrawl Search (fallback) ===
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

// === Search with fallback chain: Tavily → Firecrawl ===
async function searchWeb(query, maxResults = 3) {
  // Try Tavily first
  if (TAVILY_API_KEY) {
    const results = await searchTavily(query, maxResults);
    if (results.length > 0) return results;
  }
  // Fallback to Firecrawl
  if (FIRECRAWL_API_KEY) {
    return searchFirecrawl(query, maxResults);
  }
  return [];
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
  const provider = TAVILY_API_KEY ? 'Tavily' : FIRECRAWL_API_KEY ? 'Firecrawl' : 'none';
  const queries = buildQueries();

  // Always start with baseline zones
  const alerts = BASELINE_ZONES.map(z => ({
    ...z,
    sourceUrl: null,
    isBaseline: true,
  }));
  const seenRegions = new Set(alerts.map(a => a.region));

  // Enrich with live web search if any API is available
  if (provider !== 'none') {
    console.log(`[WebIntel] Running ${queries.length} queries via ${provider}...`);

    const allResults = [];
    const seenUrls = new Set();

    const batches = await Promise.allSettled(
      queries.map(q => searchWeb(q, 3))
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

    console.log(`[WebIntel] ${allResults.length} unique results from ${queries.length} queries via ${provider}`);

    // Classify and geo-tag live results
    for (const r of allResults) {
      const classification = classifyAlert(r.title, r.snippet);
      if (!classification.relevant) continue;

      const geo = geoTagAlert(r.title, r.snippet);
      const alert = {
        category: classification.category,
        severity: classification.severity,
        title: r.title,
        summary: r.snippet.substring(0, 200),
        sourceUrl: r.url,
        lat: geo?.lat || null,
        lon: geo?.lon || null,
        region: geo?.region || 'Unknown',
        isBaseline: false,
      };

      // If live data matches a baseline region, upgrade the baseline entry
      if (seenRegions.has(alert.region)) {
        const existing = alerts.find(a => a.region === alert.region && a.isBaseline);
        if (existing) {
          // Upgrade severity if live data is worse
          const order = { CRITICAL: 0, HIGH: 1, MODERATE: 2, LOW: 3 };
          if ((order[alert.severity] || 4) < (order[existing.severity] || 4)) {
            existing.severity = alert.severity;
          }
          // Add source URL to baseline
          if (!existing.liveSources) existing.liveSources = [];
          existing.liveSources.push({ title: alert.title, url: alert.sourceUrl });
          existing.summary = alert.summary; // Use fresh summary
        }
      } else {
        // New region not in baseline — add as new alert
        alerts.push(alert);
        seenRegions.add(alert.region);
      }
    }
  } else {
    console.log('[WebIntel] No API keys — using baseline conflict zones only');
  }

  // Sort by severity
  const order = { CRITICAL: 0, HIGH: 1, MODERATE: 2, LOW: 3 };
  alerts.sort((a, b) => (order[a.severity] || 4) - (order[b.severity] || 4));

  const severities = alerts.map(a => a.severity);
  const overallThreatLevel = severities.includes('CRITICAL') ? 'CRITICAL'
    : severities.filter(s => s === 'HIGH').length >= 2 ? 'HIGH'
    : severities.includes('HIGH') ? 'MODERATE'
    : 'LOW';

  const liveCount = alerts.filter(a => !a.isBaseline || a.liveSources?.length).length;

  return {
    source: 'WebIntelligence',
    provider,
    timestamp: new Date().toISOString(),
    totalAlerts: alerts.length,
    liveAlerts: liveCount,
    baselineAlerts: alerts.filter(a => a.isBaseline && !a.liveSources?.length).length,
    overallThreatLevel,
    alerts: alerts.slice(0, 20),
  };
}

if (process.argv[1]?.endsWith('web_intelligence.mjs')) {
  const data = await briefing();
  console.log(JSON.stringify(data, null, 2));
}
