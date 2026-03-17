import { PathLayer } from "@deck.gl/layers";
import type { Route } from "./MapView";

export interface MigrationCorridorLayerOptions {
    data: Route[];
    visible?: boolean;
}

/**
 * Creates a Deck.gl PathLayer for whale migration corridors.
 * Semi-transparent indigo dashed lines showing known migration paths.
 */
export function createMigrationCorridorLayer({
    data,
    visible = true,
}: MigrationCorridorLayerOptions) {
    return new PathLayer({
        id: "migration-corridors",
        data,
        visible,
        getPath: (d: Route) => d.path,
        getColor: [99, 102, 241, 120],  // indigo with transparency
        getWidth: 5000,
        widthMinPixels: 3,
        getDashArray: [8, 4],
        capRounded: true,
        jointRounded: true,
    });
}
