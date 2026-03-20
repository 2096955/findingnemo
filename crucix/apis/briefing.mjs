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
