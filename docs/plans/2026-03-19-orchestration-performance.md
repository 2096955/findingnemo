# Orchestration Performance Optimisation

**Date:** 2026-03-19
**Status:** Complete
**Target:** Reduce typical query response time from ~2-5 min to ~60-90s

## Problem

The 7-step orchestration protocol (seed → web_intelligence → delegate → collect → synthesize → verify → persist → respond) takes 2-5 minutes per query. The critical path is dominated by sequential LLM calls and an unnecessarily expensive verification step.

## Phases (implemented incrementally, each deployed and tested before next)

### Phase 1: Verifier Pro → Flash

**File:** `configs/shared_config.yaml` line 28

Change `verifier_model` from `vertex_ai/gemini-2.5-pro` to `vertex_ai/gemini-2.5-flash`.

**Rationale:** Verification is structured comparison (does risk score match evidence?). Flash handles this. Pro's extra reasoning is overkill.

**Saving:** 15-30s per query.

### Phase 2: Conditional Verify

**File:** `configs/agents/orchestrator.yaml` — Step 5 instruction

Add a confidence gate after synthesis:
- confidence >= 0.8 → skip verify/revise, proceed to Step 6
- confidence < 0.8 → delegate to peer_Verifier as normal

High confidence: well-known routes, all specialists responded with consistent data, no MCP failures.
Low confidence: novel regions, conflicting data, chokepoint closures, missing MCP data.

**Saving:** 20-40s on ~70% of queries.

### Phase 3: Selective Specialist Delegation

**File:** `configs/agents/orchestrator.yaml` — Step 2 instruction

Replace "Call ALL agents in a SINGLE response" with selective delegation:

**Always called (core pipeline):**
- RouteOptimizer
- RiskAnalyst
- MarineEcologySpecialist

**User opts in via natural language:**
- WeatherAnalyst — triggered when user mentions weather, storms, season concerns
- VesselTrafficMonitor — triggered when user mentions traffic, congestion, vessels
- SpeciesIdentifier — triggered when user asks about specific species or conservation

**Fallback:** If query is complex (multiple chokepoints, unusual region) or the orchestrator is uncertain, call all 6.

No UI changes. The orchestrator scans the user's message for concern signals.

### Phase 4: Parallel web_intelligence + Delegation

**File:** `configs/agents/orchestrator.yaml` — Steps 1+2 instruction

Currently sequential: web_intelligence → wait → delegate specialists.

Change to parallel: call web_intelligence AND selected specialists in the same LLM turn. SAM's `parallel_tool_calls: true` executes them simultaneously.

If web_intelligence returns a CRITICAL alert after specialists have started, the orchestrator sends a targeted follow-up to RouteOptimizer with exclusion zones. This only triggers on rare CRITICAL cases.

**Saving:** 5-15s on every query.

## Expected Combined Result

| Metric | Before | After (Phases 1-4) |
|--------|--------|---------------------|
| Typical route query | 2-5 min | 60-90s |
| Complex/chokepoint query | 3-5 min | 90-150s |
| Verifier model | gemini-2.5-pro | gemini-2.5-flash |
| Specialists per query | 6 (always) | 3 core + user opt-in |
| web_intelligence | Sequential | Parallel with delegation |

## Testing

Each phase is verified by running the full Playwright E2E suite (9 tests). The key timing benchmarks:
- Chat API test: currently 5.1m → target under 2m
- Dashboard Form test: currently 2.3m → target under 90s
- Streaming UX test: currently 3.2m → target under 2m

## Actual Results (v14 — 2026-03-20)

Full suite: **9/9 passed** (13.0m total, single worker).

| Test | Before (v10) | After (v14) | Delta |
|------|-------------|-------------|-------|
| Chat API | 5.1m | 5.1m | +0s |
| Dashboard Form | 2.3m | 2.7m | +24s |
| Streaming UX | 3.2m | 2.1m | **-1.1m** |

### Analysis

The 60-90s target was not met. Streaming UX improved meaningfully (-1.1m), but
Chat API showed no change and Dashboard Form regressed slightly. Contributing
factors:

1. **Instruction-level optimisations are non-deterministic.** The orchestrator
   LLM does not always follow the confidence gate or selective delegation paths
   — it still sometimes calls all 6 specialists and runs verification regardless.
2. **Single-run variance.** Tests hit a shared Cloud Run instance; cold starts,
   concurrent load, and Vertex AI latency fluctuations can swing timings by
   30-60s between runs.
3. **Bottleneck is specialist LLM latency, not orchestration logic.** Even with
   parallel dispatch, the slowest specialist (typically RouteOptimizer or
   RiskAssessor) dominates wall-clock time.

### Next steps to reach 60-90s target

- **Streaming response** — start delivering partial results while specialists
  are still running (requires gateway changes, not config-only).
- **Specialist model downgrade** — move RouteOptimizer/RiskAssessor from Pro to
  Flash for simple routes.
- **Caching** — cache specialist responses for repeated port pairs within a
  time window.
- **Multiple test runs** — average 3-5 runs to separate signal from noise.
