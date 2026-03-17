// Dashboard components
export { DashboardPage } from "./DashboardPage";
export { MapView } from "./MapView";
export type { RiskPoint, Sighting, Route, LayerVisibility } from "./MapView";

export { Sidebar } from "./Sidebar";
export type { RouteQuery, RiskSummary, SpeedAlert } from "./Sidebar";

// Layer factory functions
export { createRiskHeatmapLayer } from "./RiskHeatmapLayer";
export type { RiskHeatmapLayerOptions } from "./RiskHeatmapLayer";

export { createWhaleMarkerLayer } from "./WhaleMarkerLayer";
export type { WhaleMarkerLayerOptions } from "./WhaleMarkerLayer";

export { createShippingLaneLayer } from "./ShippingLaneLayer";
export type { ShippingLaneLayerOptions } from "./ShippingLaneLayer";

export { createRouteLayer } from "./RouteLayer";
export type { RouteLayerOptions } from "./RouteLayer";

export { createMigrationCorridorLayer } from "./MigrationCorridorLayer";
export type { MigrationCorridorLayerOptions } from "./MigrationCorridorLayer";
