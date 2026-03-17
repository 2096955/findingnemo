import { PathLayer } from "@deck.gl/layers";
import type { Route } from "./MapView";

export interface ShippingLaneLayerOptions {
    data: Route[];
    visible?: boolean;
}

/**
 * Creates a Deck.gl PathLayer for shipping lanes.
 * Semi-transparent gray lines showing established vessel routes.
 */
export function createShippingLaneLayer({
    data,
    visible = true,
}: ShippingLaneLayerOptions) {
    return new PathLayer({
        id: "shipping-lanes",
        data,
        visible,
        getPath: (d: Route) => d.path,
        getColor: [128, 128, 128, 100],
        getWidth: 2000,
        widthMinPixels: 1,
        capRounded: true,
        jointRounded: true,
    });
}
