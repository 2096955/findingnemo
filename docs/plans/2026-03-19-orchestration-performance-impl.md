# Orchestration Performance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce orchestration response time from 2-5 min to 60-90s through 4 incremental phases.

**Architecture:** Config-only changes — switch verifier model, rewrite orchestrator instruction to add confidence gate, selective delegation, and parallel tool calls. No Python code changes. Each phase is a separate commit, deployed and tested independently.

**Tech Stack:** YAML config (SAM agent configs), Playwright E2E tests, Cloud Build + Cloud Run deployment.

---

### Task 1: Phase 1 — Switch Verifier from Pro to Flash

**Files:**
- Modify: `configs/shared_config.yaml:28`

**Step 1: Make the change**

In `configs/shared_config.yaml`, change line 28 from:
```yaml
        model: ${LLM_VERIFIER_MODEL, vertex_ai/gemini-2.5-pro}
```
to:
```yaml
        model: ${LLM_VERIFIER_MODEL, vertex_ai/gemini-2.5-flash}
```

**Step 2: Commit**

```bash
git add configs/shared_config.yaml
git commit -m "perf: switch verifier from gemini-2.5-pro to flash"
```

**Step 3: Build and deploy**

```bash
gcloud builds submit --config cloudbuild.yaml --substitutions _TAG=v11 . --project gbg-neuro
gcloud run services replace infra/cloudrun-service.yaml --region us-central1 --project gbg-neuro
```

Wait 120s for cold start, then seed prompts externally (auto-seed still broken).

**Step 4: Run Playwright suite and record timing**

```bash
cd tests/e2e && npx playwright test --reporter=list
```

Expected: 9/9 pass. Record the timing for:
- "Chat API" test (was 5.1m)
- "Dashboard Form" test (was 2.3m)
- "Streaming UX" test (was 3.2m)

Target: measurable improvement (15-30s faster on each).

---

### Task 2: Phase 2 — Conditional Verify (confidence gate)

**Files:**
- Modify: `configs/agents/orchestrator.yaml:161-163` (Step 5 instruction)

**Step 1: Rewrite Step 5 in orchestrator instruction**

Replace the current Step 5 block (lines 161-163):
```yaml
        **STEP 5 — VERIFY + REVISE**
        Delegate draft to peer_Verifier. If CRITICAL_ISSUES → delegate to
        peer_Reviser, then re-verify once. MINOR_ISSUES → proceed as-is.
```

With:
```yaml
        **STEP 5 — VERIFY + REVISE (CONDITIONAL)**
        After synthesis, assess your confidence in the response on a 0-1 scale:
        - All specialists responded with consistent, source-backed data → HIGH (0.8+)
        - Well-known route (ports in reference table), no MCP failures → HIGH (0.8+)
        - Novel region, conflicting specialist data, MCP failures, chokepoint
          closures, or missing coverage → LOW (< 0.8)

        If confidence >= 0.8: SKIP verification. Proceed directly to Step 6.
        If confidence < 0.8: Delegate draft to peer_Verifier.
          If CRITICAL_ISSUES → delegate to peer_Reviser, then re-verify once.
          MINOR_ISSUES → proceed as-is.
```

**Step 2: Commit**

```bash
git add configs/agents/orchestrator.yaml
git commit -m "perf: conditional verify — skip when confidence >= 0.8"
```

**Step 3: Build, deploy, seed, test**

Same as Task 1 Steps 3-4. Use `_TAG=v12`.

Target: Dashboard Form test drops below 2m. Chat API test drops below 4m.

---

### Task 3: Phase 3 — Selective specialist delegation

**Files:**
- Modify: `configs/agents/orchestrator.yaml:108-122` (Step 2 instruction)

**Step 1: Rewrite Step 2 in orchestrator instruction**

Replace the current Step 2 block (lines 108-122):
```yaml
        **STEP 2 — DELEGATE (PARALLEL)**
        Call ONLY the peer tools listed in all_agents. Call ALL agents in a SINGLE
        response — ADK executes them in parallel.

        When delegating to peer_RouteOptimizer, include any exclusion zones from
        STEP 1 in your message. The RouteOptimizer will use alternative waypoints
        to avoid those regions.

        Available specialists (call ONLY those in all_agents):
        - peer_RouteOptimizer — route calculation and optimization
        - peer_RiskAssessor — collision risk scoring and historical incident analysis
        - peer_WeatherAnalyst — marine weather and ocean conditions
        - peer_VesselTrafficMonitor — AIS vessel traffic data
        - peer_MarineEcologySpecialist — migration patterns and habitat hotspots
        - peer_SpeciesIdentifier — species identification and conservation status
```

