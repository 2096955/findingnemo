# Dashboard-to-Gateway Wiring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace all mock/hardcoded data in the Dashboard with live agent responses via the SAM gateway SSE endpoint, achieving full compliance with the Project Resilience whale_agent spec.

**Architecture:** DashboardPage sends a natural-language route query to the orchestrator via `POST /api/v1/message:stream` (same endpoint the chat page uses). It subscribes to SSE events on `/api/v1/sse/subscribe/{taskId}`. Agent responses contain structured JSON blocks (risk scores, GeoJSON routes, alerts) embedded in markdown — a parser utility extracts these into the typed arrays MapView expects.

**Tech Stack:** React + TypeScript (existing), `api` client from `lib/api/client.ts`, `EventSource` for SSE, existing Deck.gl layer components.

---

## Task 1: Create `parseAgentResponse.ts` utility

**Files:**
- Create: `client/webui/frontend/src/lib/utils/parseAgentResponse.ts`

**Step 1: Write the utility**

This module extracts structured data from orchestrator responses. The orchestrator's SYNTHESIZE step calls `map_renderer` which produces GeoJSON FeatureCollections, and `report_generator` which produces markdown with risk scores. The agent response text contains these as JSON code blocks or inline JSON objects.

```typescript
// client/webui/frontend/src/lib/utils/parseAgentResponse.ts
import type { RiskPoint, Sighting, Route } from "@/components/Dashboard/MapView";
import type { RiskSummary, SpeedAlert } from "@/components/Dashboard/Sidebar";

/**
 * Extract all JSON blocks from agent response text.
 * Looks for ```json ... ``` fenced blocks and bare {...} objects.
 */
function extractJsonBlocks(text: string): unknown[] {
    const blocks: unknown[] = [];

    // Fenced code blocks: ```json ... ```
    const fencedRegex = /```(?:json)?\s*\n?([\s\S]*?)```/g;
    let match: RegExpExecArray | null;
    while ((match = fencedRegex.exec(text)) !== null) {
        try {
            blocks.push(JSON.parse(match[1].trim()));
        } catch { /* skip unparseable blocks */ }
    }

    // Bare JSON objects on their own lines (heuristic for tool output)
    const bareRegex = /^\s*(\{[\s\S]*?\})\s*$/gm;
    while ((match = bareRegex.exec(text)) !== null) {
        try {
            const parsed = JSON.parse(match[1]);
            // Avoid duplicates from fenced blocks
            if (!blocks.includes(parsed)) blocks.push(parsed);
        } catch { /* skip */ }
    }

    return blocks;
}

/**
 * Parse a GeoJSON FeatureCollection with render_type "risk_heatmap" into RiskPoint[].
 */
function parseRiskHeatmap(fc: Record<string, unknown>): RiskPoint[] {
    const features = (fc as { features?: Array<Record<string, unknown>> }).features ?? [];
    return features
        .filter((f: Record<string, unknown>) => (f.geometry as Record<string, unknown>)?.type === "Point")
        .map((f: Record<string, unknown>) => {
            const coords = (f.geometry as { coordinates: number[] }).coordinates;
            const props = f.properties as Record<string, number>;
            return { lng: coords[0], lat: coords[1], risk: props.risk ?? props.weight ?? 0.5 };
        });
}

/**
 * Parse a GeoJSON FeatureCollection with render_type "sightings" into Sighting[].
 */
function parseSightings(fc: Record<string, unknown>): Sighting[] {
    const features = (fc as { features?: Array<Record<string, unknown>> }).features ?? [];
    return features
        .filter((f: Record<string, unknown>) => (f.geometry as Record<string, unknown>)?.type === "Point")
        .map((f: Record<string, unknown>) => {
            const coords = (f.geometry as { coordinates: number[] }).coordinates;
            const props = f.properties as Record<string, string | number>;
            return {
                lng: coords[0],
                lat: coords[1],
                species: String(props.species ?? "Unknown"),
                count: Number(props.count ?? 1),
            };
        });
}

/**
 * Parse a GeoJSON FeatureCollection with LineString features into Route[].
 */
function parseRoutes(fc: Record<string, unknown>): Route[] {
    const features = (fc as { features?: Array<Record<string, unknown>> }).features ?? [];
    return features
        .filter((f: Record<string, unknown>) => (f.geometry as Record<string, unknown>)?.type === "LineString")
        .map((f: Record<string, unknown>) => {
            const coords = (f.geometry as { coordinates: [number, number][] }).coordinates;
            return { path: coords }; // Already [lng, lat] from GeoJSON spec
        });
}

/**
 * Extract risk summary numbers from agent text.
 * Looks for patterns like "collision risk: 45%", "fuel impact: +3.2%", "delay: 1.5 hours"
 */
function parseRiskSummary(text: string, jsonBlocks: unknown[]): RiskSummary | null {
    // First try structured JSON from report_generator or risk_scorer
    for (const block of jsonBlocks) {
        const b = block as Record<string, unknown>;
        if (b.collision_risk_score !== undefined || b.collisionProbability !== undefined) {
            return {
                collisionProbability: Number(b.collision_risk_score ?? b.collisionProbability ?? 0) *
                    (Number(b.collision_risk_score ?? 0) <= 1 ? 100 : 1), // normalize 0-1 to 0-100
                fuelImpact: Number(b.fuel_impact_pct ?? b.estimated_fuel_impact_pct ?? b.fuelImpact ?? 0),
                delayHours: Number(b.time_delta_hours ?? b.delayHours ?? 0),
            };
        }
    }

    // Fallback: regex from markdown text
    const riskMatch = text.match(/collision\s*(?:risk|probability)[:\s]*(\d+(?:\.\d+)?)\s*%/i);
    const fuelMatch = text.match(/fuel\s*impact[:\s]*[+\-]?(\d+(?:\.\d+)?)\s*%/i);
    const delayMatch = text.match(/(?:delay|time)[:\s]*(\d+(?:\.\d+)?)\s*h/i);

    if (riskMatch) {
        return {
            collisionProbability: parseFloat(riskMatch[1]),
            fuelImpact: fuelMatch ? parseFloat(fuelMatch[1]) : 0,
            delayHours: delayMatch ? parseFloat(delayMatch[1]) : 0,
        };
    }
    return null;
}

/**
 * Extract speed alerts from agent text.
 * Looks for patterns like "reduce speed to X knots in ZONE" or structured alert data.
 */
function parseAlerts(text: string, jsonBlocks: unknown[]): SpeedAlert[] {
    const alerts: SpeedAlert[] = [];

    // Try structured JSON first
    for (const block of jsonBlocks) {
        const b = block as Record<string, unknown>;
        if (b.recommendation && typeof b.recommendation === "string") {
            const speedMatch = (b.recommendation as string).match(/(\d+)\s*knots/i);
            if (speedMatch) {
                alerts.push({
                    zone: String(b.region ?? b.zone ?? "Risk Zone"),
                    maxSpeed: parseInt(speedMatch[1]),
                    reason: b.recommendation as string,
                });
            }
        }
        if (b.risk_level === "HIGH" || b.risk_level === "CRITICAL") {
            alerts.push({
                zone: String(b.region ?? b.zone ?? "High Risk Area"),
                maxSpeed: b.risk_level === "CRITICAL" ? 8 : 10,
                reason: String(b.recommendation ?? `${b.risk_level} collision risk detected`),
            });
        }
    }

    // Fallback: regex for speed reduction recommendations in markdown
    const speedRegex = /(?:reduce|limit)\s*speed\s*to\s*(\d+)\s*knots.*?(?:in|near|at)\s+([^.\n]+)/gi;
    let match: RegExpExecArray | null;
    while ((match = speedRegex.exec(text)) !== null) {
        alerts.push({
            zone: match[2].trim(),
            maxSpeed: parseInt(match[1]),
            reason: match[0].trim(),
        });
    }

    return alerts;
}

/**
 * Main entry point: parse a full orchestrator response into dashboard state.
 */
export interface ParsedAgentResponse {
    riskData: RiskPoint[];
    sightings: Sighting[];
    routes: Route[];
    shippingLanes: Route[];
    migrationCorridors: Route[];
    riskSummary: RiskSummary | null;
    alerts: SpeedAlert[];
    rawText: string;
}

export function parseAgentResponse(responseText: string): ParsedAgentResponse {
    const jsonBlocks = extractJsonBlocks(responseText);

    const result: ParsedAgentResponse = {
        riskData: [],
        sightings: [],
        routes: [],
        shippingLanes: [],
        migrationCorridors: [],
        riskSummary: null,
        alerts: [],
        rawText: responseText,
    };

    // Classify GeoJSON FeatureCollections by render_type metadata
    for (const block of jsonBlocks) {
        const b = block as Record<string, unknown>;
        if (b.type !== "FeatureCollection") continue;

        const renderType = (b.metadata as Record<string, string>)?.render_type;
        switch (renderType) {
            case "risk_heatmap":
                result.riskData.push(...parseRiskHeatmap(b));
                break;
            case "sightings":
                result.sightings.push(...parseSightings(b));
                break;
            case "route":
                result.routes.push(...parseRoutes(b));
                break;
            case "shipping_lanes":
                result.shippingLanes.push(...parseRoutes(b));
                break;
            case "migration_corridors":
                result.migrationCorridors.push(...parseRoutes(b));
                break;
            default:
                // Try to infer from geometry types
                if ((b as { features?: Array<Record<string, unknown>> }).features?.some(
                    (f: Record<string, unknown>) => (f.geometry as Record<string, unknown>)?.type === "LineString"
                )) {
                    result.routes.push(...parseRoutes(b));
                } else {
                    result.riskData.push(...parseRiskHeatmap(b));
                }
        }
    }

    result.riskSummary = parseRiskSummary(responseText, jsonBlocks);
    result.alerts = parseAlerts(responseText, jsonBlocks);

    return result;
}
```

