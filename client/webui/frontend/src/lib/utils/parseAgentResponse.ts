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
    googleMapsEmbedUrl?: string;
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

    // Extract Google Maps embed URL from google_maps_router output
    for (const block of jsonBlocks) {
        const b = block as Record<string, unknown>;
        if (typeof b.google_maps_embed_url === "string" && b.google_maps_embed_url) {
            result.googleMapsEmbedUrl = b.google_maps_embed_url;
            break;
        }
    }

    return result;
}
