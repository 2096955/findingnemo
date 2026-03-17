import React, { useState, useCallback, type ReactNode } from "react";
import { DashboardDataContext } from "@/lib/contexts/DashboardDataContext";
import type { ParsedAgentResponse } from "@/lib/utils/parseAgentResponse";

interface DashboardDataProviderProps {
    children: ReactNode;
}

/**
 * Provides shared dashboard data state that bridges ChatProvider responses
 * to the DashboardPage map visualization.
 *
 * Must be mounted ABOVE ChatProvider in the component tree so ChatProvider
 * can push data into it via useDashboardData().
 */
export const DashboardDataProvider: React.FC<DashboardDataProviderProps> = ({ children }) => {
    const [chatDashboardData, setChatDashboardDataState] = useState<ParsedAgentResponse | null>(null);

    const setChatDashboardData = useCallback((data: ParsedAgentResponse | null) => {
        setChatDashboardDataState(data);
    }, []);

    return (
        <DashboardDataContext.Provider value={{ chatDashboardData, setChatDashboardData }}>
            {children}
        </DashboardDataContext.Provider>
    );
};
