"""Fuel Estimator — estimates fuel impact of route diversions.

Given route distances and speed, calculates extra fuel consumption and
time impact from whale-avoidance route modifications.
"""

import logging
from typing import Optional

from google.adk.tools import ToolContext
from google.genai import types as adk_types

from solace_agent_mesh.agent.tools.dynamic_tool import DynamicTool

log = logging.getLogger(__name__)

# Approximate fuel consumption rates (liters per nautical mile) by speed
# Based on typical medium-size cargo vessel (~30,000 DWT)
_FUEL_RATE_PER_NM = {
    10: 8.0,
    12: 10.5,
    14: 13.5,
    16: 17.0,
    18: 21.0,
    20: 26.0,
    22: 32.0,
}


def _interpolate_fuel_rate(speed_knots: float) -> float:
    """Interpolate fuel consumption rate for a given speed."""
    speeds = sorted(_FUEL_RATE_PER_NM.keys())
    if speed_knots <= speeds[0]:
        return _FUEL_RATE_PER_NM[speeds[0]]
    if speed_knots >= speeds[-1]:
        return _FUEL_RATE_PER_NM[speeds[-1]]
    for i in range(len(speeds) - 1):
        if speeds[i] <= speed_knots <= speeds[i + 1]:
            ratio = (speed_knots - speeds[i]) / (speeds[i + 1] - speeds[i])
            r1 = _FUEL_RATE_PER_NM[speeds[i]]
            r2 = _FUEL_RATE_PER_NM[speeds[i + 1]]
            return r1 + ratio * (r2 - r1)
    return _FUEL_RATE_PER_NM[speeds[-1]]


def compute_fuel_impact(
    route_distance_nm: float,
    original_distance_nm: float,
    speed_knots: float,
) -> dict:
    """Compute fuel impact of a route diversion."""
    extra_distance = route_distance_nm - original_distance_nm
    fuel_rate = _interpolate_fuel_rate(speed_knots)

    fuel_impact_pct = round(
        ((route_distance_nm / max(original_distance_nm, 0.01)) - 1.0) * 100, 2
    )
    extra_fuel_liters = round(extra_distance * fuel_rate, 2)
    time_delta_hours = round(extra_distance / max(speed_knots, 0.01), 2)

    return {
        "fuel_impact_pct": fuel_impact_pct,
        "extra_fuel_liters": max(0.0, extra_fuel_liters),
        "time_delta_hours": max(0.0, time_delta_hours),
        "extra_distance_nm": round(extra_distance, 2),
        "fuel_rate_liters_per_nm": round(fuel_rate, 2),
        "total_fuel_liters": round(route_distance_nm * fuel_rate, 2),
        "original_fuel_liters": round(original_distance_nm * fuel_rate, 2),
    }


class FuelEstimatorTool(DynamicTool):
    """Estimates fuel impact of route diversions."""

    @property
    def tool_name(self) -> str:
        return "fuel_estimator"

    @property
    def tool_description(self) -> str:
        return (
            "Estimates fuel impact of whale-avoidance route diversions. "
            "Given route and original distances plus speed, returns fuel impact "
            "percentage, extra fuel in liters, and time delta in hours."
        )

    @property
    def parameters_schema(self) -> adk_types.Schema:
        return adk_types.Schema(
            type=adk_types.Type.OBJECT,
            properties={
                "route_distance_nm": adk_types.Schema(
                    type=adk_types.Type.NUMBER,
                    description="Total route distance in nautical miles (with diversion)",
                ),
                "original_distance_nm": adk_types.Schema(
                    type=adk_types.Type.NUMBER,
                    description="Original direct route distance in nautical miles",
                ),
                "speed_knots": adk_types.Schema(
                    type=adk_types.Type.NUMBER,
                    description="Vessel speed in knots",
                ),
            },
            required=["route_distance_nm", "original_distance_nm", "speed_knots"],
        )

    async def _run_async_impl(
        self,
        args: dict,
        tool_context: Optional[ToolContext] = None,
        credential: Optional[str] = None,
    ) -> dict:
        try:
            return compute_fuel_impact(
                route_distance_nm=float(args["route_distance_nm"]),
                original_distance_nm=float(args["original_distance_nm"]),
                speed_knots=float(args["speed_knots"]),
            )
        except (KeyError, ValueError, TypeError) as exc:
            return {"error": f"Invalid input: {exc}"}
