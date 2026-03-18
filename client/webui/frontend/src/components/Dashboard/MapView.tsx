import { useState, useCallback, useMemo, useEffect, useRef } from "react";
import Map from "react-map-gl/maplibre";
import DeckGL from "@deck.gl/react";
import "maplibre-gl/dist/maplibre-gl.css";
import { createRiskHeatmapLayer } from "./RiskHeatmapLayer";
import { createWhaleMarkerLayer } from "./WhaleMarkerLayer";
import { createShippingLaneLayer } from "./ShippingLaneLayer";
import { createRouteLayer } from "./RouteLayer";
import { createMigrationCorridorLayer } from "./MigrationCorridorLayer";

const INITIAL_VIEW_STATE = {
    latitude: 37.8,
    longitude: -122.4,
    zoom: 4,
    pitch: 30,
    bearing: 0,
};

export interface RiskPoint {
    lat: number;
    lng: number;
    risk: number;
}

export interface Sighting {
    lat: number;
    lng: number;
    species: string;
    count: number;
}

export interface Route {
    path: [number, number][];
}

export interface LayerVisibility {
    riskHeatmap: boolean;
    sightings: boolean;
    shippingLanes: boolean;
    routes: boolean;
    migrationCorridors: boolean;
}

interface MapViewProps {
    riskData?: RiskPoint[];
    sightings?: Sighting[];
    routes?: Route[];
    shippingLanes?: Route[];
    migrationCorridors?: Route[];
    layerVisibility?: LayerVisibility;
    onSightingClick?: (info: { object: Sighting }) => void;
}

const DEFAULT_VISIBILITY: LayerVisibility = {
    riskHeatmap: true,
    sightings: true,
    shippingLanes: true,
    routes: true,
    migrationCorridors: true,
};

export function MapView({
    riskData = [],
    sightings = [],
    routes = [],
    shippingLanes = [],
    migrationCorridors = [],
    layerVisibility = DEFAULT_VISIBILITY,
    onSightingClick,
}: MapViewProps) {
    const [viewState, setViewState] = useState(INITIAL_VIEW_STATE);
    const hasFitted = useRef(false);

    // Auto-fit map to data bounds when route data arrives
    useEffect(() => {
        if (hasFitted.current) return;
        // Only fit once routes are present — avoid fitting to partial risk-only data
        if (routes.length === 0 && shippingLanes.length === 0 && migrationCorridors.length === 0) return;

        // Collect all coordinates from every data source (iterative to avoid stack overflow)
        let minLng = Infinity, maxLng = -Infinity;
        let minLat = Infinity, maxLat = -Infinity;
        let count = 0;

        const push = (lng: number, lat: number) => {
            if (lng < minLng) minLng = lng;
            if (lng > maxLng) maxLng = lng;
            if (lat < minLat) minLat = lat;
            if (lat > maxLat) maxLat = lat;
            count++;
        };

        for (const r of routes) { for (const [lng, lat] of r.path) push(lng, lat); }
        for (const r of shippingLanes) { for (const [lng, lat] of r.path) push(lng, lat); }
        for (const r of migrationCorridors) { for (const [lng, lat] of r.path) push(lng, lat); }
        for (const p of riskData) push(p.lng, p.lat);
        for (const s of sightings) push(s.lng, s.lat);

        if (count < 2) return;

        // Handle antimeridian crossing: if the longitude span > 180°,
        // the route crosses the date line — shift the western edge east by 360°
        if (maxLng - minLng > 180) {
            minLng += 360;
            // Swap so min < max after the shift
            [minLng, maxLng] = [maxLng, minLng];
        }

        const rawCenterLng = (minLng + maxLng) / 2;
        // Normalize center longitude to [-180, 180]
        const centerLng = ((rawCenterLng + 540) % 360) - 180;
        const centerLat = (minLat + maxLat) / 2;
        const spanLng = Math.max(maxLng - minLng, 1);
        const spanLat = Math.max(maxLat - minLat, 1);
        const zoom = Math.max(0, Math.min(12,
            Math.log2(360 / Math.max(spanLng, spanLat)) - 1
        ));

        setViewState(prev => ({ ...prev, latitude: centerLat, longitude: centerLng, zoom }));
        hasFitted.current = true;
    }, [routes, shippingLanes, migrationCorridors, riskData, sightings]);

    const handleViewStateChange = useCallback(({ viewState: vs }: { viewState: unknown }) => {
        setViewState(vs as typeof INITIAL_VIEW_STATE);
    }, []);

    const getTooltip = useCallback(({ object }: { object?: Sighting }) => {
        if (!object) return null;
        return {
            html: `<div style="padding: 8px; font-family: sans-serif;">
                <strong>${object.species}</strong><br/>
                Count: ${object.count}<br/>
                Location: ${object.lat.toFixed(3)}, ${object.lng.toFixed(3)}
            </div>`,
            style: {
                backgroundColor: "#1B3A4B",
                color: "#fff",
                borderRadius: "6px",
                fontSize: "12px",
            },
        };
    }, []);

    const layers = useMemo(() => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const result: any[] = [];

        if (layerVisibility.riskHeatmap && riskData.length > 0) {
            result.push(createRiskHeatmapLayer({ data: riskData }));
        }

        if (layerVisibility.sightings && sightings.length > 0) {
            result.push(createWhaleMarkerLayer({ data: sightings, onSightingClick }));
        }

        if (layerVisibility.shippingLanes && shippingLanes.length > 0) {
            result.push(createShippingLaneLayer({ data: shippingLanes }));
        }

        if (layerVisibility.routes && routes.length > 0) {
            result.push(createRouteLayer({ data: routes }));
        }

        if (layerVisibility.migrationCorridors && migrationCorridors.length > 0) {
            result.push(createMigrationCorridorLayer({ data: migrationCorridors }));
        }

        return result;
    }, [riskData, sightings, routes, shippingLanes, migrationCorridors, layerVisibility, onSightingClick]);

    return (
        <div style={{ width: "100%", height: "100%", position: "relative" }}>
            <DeckGL
                viewState={viewState}
                onViewStateChange={handleViewStateChange}
                layers={layers}
                controller={true}
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                getTooltip={getTooltip as any}
            >
                <Map mapStyle="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json" />
            </DeckGL>
        </div>
    );
}