With:
```yaml
        **STEP 2 — DELEGATE (SELECTIVE)**
        Call selected specialists in a SINGLE response — SAM executes them in
        parallel. When delegating to peer_RouteOptimizer, include any exclusion
        zones from STEP 1.

        CORE SPECIALISTS (always call these):
        - peer_RouteOptimizer — route calculation and optimization
        - peer_RiskAssessor — collision risk scoring and historical incident analysis
        - peer_MarineEcologySpecialist — migration patterns and habitat hotspots

        OPTIONAL SPECIALISTS (call ONLY if user's message signals the need):
        - peer_WeatherAnalyst — call if user mentions weather, storms, monsoon,
          season concerns, or if web_intelligence flagged a weather hazard
        - peer_VesselTrafficMonitor — call if user mentions traffic, congestion,
          busy lanes, vessel density, or AIS data
        - peer_SpeciesIdentifier — call if user asks about specific species,
          conservation status, endangered species, or IUCN data

        FALLBACK: If the query involves multiple chokepoints, an unusual region
        not in the reference table, or you are uncertain which specialists are
        needed, call ALL 6 specialists.
```

**Step 2: Commit**

```bash
git add configs/agents/orchestrator.yaml
git commit -m "perf: selective specialist delegation — 3 core + user opt-in"
```

**Step 3: Build, deploy, seed, test**

Same as Task 1 Steps 3-4. Use `_TAG=v13`.

Target: Dashboard Form test under 90s. Chat API test under 3m.

**Step 4: Verify opt-in works**

Manually test via the API that mentioning "weather" triggers WeatherAnalyst:
```bash
curl -s -X POST "$URL/api/v1/message:stream" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"weather-test","method":"message/stream","params":{"message":{"role":"user","parts":[{"type":"text","text":"Plan SF to LA route — worried about storm season weather"}],"messageId":"weather-test","kind":"message","contextId":"","metadata":{"agent_name":"WhaleRouteCoordinator"}}}}'
```

Poll the task and check the response mentions weather/storm data from WeatherAnalyst.

---

### Task 4: Phase 4 — Parallel web_intelligence + delegation

**Files:**
- Modify: `configs/agents/orchestrator.yaml:59-106` (Steps 0+1 instruction)
- Modify: `configs/agents/orchestrator.yaml` (Step 2 — merge with Step 1)

**Step 1: Merge Steps 0, 1, and 2 into a single parallel call**

Replace Steps 0, 1, and 2 (lines 59-122 after previous edits) with:

```yaml
        **STEP 1 — SEED + GATHER + DELEGATE (PARALLEL)**
        In a SINGLE response, call ALL of the following tools simultaneously:

        1. memory_plane with operation="seed_session" and query=<question>
        2. web_intelligence with route_description derived from the user's question
        3. The selected specialist peers (see SPECIALIST SELECTION below)

        SAM executes all tool calls in parallel (parallel_tool_calls is enabled).

        SPECIALIST SELECTION:
        CORE (always call):
        - peer_RouteOptimizer — include origin/dest coordinates from reference
          table and any known exclusion zones in your message
        - peer_RiskAssessor — collision risk scoring and historical incident analysis
        - peer_MarineEcologySpecialist — migration patterns and habitat hotspots

        OPTIONAL (call ONLY if user's message signals the need):
        - peer_WeatherAnalyst — user mentions weather, storms, monsoon, season
        - peer_VesselTrafficMonitor — user mentions traffic, congestion, vessels
        - peer_SpeciesIdentifier — user asks about species, conservation, IUCN

        FALLBACK: If uncertain or query involves multiple chokepoints, call all 6.

        **STEP 2 — THREAT CHECK + COLLECT**
        After all parallel calls return:
        1. Check web_intelligence results for HIGH/CRITICAL threats
        2. If CRITICAL threat affects the route AND RouteOptimizer did not account
           for it (because it ran in parallel): send ONE targeted follow-up to
           peer_RouteOptimizer with exclusion zones. Otherwise, proceed.
        3. Store specialists_used and coverage in memory_plane (namespace: intermediate)
        4. If coverage < 70%, send ONE targeted follow-up, then proceed regardless

        CRITICAL — CHOKEPOINT BOTTLENECK LOGIC:
        (keep existing bottleneck map and logic unchanged)
```

Also renumber remaining steps: Step 3 = SYNTHESIZE, Step 4 = VERIFY (conditional), Step 5 = PERSIST, Step 6 = RESPOND.

**Step 2: Commit**

```bash
git add configs/agents/orchestrator.yaml
git commit -m "perf: parallel web_intelligence + delegation in single tool call"
```

**Step 3: Build, deploy, seed, test**

Same as Task 1 Steps 3-4. Use `_TAG=v14`.

Target: Dashboard Form test under 90s. Chat API test under 2m. Streaming UX under 2m.

---

### Task 5: Final verification — full suite + timing report

**Step 1: Run full Playwright suite**

```bash
cd tests/e2e && npx playwright test --reporter=list
```

Expected: 9/9 pass.

**Step 2: Record final timings and compare**

| Test | Before (v10) | After (v14) | Delta |
|------|-------------|-------------|-------|
| Chat API | 5.1m | ? | ? |
| Dashboard Form | 2.3m | ? | ? |
| Streaming UX | 3.2m | ? | ? |

**Step 3: Update design doc with actual results**

Edit `docs/plans/2026-03-19-orchestration-performance.md` to add actual measured timings.

**Step 4: Commit**

```bash
git add docs/plans/2026-03-19-orchestration-performance.md
git commit -m "docs: record actual performance results after phases 1-4"
```