**Step 2: Commit**

```bash
git add client/webui/frontend/src/lib/utils/parseAgentResponse.ts
git commit -m "feat: add agent response parser for dashboard data extraction"
```

---

## Task 2: Rewrite DashboardPage to use real gateway SSE

**Files:**
- Modify: `client/webui/frontend/src/components/Dashboard/DashboardPage.tsx`

**Step 1: Replace the entire DashboardPage with gateway-connected version**

```typescript
// client/webui/frontend/src/components/Dashboard/DashboardPage.tsx
import React, { useState, useCallback, useRef } from "react";
import { MapView, type LayerVisibility, type RiskPoint, type Sighting, type Route } from "./MapView";
import { Sidebar, type RouteQuery, type RiskSummary, type SpeedAlert } from "./Sidebar";
import { api } from "@/lib/api/client";
import { parseAgentResponse } from "@/lib/utils/parseAgentResponse";

/** Generate a simple UUID v4. */
function uuid(): string {
    return crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/**
 * DashboardPage composes the MapView and Sidebar into a full-width dashboard layout.
 * Sends route planning queries to the SAM gateway orchestrator and populates the map
 * with real agent data via SSE streaming.
 */
export function DashboardPage() {
    // Layer visibility state
    const [layerVisibility, setLayerVisibility] = useState<LayerVisibility>({
        riskHeatmap: true,
        sightings: true,
        shippingLanes: true,
        routes: true,
        migrationCorridors: true,
    });

    // Filter state
    const [selectedSeason, setSelectedSeason] = useState("All Seasons");
    const [selectedSpecies, setSelectedSpecies] = useState("All Species");

    // Data state - populated by agent responses
    const [riskData, setRiskData] = useState<RiskPoint[]>([]);
    const [sightings, setSightings] = useState<Sighting[]>([]);
    const [routes, setRoutes] = useState<Route[]>([]);
    const [shippingLanes, setShippingLanes] = useState<Route[]>([]);
    const [migrationCorridors, setMigrationCorridors] = useState<Route[]>([]);
    const [riskSummary, setRiskSummary] = useState<RiskSummary | null>(null);
    const [alerts, setAlerts] = useState<SpeedAlert[]>([]);
    const [isQuerying, setIsQuerying] = useState(false);
    const [statusText, setStatusText] = useState("");
    const [error, setError] = useState<string | null>(null);

    // Session tracking for multi-turn conversations
    const sessionIdRef = useRef<string>("");
    const eventSourceRef = useRef<EventSource | null>(null);

    /**
     * Build a natural-language query from the route form + filters.
     */
    const buildQuery = useCallback(
        (query: RouteQuery): string => {
            let nl = `Plan a safe shipping route from ${query.originPort} to ${query.destinationPort}`;
            if (query.departureDate) {
                nl += ` departing ${query.departureDate}`;
            }
            nl += `, optimized to minimize whale strike risk.`;

            if (selectedSeason !== "All Seasons") {
                nl += ` Consider ${selectedSeason.toLowerCase()} seasonal conditions.`;
            }
            if (selectedSpecies !== "All Species") {
                nl += ` Focus on ${selectedSpecies} protection.`;
            }

            nl += ` Include risk heatmap data, whale sighting locations, shipping lane traffic, migration corridors, speed reduction recommendations, and fuel/delay impact estimates.`;
            nl += ` Return all map visualization data as GeoJSON FeatureCollections with render_type metadata.`;

            return nl;
        },
        [selectedSeason, selectedSpecies]
    );

    /**
     * Process accumulated response text from SSE events.
     */
    const processResponse = useCallback((fullText: string) => {
        const parsed = parseAgentResponse(fullText);

        if (parsed.riskData.length > 0) setRiskData(parsed.riskData);
        if (parsed.sightings.length > 0) setSightings(parsed.sightings);
        if (parsed.routes.length > 0) setRoutes(parsed.routes);
        if (parsed.shippingLanes.length > 0) setShippingLanes(parsed.shippingLanes);
        if (parsed.migrationCorridors.length > 0) setMigrationCorridors(parsed.migrationCorridors);
        if (parsed.riskSummary) setRiskSummary(parsed.riskSummary);
        if (parsed.alerts.length > 0) setAlerts(parsed.alerts);
    }, []);

    /**
     * Send a route query to the SAM gateway and subscribe to SSE for the response.
     */
    const handleRouteQuery = useCallback(
        async (query: RouteQuery) => {
            // Clean up any existing SSE connection
            if (eventSourceRef.current) {
                eventSourceRef.current.close();
                eventSourceRef.current = null;
            }

            setIsQuerying(true);
            setError(null);
            setStatusText("Sending query to Whale Route Coordinator...");

            const messageText = buildQuery(query);
            const messageId = `msg-${uuid()}`;
            const requestId = `req-${uuid()}`;

            // Build JSON-RPC request matching the chat page pattern
            const sendMessageRequest = {
                jsonrpc: "2.0",
                id: requestId,
                method: "message/stream",
                params: {
                    message: {
                        role: "user",
                        parts: [{ type: "text", text: messageText }],
                        messageId,
                        kind: "message",
                        contextId: sessionIdRef.current || "",
                        metadata: {
                            agent_name: "WhaleRouteCoordinator",
                        },
                    },
                },
            };

            try {
                // POST to gateway - returns taskId for SSE subscription
                const result = await api.webui.post<{
                    jsonrpc: string;
                    id: string;
                    result: {
                        id: string;
                        contextId: string;
                        kind: string;
                        status?: { state: string; message?: unknown };
                    };
                }>("/api/v1/message:stream", sendMessageRequest);

                const taskId = result?.result?.id;
                const newSessionId = result?.result?.contextId;

                if (!taskId) {
                    throw new Error("Gateway did not return a task ID");
                }

                // Store session ID for future queries
                if (newSessionId) {
                    sessionIdRef.current = newSessionId;
                }

                setStatusText("Orchestrator is coordinating specialists...");

                // Subscribe to SSE events for this task
                const sseUrl = api.webui.getFullUrl(`/api/v1/sse/subscribe/${taskId}`);
                const eventSource = new EventSource(sseUrl, { withCredentials: true });
                eventSourceRef.current = eventSource;

                let accumulatedText = "";

                const handleSseEvent = (event: MessageEvent) => {
                    try {
                        const rpcResponse = JSON.parse(event.data);
                        const eventResult = rpcResponse?.result;
                        if (!eventResult) return;

                        // Extract text from message parts
                        const message = eventResult.status?.message;
                        if (message?.parts) {
                            for (const part of message.parts) {
                                if (part.type === "text" && part.text) {
                                    accumulatedText = part.text;
                                } else if (part.type === "data") {
                                    // Agent progress updates
                                    const data = part.data ?? part;
                                    if (data.status_text) {
                                        setStatusText(data.status_text);
                                    }
                                }
                            }
                        }

                        // Check if this is the final event
                        if (eventResult.kind === "task" || eventResult.final === true) {
                            // Process complete response
                            processResponse(accumulatedText);
                            setIsQuerying(false);
                            setStatusText("");
                            eventSource.close();
                            eventSourceRef.current = null;
                        } else if (eventResult.kind === "status-update") {
                            // Intermediate update — try parsing partial results
                            processResponse(accumulatedText);
                            const state = eventResult.status?.state;
                            if (state === "running") {
                                setStatusText("Specialists analyzing data...");
                            }
                        }
                    } catch (err) {
                        console.warn("Failed to parse SSE event:", err);
                    }
                };

                eventSource.addEventListener("status_update", handleSseEvent);
                eventSource.addEventListener("artifact_update", handleSseEvent);
                eventSource.addEventListener("final_response", handleSseEvent);

                eventSource.addEventListener("error", () => {
                    // EventSource auto-reconnects on error, but if it closes we finalize
                    if (eventSource.readyState === EventSource.CLOSED) {
                        if (accumulatedText) {
                            processResponse(accumulatedText);
                        }
                        setIsQuerying(false);
                        setStatusText("");
                        eventSourceRef.current = null;
                    }
                });
            } catch (err) {
                const message = err instanceof Error ? err.message : "Failed to connect to gateway";
                setError(message);
                setIsQuerying(false);
                setStatusText("");
            }
        },
        [buildQuery, processResponse]
    );

    return (
        <div className="flex h-full w-full">
            <Sidebar
                onRouteQuery={handleRouteQuery}
                riskSummary={riskSummary}
                alerts={alerts}
                layerVisibility={layerVisibility}
                onLayerVisibilityChange={setLayerVisibility}
                isQuerying={isQuerying}
                selectedSeason={selectedSeason}
                onSeasonChange={setSelectedSeason}
                selectedSpecies={selectedSpecies}
                onSpeciesChange={setSelectedSpecies}
            />
            <div className="relative flex-1">
                {/* Status overlay */}
                {(statusText || error) && (
                    <div className="absolute left-4 top-4 z-10 max-w-sm rounded-lg bg-background/90 px-4 py-2 shadow-lg backdrop-blur-sm"
                         style={{ borderColor: "var(--border)", border: "1px solid" }}>
                        {error ? (
                            <p className="text-sm" style={{ color: "var(--destructive)" }}>{error}</p>
                        ) : (
                            <div className="flex items-center gap-2">
                                <div className="h-2 w-2 animate-pulse rounded-full" style={{ backgroundColor: "var(--primary)" }} />
                                <p className="text-sm text-muted-foreground">{statusText}</p>
                            </div>
                        )}
                    </div>
                )}
                <MapView
                    riskData={riskData}
                    sightings={sightings}
                    routes={routes}
                    shippingLanes={shippingLanes}
                    migrationCorridors={migrationCorridors}
                    layerVisibility={layerVisibility}
                />
            </div>
        </div>
    );
}
```

