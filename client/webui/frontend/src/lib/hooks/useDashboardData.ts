import { useContext } from "react";
import { DashboardDataContext } from "@/lib/contexts/DashboardDataContext";

export function useDashboardData() {
    const ctx = useContext(DashboardDataContext);
    if (!ctx) {
        throw new Error("useDashboardData must be used within a DashboardDataProvider");
    }
    return ctx;
}
