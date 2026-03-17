import { PathLayer } from "@deck.gl/layers";
import type { Route } from "./MapView";

export interface RouteLayerOptions {
    data: Route[];
    visible?: boolean;
}

/**
 * Creates a Deck.gl PathLayer for recommended whale-safe routes.
 * Green solid line showing the optimized path.
 */
export function createRouteLayer({
    data,
    visible = true,
}: RouteLayerOptions) {
    return new PathLayer({
        id: "recommended-route",
        data,
        visible,
        getPath: (d: Route) => d.path,
        getColor: [16, 185, 129, 255],  // emerald green
        getWidth: 3000,
        widthMinPixels: 2,
        capRounded: true,
        jointRounded: true,
    });
}
