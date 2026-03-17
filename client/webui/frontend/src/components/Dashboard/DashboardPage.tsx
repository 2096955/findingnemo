import React, { useState, useCallback } from "react";
import { MapView, type LayerVisibility, type RiskPoint, type Sighting, type Route } from "./MapView";
import { Sidebar, type RouteQuery, type RiskSummary, type SpeedAlert } from "./Sidebar";

/**
 * DashboardPage composes the MapView and Sidebar into a full-width dashboard layout.
 * It manages shared state (layer visibility, filters, risk data) between the map and sidebar.
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

    // Data state - populated by agent responses
    const [riskData, setRiskData] = useState<RiskPoint[]>([]);
    const [sightings, setSightings] = useState<Sighting[]>([]);
    const [routes, setRoutes] = useState<Route[]>([]);
    const [shippingLanes, setShippingLanes] = useState<Route[]>([]);
    const [migrationCorridors, setMigrationCorridors] = useState<Route[]>([]);
    const [riskSummary, setRiskSummary] = useState<RiskSummary | null>(null);
    const [alerts, setAlerts] = useState<SpeedAlert[]>([]);
    const [isQuerying, setIsQuerying] = useState(false);

    // Load demo data on first interaction to show the map is functional
    const loadDemoData = useCallback(() => {
        // Sample risk data along the US West Coast
        setRiskData([
            { lat: 37.8, lng: -122.4, risk: 0.8 },
            { lat: 37.5, lng: -122.8, risk: 0.6 },
            { lat: 36.8, lng: -122.0, risk: 0.9 },
            { lat: 34.0, lng: -119.5, risk: 0.7 },
            { lat: 34.4, lng: -120.5, risk: 0.85 },
            { lat: 33.7, lng: -118.3, risk: 0.5 },
            { lat: 38.3, lng: -123.1, risk: 0.75 },
            { lat: 35.5, lng: -121.0, risk: 0.65 },
        ]);

        // Sample whale sightings
        setSightings([
            { lat: 37.7, lng: -122.6, species: "Humpback Whale", count: 12 },
            { lat: 36.9, lng: -122.1, species: "Blue Whale", count: 5 },
            { lat: 34.1, lng: -119.8, species: "Gray Whale", count: 8 },
            { lat: 34.5, lng: -120.7, species: "Humpback Whale", count: 15 },
            { lat: 38.0, lng: -123.0, species: "Blue Whale", count: 3 },
            { lat: 33.9, lng: -118.5, species: "Fin Whale", count: 6 },
        ]);

        // Sample shipping lane
        setShippingLanes([
            {
                path: [
                    [-122.4, 37.8],
                    [-122.0, 36.5],
                    [-120.8, 35.0],
                    [-119.5, 34.0],
                    [-118.3, 33.7],
                ],
            },
        ]);

        // Sample migration corridor
        setMigrationCorridors([
            {
                path: [
                    [-124.0, 40.0],
                    [-123.5, 38.5],
                    [-123.0, 37.0],
                    [-122.0, 35.5],
                    [-120.5, 34.0],
                    [-119.0, 33.0],
                ],
            },
        ]);
    }, []);

    const handleRouteQuery = useCallback(
        async (query: RouteQuery) => {
            setIsQuerying(true);

            // Load demo data to visualize while we wait
            loadDemoData();

            // Simulate a route planning response
            // In production, this would call the SAM gateway via SSE
            setTimeout(() => {
                setRoutes([
                    {
                        path: [
                            [-122.4, 37.8],
                            [-123.0, 37.0],
                            [-122.5, 36.0],
                            [-121.5, 35.0],
                            [-120.0, 34.2],
                            [-118.5, 33.8],
                        ],
                    },
                ]);

                setRiskSummary({
                    collisionProbability: 12.4,
                    fuelImpact: 3.2,
                    delayHours: 1.5,
                });

                setAlerts([
                    {
                        zone: "Monterey Bay NMS",
                        maxSpeed: 10,
                        reason: "Blue whale feeding area",
                    },
                    {
                        zone: "Santa Barbara Channel",
                        maxSpeed: 10,
                        reason: "Seasonal speed restriction",
                    },
                ]);

                setIsQuerying(false);
            }, 1500);
        },
        [loadDemoData]
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
            <div className="flex-1">
                <MapView
                    riskData={riskData}
                    sightings={sightings}
                    routes={routes}
                    shippingLanes={shippingLanes}
                    migrationCorridors={migrationCorridors}
                    layerVisibility={layerVisibility}
                />
            </div>
        </div>
    );
}
