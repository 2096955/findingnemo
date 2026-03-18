// client/webui/frontend/src/components/Dashboard/DashboardPage.tsx
import { useState, useCallback, useRef } from "react";
import { MapView, type LayerVisibility, type RiskPoint, type Sighting, type Route } from "./MapView";
import { Sidebar, type RouteQuery, type RiskSummary, type SpeedAlert } from "./Sidebar";
import { GoogleMapsEmbed } from "./GoogleMapsEmbed";
import { api } from "@/lib/api/client";
import { parseAgentResponse } from "@/lib/utils/parseAgentResponse";
import { useDashboardData } from "@/lib/hooks";

/** Generate a simple UUID v4. */
function uuid(): string {
    return crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/**
 * DashboardPage composes the MapView and Sidebar into a full-width dashboard layout.
 * Sends route planning queries to the SAM gateway orchestrator and populates the map
 * with real agent data via SSE streaming.
 *
 * Also consumes shared data from ChatProvider — when a chat response contains GeoJSON
 * map layers, they are automatically pushed here via DashboardDataContext.
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

    // Data state - populated by agent responses (local queries)
    const [localRiskData, setLocalRiskData] = useState<RiskPoint[]>([]);
    const [localSightings, setLocalSightings] = useState<Sighting[]>([]);
    const [localRoutes, setLocalRoutes] = useState<Route[]>([]);
    const [localShippingLanes, setLocalShippingLanes] = useState<Route[]>([]);
    const [localMigrationCorridors, setLocalMigrationCorridors] = useState<Route[]>([]);
    const [localRiskSummary, setLocalRiskSummary] = useState<RiskSummary | null>(null);
    const [localAlerts, setLocalAlerts] = useState<SpeedAlert[]>([]);
    const [localGoogleMapsEmbedUrl, setLocalGoogleMapsEmbedUrl] = useState("");
    const [isQuerying, setIsQuerying] = useState(false);
    const [statusText, setStatusText] = useState("");
    const [error, setError] = useState<string | null>(null);

    // Map tab state
    const [activeMapTab, setActiveMapTab] = useState<"whale-layers" | "google-route">("whale-layers");
    const [lastOriginPort, setLastOriginPort] = useState("");
    const [lastDestPort, setLastDestPort] = useState("");

    // Shared data from chat responses
    const { chatDashboardData } = useDashboardData();

    // Merge: local query data takes priority; fall back to chat data
    const riskData = localRiskData.length > 0 ? localRiskData : (chatDashboardData?.riskData ?? []);
    const sightings = localSightings.length > 0 ? localSightings : (chatDashboardData?.sightings ?? []);
    const routes = localRoutes.length > 0 ? localRoutes : (chatDashboardData?.routes ?? []);
    const shippingLanes = localShippingLanes.length > 0 ? localShippingLanes : (chatDashboardData?.shippingLanes ?? []);
    const migrationCorridors = localMigrationCorridors.length > 0 ? localMigrationCorridors : (chatDashboardData?.migrationCorridors ?? []);
    const riskSummary = localRiskSummary ?? chatDashboardData?.riskSummary ?? null;
    const alerts = localAlerts.length > 0 ? localAlerts : (chatDashboardData?.alerts ?? []);
    const googleMapsEmbedUrl = localGoogleMapsEmbedUrl || chatDashboardData?.googleMapsEmbedUrl || "";

    // Track whether we're showing chat data (for the status banner)
    const hasChatData = chatDashboardData !== null && (
        (chatDashboardData.riskData.length > 0 || chatDashboardData.sightings.length > 0
            || chatDashboardData.routes.length > 0 || chatDashboardData.riskSummary !== null)
    );
    const isShowingChatData = hasChatData && localRiskData.length === 0 && localRoutes.length === 0;

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

        if (parsed.riskData.length > 0) setLocalRiskData(parsed.riskData);
        if (parsed.sightings.length > 0) setLocalSightings(parsed.sightings);
        if (parsed.routes.length > 0) setLocalRoutes(parsed.routes);
        if (parsed.shippingLanes.length > 0) setLocalShippingLanes(parsed.shippingLanes);
        if (parsed.migrationCorridors.length > 0) setLocalMigrationCorridors(parsed.migrationCorridors);
        if (parsed.riskSummary) setLocalRiskSummary(parsed.riskSummary);
        if (parsed.alerts.length > 0) setLocalAlerts(parsed.alerts);
        if (parsed.googleMapsEmbedUrl) setLocalGoogleMapsEmbedUrl(parsed.googleMapsEmbedUrl);
    }, []);

    /**
     * Send a route query to the SAM gateway and subscribe to SSE for the response.
     */
    const handleRouteQuery = useCallback(
        async (query: RouteQuery) => {
            // Track port names for Google Maps embed
            setLastOriginPort(query.originPort);
            setLastDestPort(query.destinationPort);

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
                {(statusText || error || isShowingChatData) && (
                    <div className="absolute left-4 top-4 z-10 max-w-sm rounded-lg bg-background/90 px-4 py-2 shadow-lg backdrop-blur-sm"
                         style={{ borderColor: "var(--border)", border: "1px solid" }}>
                        {error ? (
                            <p className="text-sm" style={{ color: "var(--destructive)" }}>{error}</p>
                        ) : statusText ? (
                            <div className="flex items-center gap-2">
                                <div className="h-2 w-2 animate-pulse rounded-full" style={{ backgroundColor: "var(--primary)" }} />
                                <p className="text-sm text-muted-foreground">{statusText}</p>
                            </div>
                        ) : isShowingChatData ? (
                            <div className="flex items-center gap-2">
                                <div className="h-2 w-2 rounded-full" style={{ backgroundColor: "var(--primary)" }} />
                                <p className="text-sm text-muted-foreground">Showing data from chat query</p>
                            </div>
                        ) : null}
                    </div>
                )}

                {/* Map tab switcher */}
                <div className="absolute right-4 top-4 z-10 flex gap-1 rounded-lg bg-background/90 p-1 shadow-lg backdrop-blur-sm"
                     role="tablist" aria-label="Map view"
                     style={{ borderColor: "var(--border)", border: "1px solid" }}>
                    <button
                        role="tab"
                        aria-selected={activeMapTab === "whale-layers"}
                        aria-controls="panel-whale-layers"
                        onClick={() => setActiveMapTab("whale-layers")}
                        className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                            activeMapTab === "whale-layers"
                                ? "bg-primary text-primary-foreground"
                                : "text-muted-foreground hover:text-foreground"
                        }`}
                    >
                        Whale Layers
                    </button>
                    <button
                        role="tab"
                        aria-selected={activeMapTab === "google-route"}
                        aria-controls="panel-google-route"
                        onClick={() => setActiveMapTab("google-route")}
                        className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                            activeMapTab === "google-route"
                                ? "bg-primary text-primary-foreground"
                                : "text-muted-foreground hover:text-foreground"
                        }`}
                    >
                        Google Route
                    </button>
                </div>

                {activeMapTab === "whale-layers" ? (
                    <MapView
                        riskData={riskData}
                        sightings={sightings}
                        routes={routes}
                        shippingLanes={shippingLanes}
                        migrationCorridors={migrationCorridors}
                        layerVisibility={layerVisibility}
                    />
                ) : (
                    <GoogleMapsEmbed
                        embedUrl={googleMapsEmbedUrl}
                        origin={lastOriginPort}
                        destination={lastDestPort}
                    />
                )}
            </div>
        </div>
    );
}
