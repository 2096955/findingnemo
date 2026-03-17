import React, { useState, useCallback } from "react";
import type { LayerVisibility } from "./MapView";

/** ---- Data types for sidebar panels ---- */

export interface RouteQuery {
    originPort: string;
    destinationPort: string;
    departureDate: string;
}

export interface RiskSummary {
    collisionProbability: number; // 0-100 %
    fuelImpact: number; // percentage change
    delayHours: number;
}

export interface SpeedAlert {
    zone: string;
    maxSpeed: number; // knots
    reason: string;
}

/** ---- Sidebar props ---- */

interface SidebarProps {
    onRouteQuery?: (query: RouteQuery) => void;
    riskSummary?: RiskSummary | null;
    alerts?: SpeedAlert[];
    layerVisibility: LayerVisibility;
    onLayerVisibilityChange: (visibility: LayerVisibility) => void;
    isQuerying?: boolean;
    statusText?: string;
    error?: string | null;
    selectedSeason?: string;
    onSeasonChange?: (season: string) => void;
    selectedSpecies?: string;
    onSpeciesChange?: (species: string) => void;
}

const SEASONS = ["All Seasons", "Spring", "Summer", "Fall", "Winter"];
const SPECIES = [
    "All Species",
    "Blue Whale",
    "Humpback Whale",
    "Gray Whale",
    "Right Whale",
    "Fin Whale",
    "Sperm Whale",
];

const LAYER_LABELS: Record<keyof LayerVisibility, string> = {
    riskHeatmap: "Risk Heatmap",
    sightings: "Whale Sightings",
    shippingLanes: "Shipping Lanes",
    routes: "Recommended Routes",
    migrationCorridors: "Migration Corridors",
};

