// client/webui/frontend/src/components/Dashboard/DashboardPage.tsx
import { useState, useCallback, useRef } from "react";
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
