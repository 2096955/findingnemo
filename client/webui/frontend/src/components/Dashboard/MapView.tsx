import React, { useState, useCallback, useMemo } from "react";
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
        const result: unknown[] = [];

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
                getTooltip={getTooltip as (info: unknown) => unknown}
            >
                <Map mapStyle="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json" />
            </DeckGL>
        </div>
    );
}
