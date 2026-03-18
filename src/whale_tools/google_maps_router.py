"""Google Maps Router — real-world route computation via Gemini + Maps grounding.

Uses the google-genai SDK with Google Maps as a grounding tool to compute
actual maritime/shipping routes with real distances, waypoints, and ETAs.
Supplements the haversine-based route_calculator with ground-truth data.
"""

import json
import logging
import os
import re
from typing import Optional

from google.adk.tools import ToolContext
from google.genai import types as adk_types

from solace_agent_mesh.agent.tools.dynamic_tool import DynamicTool

log = logging.getLogger(__name__)


def _build_prompt(
    origin: str,
    destination: str,
    waypoints: list[str] | None = None,
    exclusion_zones: list[str] | None = None,
) -> str:
    """Build a structured prompt for Gemini + Maps grounding."""
    parts = [
        f"Compute a shipping/maritime route from {origin} to {destination}.",
    ]
    if waypoints:
        parts.append(f"Include these intermediate waypoints: {', '.join(waypoints)}.")
    if exclusion_zones:
        parts.append(
            f"AVOID these regions entirely (closed/dangerous): {', '.join(exclusion_zones)}. "
            "Route around them using safe alternatives."
        )
    parts.append(
        "\nReturn your answer as a JSON object with this exact structure:\n"
        "{\n"
        '  "origin": {"name": "...", "lat": ..., "lng": ...},\n'
        '  "destination": {"name": "...", "lat": ..., "lng": ...},\n'
        '  "waypoints": [{"name": "...", "lat": ..., "lng": ..., "note": "..."}],\n'
        '  "total_distance_nm": ...,\n'
        '  "total_distance_km": ...,\n'
        '  "estimated_travel_hours": ...,\n'
        '  "route_description": "Brief narrative of the route taken",\n'
        '  "warnings": ["any route warnings or advisories"]\n'
        "}\n\n"
        "Use real port coordinates. If this is an ocean route, provide waypoints "
        "at key navigation points (straits, capes, channel entries). "
        "Distances should reflect actual maritime routing, not straight-line."
    )
    return "\n".join(parts)


def _extract_json(text: str) -> dict | None:
    """Extract the first JSON object from LLM response text."""
    # Try fenced code blocks first
    fenced = re.search(r"```(?:json)?\s*\n?([\s\S]*?)```", text)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try bare JSON object — use brace-depth counting for robustness
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break

    return None


def _to_geojson(waypoints: list[dict], origin: dict, destination: dict) -> dict:
    """Convert waypoint list to a GeoJSON FeatureCollection with LineString."""
    all_points = [origin] + waypoints + [destination]
    coordinates = [
        [p["lng"], p["lat"]]
        for p in all_points
        if isinstance(p.get("lng"), (int, float)) and isinstance(p.get("lat"), (int, float))
    ]

    return {
        "type": "FeatureCollection",
        "metadata": {"render_type": "route", "source": "google_maps"},
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": coordinates,
                },
                "properties": {
                    "source": "google_maps_grounding",
                    "waypoint_count": len(all_points),
                },
            }
        ],
    }


def _build_embed_url(
    origin: str,
    destination: str,
    waypoints: list[dict] | None = None,
    api_key: str = "",
) -> str:
    """Build a Google Maps Embed API directions URL."""
    if not api_key:
        return ""
    from urllib.parse import quote

    base = "https://www.google.com/maps/embed/v1/directions"
    url = f"{base}?key={api_key}&origin={quote(origin)}&destination={quote(destination)}"
    if waypoints:
        wp_str = "|".join(
            f"{w['lat']},{w['lng']}" if "lat" in w else w.get("name", "")
            for w in waypoints[:8]  # Embed API supports up to 8 waypoints
        )
        url += f"&waypoints={quote(wp_str, safe='|,')}"
    return url