export function Sidebar({
    onRouteQuery,
    riskSummary,
    alerts = [],
    layerVisibility,
    onLayerVisibilityChange,
    isQuerying = false,
    statusText = "",
    error = null,
    selectedSeason = "All Seasons",
    onSeasonChange,
    selectedSpecies = "All Species",
    onSpeciesChange,
}: SidebarProps) {
    const [originPort, setOriginPort] = useState("");
    const [destinationPort, setDestinationPort] = useState("");
    const [departureDate, setDepartureDate] = useState("");

    const handleSubmit = useCallback(
        (e: React.FormEvent) => {
            e.preventDefault();
            if (originPort && destinationPort && onRouteQuery) {
                onRouteQuery({ originPort, destinationPort, departureDate });
            }
        },
        [originPort, destinationPort, departureDate, onRouteQuery]
    );

    const handleLayerToggle = useCallback(
        (key: keyof LayerVisibility) => {
            onLayerVisibilityChange({
                ...layerVisibility,
                [key]: !layerVisibility[key],
            });
        },
        [layerVisibility, onLayerVisibilityChange]
    );

    return (
        <aside
            className="flex h-full w-80 flex-shrink-0 flex-col overflow-y-auto border-r bg-background"
            style={{ borderColor: "var(--border)" }}
        >
            {/* Header */}
            <div className="border-b px-4 py-3" style={{ borderColor: "var(--border)" }}>
                <h2 className="text-lg font-semibold text-foreground">Whale Strike Dashboard</h2>
                <p className="text-xs text-muted-foreground">Route planning & risk assessment</p>
            </div>

            {/* Route Input Form */}
            <div className="border-b px-4 py-3" style={{ borderColor: "var(--border)" }}>
                <h3 className="mb-2 text-sm font-medium text-foreground">Route Planning</h3>
                <form onSubmit={handleSubmit} className="space-y-2">
                    <div>
                        <label className="mb-1 block text-xs text-muted-foreground">Origin Port</label>
                        <input
                            type="text"
                            placeholder="e.g. San Francisco"
                            value={originPort}
                            onChange={(e) => setOriginPort(e.target.value)}
                            className="w-full rounded border bg-card px-2 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                            style={{ borderColor: "var(--border)" }}
                        />
                    </div>
                    <div>
                        <label className="mb-1 block text-xs text-muted-foreground">Destination Port</label>
                        <input
                            type="text"
                            placeholder="e.g. Los Angeles"
                            value={destinationPort}
                            onChange={(e) => setDestinationPort(e.target.value)}
                            className="w-full rounded border bg-card px-2 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                            style={{ borderColor: "var(--border)" }}
                        />
                    </div>
                    <div>
                        <label className="mb-1 block text-xs text-muted-foreground">Departure Date</label>
                        <input
                            type="date"
                            value={departureDate}
                            onChange={(e) => setDepartureDate(e.target.value)}
                            className="w-full rounded border bg-card px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                            style={{ borderColor: "var(--border)" }}
                        />
                    </div>
                    <button
                        type="submit"
                        disabled={!originPort || !destinationPort || isQuerying}
                        className="w-full rounded px-3 py-1.5 text-sm font-medium text-white transition-colors disabled:opacity-50"
                        style={{ backgroundColor: "var(--primary)" }}
                    >
                        {isQuerying ? "Planning..." : "Plan Route"}
                    </button>
                </form>
                {isQuerying && statusText && (
                    <p className="mt-2 text-xs text-muted-foreground animate-pulse">{statusText}</p>
                )}
                {error && (
                    <p className="mt-2 text-xs" style={{ color: "var(--destructive)" }}>{error}</p>
                )}
            </div>

            {/* Season / Species Filters */}
            <div className="border-b px-4 py-3" style={{ borderColor: "var(--border)" }}>
                <h3 className="mb-2 text-sm font-medium text-foreground">Filters</h3>
                <div className="space-y-2">
                    <div>
                        <label className="mb-1 block text-xs text-muted-foreground">Season</label>
                        <select
                            value={selectedSeason}
                            onChange={(e) => onSeasonChange?.(e.target.value)}
                            className="w-full rounded border bg-card px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                            style={{ borderColor: "var(--border)" }}
                        >
                            {SEASONS.map((s) => (
                                <option key={s} value={s}>
                                    {s}
                                </option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <label className="mb-1 block text-xs text-muted-foreground">Species</label>
                        <select
                            value={selectedSpecies}
                            onChange={(e) => onSpeciesChange?.(e.target.value)}
                            className="w-full rounded border bg-card px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                            style={{ borderColor: "var(--border)" }}
                        >
                            {SPECIES.map((s) => (
                                <option key={s} value={s}>
                                    {s}
                                </option>
                            ))}
                        </select>
                    </div>
                </div>
            </div>

            {/* Risk Summary */}
            {riskSummary && (
                <div className="border-b px-4 py-3" style={{ borderColor: "var(--border)" }}>
                    <h3 className="mb-2 text-sm font-medium text-foreground">Risk Summary</h3>
                    <div className="space-y-2">
                        <div className="flex items-center justify-between rounded bg-card p-2">
                            <span className="text-xs text-muted-foreground">Collision Probability</span>
                            <span
                                className="text-sm font-semibold"
                                style={{
                                    color:
                                        riskSummary.collisionProbability > 50
                                            ? "var(--destructive)"
                                            : riskSummary.collisionProbability > 20
                                              ? "var(--warning, #F59E0B)"
                                              : "var(--color-success-wMain, #10B981)",
                                }}
                            >
                                {riskSummary.collisionProbability.toFixed(1)}%
                            </span>
                        </div>
                        <div className="flex items-center justify-between rounded bg-card p-2">
                            <span className="text-xs text-muted-foreground">Fuel Impact</span>
                            <span className="text-sm font-semibold text-foreground">
                                {riskSummary.fuelImpact > 0 ? "+" : ""}
                                {riskSummary.fuelImpact.toFixed(1)}%
                            </span>
                        </div>
                        <div className="flex items-center justify-between rounded bg-card p-2">
                            <span className="text-xs text-muted-foreground">Estimated Delay</span>
                            <span className="text-sm font-semibold text-foreground">{riskSummary.delayHours.toFixed(1)}h</span>
                        </div>
                    </div>
                </div>
            )}

            {/* Active Alerts */}
            {alerts.length > 0 && (
                <div className="border-b px-4 py-3" style={{ borderColor: "var(--border)" }}>
                    <h3 className="mb-2 text-sm font-medium text-foreground">
                        Active Alerts{" "}
                        <span
                            className="ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full text-[10px] text-white"
                            style={{ backgroundColor: "var(--destructive)" }}
                        >
                            {alerts.length}
                        </span>
                    </h3>
                    <div className="space-y-2">
                        {alerts.map((alert, i) => (
                            <div
                                key={i}
                                className="rounded border-l-2 bg-card p-2"
                                style={{ borderLeftColor: "var(--destructive)" }}
                            >
                                <div className="text-xs font-medium text-foreground">{alert.zone}</div>
                                <div className="text-xs text-muted-foreground">
                                    Max {alert.maxSpeed} knots - {alert.reason}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Layer Toggles */}
            <div className="px-4 py-3">
                <h3 className="mb-2 text-sm font-medium text-foreground">Map Layers</h3>
                <div className="space-y-1.5">
                    {(Object.keys(LAYER_LABELS) as (keyof LayerVisibility)[]).map((key) => (
                        <label key={key} className="flex cursor-pointer items-center gap-2">
                            <input
                                type="checkbox"
                                checked={layerVisibility[key]}
                                onChange={() => handleLayerToggle(key)}
                                className="h-3.5 w-3.5 rounded border-gray-300 accent-[var(--primary)]"
                            />
                            <span className="text-xs text-foreground">{LAYER_LABELS[key]}</span>
                        </label>
                    ))}
                </div>
            </div>
        </aside>
    );
}
