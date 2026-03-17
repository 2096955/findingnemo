"""Risk Scorer — calculates whale-vessel collision probability.

Uses a weighted combination of whale density, seasonal factor, traffic density,
speed risk factor, and an interaction term to produce a 0-1 collision risk score.
"""

import logging
from typing import Optional

from google.adk.tools import ToolContext
from google.genai import types as adk_types

from solace_agent_mesh.agent.tools.dynamic_tool import DynamicTool

log = logging.getLogger(__name__)

# Seasonal multipliers by month (1-indexed)
SEASONAL_MULTIPLIERS = {
    1: 0.6, 2: 0.7, 3: 0.9, 4: 1.0, 5: 0.9, 6: 0.7,
    7: 0.5, 8: 0.4, 9: 0.5, 10: 0.7, 11: 0.8, 12: 0.7,
}


def _speed_risk(speed_knots: float) -> float:
    """Map vessel speed to risk factor."""
    if speed_knots <= 10:
        return 0.2
    elif speed_knots <= 14:
        return 0.5
    elif speed_knots <= 18:
        return 0.8
    else:
        return 1.0


def compute_risk(
    latitude: float,
    longitude: float,
    month: int,
    whale_density: float,
    vessel_traffic_density: float,
    vessel_speed_knots: float,
) -> dict:
    """Compute collision risk score and classification.

    Returns dict with collision_risk_score, risk_level, recommendation, and
    component breakdown.
    """
    # Clamp inputs
    whale_density = max(0.0, min(1.0, whale_density))
    vessel_traffic_density = max(0.0, min(1.0, vessel_traffic_density))
    vessel_speed_knots = max(0.0, vessel_speed_knots)
    month = max(1, min(12, month))

    seasonal = SEASONAL_MULTIPLIERS[month]
    speed_factor = _speed_risk(vessel_speed_knots)

    # Weighted combination
    # whale density * seasonal factor (0.35)
    # traffic density (0.25)
    # speed risk factor (0.25)
    # interaction term: whale_density * vessel_traffic_density (0.15)
    whale_seasonal = whale_density * seasonal
    interaction = whale_density * vessel_traffic_density

    score = (
        0.35 * whale_seasonal
        + 0.25 * vessel_traffic_density
        + 0.25 * speed_factor
        + 0.15 * interaction
    )

    # Clamp to [0, 1]
    score = max(0.0, min(1.0, round(score, 4)))

    # Classification
    if score >= 0.8:
        risk_level = "CRITICAL"
        recommendation = (
            "Immediate halt or maximum speed reduction required. "
            "Mandatory route diversion away from critical whale zone."
        )
    elif score >= 0.6:
        risk_level = "HIGH"
        recommendation = (
            "Immediate speed reduction to 10 knots or less recommended. "
            "Consider route diversion to avoid high-density whale area."
        )
    elif score >= 0.3:
        risk_level = "MODERATE"
        recommendation = (
            "Reduce speed to 14 knots or less. Increase lookout watch. "
            "Monitor whale alert broadcasts for real-time sighting data."
        )
    else:
        risk_level = "LOW"
        recommendation = (
            "Maintain standard watch procedures. Continue monitoring "
            "whale alert channels for any changes in conditions."
        )

    return {
        "collision_risk_score": score,
        "risk_level": risk_level,
        "recommendation": recommendation,
        "location": {"latitude": latitude, "longitude": longitude},
        "components": {
            "whale_seasonal_factor": round(whale_seasonal, 4),
            "seasonal_multiplier": seasonal,
            "traffic_density": vessel_traffic_density,
            "speed_risk": speed_factor,
            "interaction_term": round(interaction, 4),
        },
        "inputs": {
            "whale_density": whale_density,
            "vessel_traffic_density": vessel_traffic_density,
            "vessel_speed_knots": vessel_speed_knots,
            "month": month,
        },
    }


class RiskScorerTool(DynamicTool):
    """Calculates whale-vessel collision probability."""

    @property
    def tool_name(self) -> str:
        return "risk_scorer"

    @property
    def tool_description(self) -> str:
        return (
            "Calculates whale-vessel collision probability based on whale density, "
            "vessel traffic, speed, and seasonal factors. Returns a 0-1 risk score "
            "with HIGH/MODERATE/LOW classification and recommendation."
        )

    @property
    def parameters_schema(self) -> adk_types.Schema:
        return adk_types.Schema(
            type=adk_types.Type.OBJECT,
            properties={
                "latitude": adk_types.Schema(
                    type=adk_types.Type.NUMBER,
                    description="Latitude of the assessment point",
                ),
                "longitude": adk_types.Schema(
                    type=adk_types.Type.NUMBER,
                    description="Longitude of the assessment point",
                ),
                "month": adk_types.Schema(
                    type=adk_types.Type.INTEGER,
                    description="Month (1-12) for seasonal adjustment",
                ),
                "whale_density": adk_types.Schema(
                    type=adk_types.Type.NUMBER,
                    description="Whale density at this location (0-1)",
                ),
                "vessel_traffic_density": adk_types.Schema(
                    type=adk_types.Type.NUMBER,
                    description="Vessel traffic density (0-1)",
                ),
                "vessel_speed_knots": adk_types.Schema(
                    type=adk_types.Type.NUMBER,
                    description="Vessel speed in knots",
                ),
            },
            required=["latitude", "longitude", "month", "whale_density",
                       "vessel_traffic_density", "vessel_speed_knots"],
        )

    async def _run_async_impl(
        self,
        args: dict,
        tool_context: Optional[ToolContext] = None,
        credential: Optional[str] = None,
    ) -> dict:
        try:
            return compute_risk(
                latitude=float(args["latitude"]),
                longitude=float(args["longitude"]),
                month=int(args["month"]),
                whale_density=float(args["whale_density"]),
                vessel_traffic_density=float(args["vessel_traffic_density"]),
                vessel_speed_knots=float(args["vessel_speed_knots"]),
            )
        except (KeyError, ValueError, TypeError) as exc:
            return {"error": f"Invalid input: {exc}"}