**Step 2: Commit**

```bash
git add client/webui/frontend/src/components/Dashboard/DashboardPage.tsx
git commit -m "feat: wire DashboardPage to SAM gateway SSE — replace all mocks with live agent data"
```

---

## Task 3: Update orchestrator to include structured JSON in responses

**Files:**
- Modify: `configs/agents/orchestrator.yaml` (lines 66-70, STEP 4 SYNTHESIZE)

**Step 1: Add instruction for structured output**

Append to the STEP 4 — SYNTHESIZE section in the orchestrator instruction:

```yaml
        **STEP 4 — SYNTHESIZE**
        Call report_generator with collected evidence. Choose mode:
        - Route planning → "route_recommendation"
        - Risk inquiry → "risk_assessment"
        - Simple factual → "quick_answer"
        Then call map_renderer to generate visualization layers for the dashboard.

        IMPORTANT: In your final response, include ALL map_renderer GeoJSON outputs
        as fenced JSON code blocks (```json ... ```) so the dashboard can parse them.
        Include separate FeatureCollections for each layer: risk_heatmap, route,
        sightings, shipping_lanes, migration_corridors.
        Also include a summary JSON block with collision_risk_score (0-1),
        fuel_impact_pct, time_delta_hours, and any speed reduction recommendations.
```

