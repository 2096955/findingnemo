import React, { useState, useCallback, useMemo } from "react";
import Map from "react-map-gl/maplibre";
import DeckGL from "@deck.gl/react";
import { HeatmapLayer, ScatterplotLayer, PathLayer } from "@deck.gl/layers";
import "maplibre-gl/dist/maplibre-gl.css";

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
            result.push(
                new HeatmapLayer({
                    id: "risk-heatmap",
                    data: riskData,
                    getPosition: (d: RiskPoint) => [d.lng, d.lat],
                    getWeight: (d: RiskPoint) => d.risk,
                    radiusPixels: 60,
                    intensity: 1,
                    threshold: 0.1,
                    colorRange: [
                        [65, 182, 196],
                        [127, 205, 187],
                        [199, 233, 180],
                        [255, 255, 204],
                        [254, 178, 76],
                        [240, 59, 32],
                    ],
                })
            );
        }

        if (layerVisibility.sightings && sightings.length > 0) {
            result.push(
                new ScatterplotLayer({
                    id: "whale-sightings",
                    data: sightings,
                    getPosition: (d: Sighting) => [d.lng, d.lat],
                    getRadius: (d: Sighting) => Math.max(d.count * 500, 1000),
                    getFillColor: [0, 119, 182, 180],
                    getLineColor: [0, 0, 0, 255],
                    lineWidthMinPixels: 1,
                    pickable: true,
                    onClick: onSightingClick as ((info: unknown) => void) | undefined,
                })
            );
        }

        if (layerVisibility.shippingLanes && shippingLanes.length > 0) {
            result.push(
                new PathLayer({
                    id: "shipping-lanes",
                    data: shippingLanes,
                    getPath: (d: Route) => d.path,
                    getColor: [128, 128, 128, 100],
                    getWidth: 2000,
                    widthMinPixels: 1,
                })
            );
        }

        if (layerVisibility.routes && routes.length > 0) {
            result.push(
                new PathLayer({
                    id: "recommended-route",
                    data: routes,
                    getPath: (d: Route) => d.path,
                    getColor: [16, 185, 129, 255],
                    getWidth: 3000,
                    widthMinPixels: 2,
                })
            );
        }

        if (layerVisibility.migrationCorridors && migrationCorridors.length > 0) {
            result.push(
                new PathLayer({
                    id: "migration-corridors",
                    data: migrationCorridors,
                    getPath: (d: Route) => d.path,
                    getColor: [99, 102, 241, 120],
                    getWidth: 5000,
                    widthMinPixels: 3,
                    getDashArray: [8, 4],
                })
            );
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
