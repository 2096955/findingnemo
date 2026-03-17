import { ScatterplotLayer } from "@deck.gl/layers";
import type { Sighting } from "./MapView";

export interface WhaleMarkerLayerOptions {
    data: Sighting[];
    visible?: boolean;
    onSightingClick?: (info: { object: Sighting }) => void;
}

/**
 * Creates a Deck.gl ScatterplotLayer for whale sighting markers.
 * Circle radius scales with sighting count.
 */
export function createWhaleMarkerLayer({
    data,
    visible = true,
    onSightingClick,
}: WhaleMarkerLayerOptions) {
    return new ScatterplotLayer({
        id: "whale-sightings",
        data,
        visible,
        getPosition: (d: Sighting) => [d.lng, d.lat],
        getRadius: (d: Sighting) => Math.max(d.count * 500, 1000),
        getFillColor: [0, 119, 182, 180],   // ocean blue with transparency
        getLineColor: [0, 0, 0, 255],
        lineWidthMinPixels: 1,
        pickable: true,
        onClick: onSightingClick as ((info: unknown) => void) | undefined,
        autoHighlight: true,
        highlightColor: [0, 95, 138, 220],
    });
}