**Step 2: Update STEP 6 PERSIST to include C/A/O data**

```yaml
        **STEP 6 — PERSIST**
        Call memory_plane with operation="flush_cold", query=<original question>,
        and specialists_used=<comma-separated list of specialists that responded>.
```

**Step 3: Commit**

```bash
git add configs/agents/orchestrator.yaml
git commit -m "feat: instruct orchestrator to output structured JSON for dashboard consumption"
```

---

## Task 4: Add Sidebar status text and error display

**Files:**
- Modify: `client/webui/frontend/src/components/Dashboard/Sidebar.tsx`

**Step 1: Add statusText prop to SidebarProps**

Add to the interface:
```typescript
    statusText?: string;
    error?: string | null;
```

Update the component signature to accept them. Add a status section below the submit button:

```typescript
{isQuerying && statusText && (
    <p className="mt-2 text-xs text-muted-foreground animate-pulse">{statusText}</p>
)}
{error && (
    <p className="mt-2 text-xs" style={{ color: "var(--destructive)" }}>{error}</p>
)}
```

**Step 2: Commit**

```bash
git add client/webui/frontend/src/components/Dashboard/Sidebar.tsx
git commit -m "feat: add query status and error display to dashboard sidebar"
```

---

## Summary

| Task | What changes | Why |
|------|-------------|-----|
| 1 | New `parseAgentResponse.ts` | Translates map_renderer GeoJSON FeatureCollections + risk scorer output into MapView's flat array types |
| 2 | Rewrite `DashboardPage.tsx` | Replaces setTimeout mock with real `POST /api/v1/message:stream` + `EventSource` SSE subscription |
| 3 | Update `orchestrator.yaml` | Instructs orchestrator to include JSON code blocks in responses so parser can extract map data |
| 4 | Update `Sidebar.tsx` | Shows real-time status and errors during agent queries |

**No mocks. No hardcoded data.** Season/species filters are injected into the natural-language query, which the orchestrator passes to query_decomposer for specialist routing. The C/A/O persist step is wired via the orchestrator's existing STEP 6 flush_cold instruction.
