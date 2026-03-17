import { createContext } from "react";
import type { ParsedAgentResponse } from "@/lib/utils/parseAgentResponse";

export interface DashboardDataContextValue {
    /** Parsed GeoJSON data from the most recent chat response containing map layers */
    chatDashboardData: ParsedAgentResponse | null;
    /** Push parsed agent response data from chat to the dashboard */
    setChatDashboardData: (data: ParsedAgentResponse | null) => void;
}

export const DashboardDataContext = createContext<DashboardDataContextValue | undefined>(undefined);
