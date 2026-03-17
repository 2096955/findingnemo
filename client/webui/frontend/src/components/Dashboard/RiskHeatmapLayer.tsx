import { HeatmapLayer } from "@deck.gl/aggregation-layers";
import type { RiskPoint } from "./MapView";

export interface RiskHeatmapLayerOptions {
    data: RiskPoint[];
    visible?: boolean;
    radiusPixels?: number;
    intensity?: number;
    threshold?: number;
}

/**
 * Creates a Deck.gl HeatmapLayer for whale strike risk zones.
 * Colors range from cool (low risk) to hot (high risk).
 */
export function createRiskHeatmapLayer({
    data,
    visible = true,
    radiusPixels = 60,
    intensity = 1,
    threshold = 0.1,
}: RiskHeatmapLayerOptions) {
    return new HeatmapLayer({
        id: "risk-heatmap",
        data,
        visible,
        getPosition: (d: RiskPoint) => [d.lng, d.lat],
        getWeight: (d: RiskPoint) => d.risk,
        radiusPixels,
        intensity,
        threshold,
        colorRange: [
            [65, 182, 196],   // low risk - teal
            [127, 205, 187],  // low-medium
            [199, 233, 180],  // medium-low
            [255, 255, 204],  // medium
            [254, 178, 76],   // medium-high
            [240, 59, 32],    // high risk - red
        ],
    });
}