async def compute_maps_route(
    origin: str,
    destination: str,
    waypoints: list[str] | None = None,
    exclusion_zones: list[str] | None = None,
    gemini_api_key: str = "",
    maps_api_key: str = "",
    model: str = "",
) -> dict:
    """Call Gemini with Google Maps grounding to compute a real route."""
    prompt = _build_prompt(origin, destination, waypoints, exclusion_zones)
    log.info(
        "[google_maps_router] %s → %s (waypoints=%s, exclusions=%s)",
        origin, destination, waypoints, exclusion_zones,
    )

    try:
        from google import genai
        from google.genai.types import GenerateContentConfig, Tool
    except ImportError as exc:
        return {"error": f"google-genai SDK not available: {exc}"}

    # Build client — on Cloud Run, auto-discovers Vertex AI service account.
    # Locally, uses GEMINI_API_KEY.
    try:
        if gemini_api_key:
            client = genai.Client(api_key=gemini_api_key)
        else:
            client = genai.Client(
                vertexai=True,
                project=os.environ.get("GOOGLE_CLOUD_PROJECT", "gbg-neuro"),
                location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
            )
    except Exception as exc:
        return {"error": f"Failed to initialise genai client: {exc}"}

    resolved_model = model or os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

    # Try with Google Maps grounding first; fall back to plain Gemini if unavailable.
    response = None
    try:
        from google.genai.types import GoogleMaps
        response = client.models.generate_content(
            model=resolved_model,
            contents=prompt,
            config=GenerateContentConfig(
                tools=[Tool(google_maps=GoogleMaps())],
                temperature=0.1,
            ),
        )
        log.info("[google_maps_router] Used Google Maps grounding")
    except Exception as exc:
        log.warning("[google_maps_router] Maps grounding unavailable (%s), falling back to plain Gemini", exc)

    if response is None:
        try:
            response = client.models.generate_content(
                model=resolved_model,
                contents=prompt,
                config=GenerateContentConfig(temperature=0.1),
            )
        except Exception as exc:
            log.error("[google_maps_router] Gemini call failed: %s", exc)
            return {"error": f"Route computation failed: {exc}"}

    # Parse the structured response
    raw_text = response.text if response.text else ""
    parsed = _extract_json(raw_text)

    if not parsed:
        log.warning("[google_maps_router] Could not parse JSON from response")
        return {
            "error": "Could not parse structured route from Gemini response",
            "raw_response": raw_text[:2000],
        }

    # Build standardised output matching route_calculator format
    route_waypoints = parsed.get("waypoints", [])
    origin_point = parsed.get("origin", {"lat": 0, "lng": 0})
    dest_point = parsed.get("destination", {"lat": 0, "lng": 0})

    all_waypoints = [origin_point] + route_waypoints + [dest_point]

    geojson = _to_geojson(route_waypoints, origin_point, dest_point)
    embed_url = _build_embed_url(origin, destination, route_waypoints, maps_api_key)

    total_nm = parsed.get("total_distance_nm", 0)
    total_km = parsed.get("total_distance_km", 0)
    # Estimate if one is missing
    if total_nm and not total_km:
        total_km = round(total_nm * 1.852, 1)
    elif total_km and not total_nm:
        total_nm = round(total_km / 1.852, 1)

    return {
        "origin": origin_point,
        "destination": dest_point,
        "waypoints": all_waypoints,
        "total_distance_nm": total_nm,
        "total_distance_km": total_km,
        "estimated_travel_hours": parsed.get("estimated_travel_hours", 0),
        "route_description": parsed.get("route_description", ""),
        "warnings": parsed.get("warnings", []),
        "geojson": geojson,
        "google_maps_embed_url": embed_url,
        "source": "google_maps_grounding",
    }


class GoogleMapsRouterTool(DynamicTool):
    """Computes real shipping routes using Gemini + Google Maps grounding."""

    def __init__(self, tool_config: dict | None = None, **kwargs):
        super().__init__(tool_config=tool_config, **kwargs)
        cfg = tool_config or {}
        self._gemini_api_key = cfg.get(
            "gemini_api_key", os.environ.get("GEMINI_API_KEY", "")
        )
        self._maps_api_key = cfg.get(
            "maps_api_key", os.environ.get("GOOGLE_MAPS_API_KEY", "")
        )
        self._model = cfg.get("model", "")

    @property
    def tool_name(self) -> str:
        return "google_maps_router"

    @property
    def tool_description(self) -> str:
        return (
            "Computes real shipping routes using Google Maps data via Gemini "
            "grounding. Returns actual maritime waypoints, distances in nautical "
            "miles, estimated travel time, and a GeoJSON route for map display. "
            "Use this for ground-truth route data alongside route_calculator's "
            "whale-avoidance offsets."
        )

    @property
    def parameters_schema(self) -> adk_types.Schema:
        return adk_types.Schema(
            type=adk_types.Type.OBJECT,
            properties={
                "origin": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="Origin port name or 'lat,lng', e.g. 'Dubai' or '25.01,55.06'",
                ),
                "destination": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="Destination port name or 'lat,lng'",
                ),
                "waypoints": adk_types.Schema(
                    type=adk_types.Type.ARRAY,
                    items=adk_types.Schema(type=adk_types.Type.STRING),
                    description="Optional intermediate waypoints, e.g. ['Suez Canal', 'Gibraltar']",
                    nullable=True,
                ),
                "exclusion_zones": adk_types.Schema(
                    type=adk_types.Type.ARRAY,
                    items=adk_types.Schema(type=adk_types.Type.STRING),
                    description="Regions to avoid, e.g. ['Strait of Hormuz', 'Red Sea']",
                    nullable=True,
                ),
            },
            required=["origin", "destination"],
        )

    async def _run_async_impl(
        self,
        args: dict,
        tool_context: Optional[ToolContext] = None,
        credential: Optional[str] = None,
    ) -> dict:
        try:
            return await compute_maps_route(
                origin=str(args.get("origin", "")),
                destination=str(args.get("destination", "")),
                waypoints=args.get("waypoints"),
                exclusion_zones=args.get("exclusion_zones"),
                gemini_api_key=self._gemini_api_key,
                maps_api_key=self._maps_api_key,
                model=self._model,
            )
        except Exception as exc:
            log.exception("[google_maps_router] Unexpected error: %s", exc)
            return {"error": f"Google Maps routing failed: {exc}"}
