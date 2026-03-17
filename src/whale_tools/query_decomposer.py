"""Whale Query Decomposer — breaks questions into domain-routed sub-questions.

Uses LLM-powered decomposition (when a model is configured via ``tool_config``)
to intelligently route questions to specialist agents. Falls back to keyword-based
heuristics when the LLM is not configured or fails.

Stores the selected agent list in session state (``_selected_agents``) so that
the protocol_step_validator callback can restrict DELEGATE-step peer tools to
only those agents the decomposer chose.
"""

import json
import logging
import re
from typing import Optional

from google.adk.tools import ToolContext
from google.genai import types as adk_types

from solace_agent_mesh.agent.tools.dynamic_tool import DynamicTool

from whale_common.constants import DOMAIN_AGENT_ROUTING

log = logging.getLogger(__name__)

# Session state key read by protocol_step_validator to restrict peer tools
_SELECTED_AGENTS_KEY = "_selected_agents"

# ---------------------------------------------------------------------------
# LLM decomposition prompt
# ---------------------------------------------------------------------------

_DECOMPOSE_SYSTEM_PROMPT = """You are a marine research and route-planning query router. Given a user's whale/shipping question, decompose it into focused sub-questions and route each to the most appropriate specialist agent.

Available specialists:
- RouteOptimizer: Shipping route planning, waypoint optimization, voyage planning, detour calculations
- RiskAssessor: Whale-vessel collision risk scoring, probability assessment, hazard evaluation
- WeatherAnalyst: Marine weather, sea state, storm tracking, wave/wind conditions, ocean currents
- VesselTrafficMonitor: AIS vessel tracking, shipping lane density, port traffic, fleet monitoring
- WhaleMigrationTracker: Whale migration patterns, seasonal movements, breeding/feeding corridors
- HabitatAnalyst: Marine habitat mapping, feeding hotspots, krill/plankton distribution, ecosystem data
- SpeciesIdentifier: Whale species identification, IUCN conservation status, population data
- IncidentAnalyst: Historical whale strike data, collision incident records, trend analysis

Rules:
1. Most questions need 2-4 specialists, not all 8
2. Consider implicit relationships:
   - Route safety questions → RouteOptimizer + RiskAssessor
   - Seasonal route planning → RouteOptimizer + WhaleMigrationTracker + WeatherAnalyst
   - Whale strike prevention → RiskAssessor + VesselTrafficMonitor + IncidentAnalyst
   - Species sighting questions → SpeciesIdentifier + WhaleMigrationTracker + HabitatAnalyst
3. Do NOT split a single coherent question into fragments
4. Return 1-3 sub-questions maximum

Return JSON:
{
  "sub_questions": [
    {
      "question": "the sub-question text",
      "target_agent": "PrimarySpecialist",
      "secondary_agents": ["SecondarySpecialist1"]
    }
  ],
  "all_agents": ["Agent1", "Agent2", "Agent3"],
  "reasoning": "brief explanation of routing decisions"
}"""

_DECOMPOSE_USER_PROMPT = """Decompose and route this whale/marine question:

{question}

Return JSON only."""

# Set of valid agent names derived from the routing map at import time
_VALID_AGENTS = {info["agent"] for info in DOMAIN_AGENT_ROUTING.values()}


def _score_domain(text: str, domain_info: dict) -> float:
    """Score how well a text matches a domain based on keyword overlap.

    Short keywords (<=3 chars) use word-boundary matching to prevent false
    positives from substrings. Longer keywords use simple substring matching.
    """
    text_lower = text.lower()
    keywords = domain_info["keywords"]
    matches = 0
    for kw in keywords:
        if len(kw) <= 3:
            if re.search(r"\b" + re.escape(kw) + r"\b", text_lower):
                matches += 1
        else:
            if kw in text_lower:
                matches += 1
    return matches / max(len(keywords), 1)


def _route_question(question: str) -> list[dict]:
    """Route a question to primary + secondary specialist agents.

    Returns list of dicts: [{domain, agent, confidence, role}, ...].
    Primary = highest keyword match. Up to 2 secondary agents included
    if they have any keyword matches.
    """
    scored = []
    for domain, info in DOMAIN_AGENT_ROUTING.items():
        score = _score_domain(question, info)
        scored.append((domain, info["agent"], score))

    scored.sort(key=lambda x: x[2], reverse=True)

    if log.isEnabledFor(logging.DEBUG):
        top_scores = [(d, round(s, 4)) for d, _, s in scored[:5]]
        log.debug("query_decomposer: domain scores for %r: %s", question[:80], top_scores)

    results = []

    # Primary: best match, or route_optimization if nothing matched
    if scored[0][2] > 0:
        primary = scored[0]
    else:
        primary = ("route_optimization", "RouteOptimizer", 0.04)
    results.append({
        "domain": primary[0],
        "agent": primary[1],
        "confidence": round(min(primary[2] * 5, 1.0), 2),
        "role": "primary",
    })

    # Secondary: up to 2 more with any keyword match
    for domain, agent, score in scored[1:]:
        if score > 0 and agent != results[0]["agent"] and len(results) < 3:
            results.append({
                "domain": domain,
                "agent": agent,
                "confidence": round(min(score * 5, 1.0), 2),
                "role": "secondary",
            })

    log.info(
        "query_decomposer: routed %r → %s",
        question[:60],
        [(r["agent"], r["role"], r["confidence"]) for r in results],
    )
    return results


def _split_question(question: str, max_sub: int) -> list[str]:
    """Split a compound question into sub-questions using heuristics."""
    if len(question) < 50 and "?" in question:
        return [question.strip()]

    sub_questions = []

    # Split on numbered patterns
    numbered = re.split(r"\d+[.)]\s+|[a-z][.)]\s+", question)
    if len(numbered) > 2:
        sub_questions = [s.strip() for s in numbered if s.strip()]
    else:
        # Split on semicolons
        parts = question.split(";")
        if len(parts) > 1:
            sub_questions = [p.strip() for p in parts if p.strip()]
        else:
            # Split on conjunctions
            conj_pattern = r"\s+(?:and also|and\b|also\b|as well as|in addition to)\s+"
            parts = re.split(conj_pattern, question, flags=re.IGNORECASE)
            if len(parts) > 1:
                sub_questions = [p.strip() for p in parts if p.strip()]

    if not sub_questions:
        sub_questions = [question.strip()]

    cleaned = []
    for sq in sub_questions:
        sq = sq.strip().rstrip(".")
        if not sq.endswith("?"):
            sq += "?"
        cleaned.append(sq)

    return cleaned[:max_sub]


class QueryDecomposerTool(DynamicTool):
    """Decomposes whale/marine questions into domain-routed sub-questions."""

    def __init__(self, tool_config: Optional[dict] = None, **kwargs):
        super().__init__(tool_config=tool_config, **kwargs)
        cfg = tool_config or {}
        raw_model = cfg.get("model")
        if isinstance(raw_model, dict):
            self._model: str = raw_model.get("model", "")
            self._vertex_kwargs: dict = {
                k: raw_model[k]
                for k in ("vertex_project", "vertex_location")
                if k in raw_model
            }
        elif raw_model:
            self._model = raw_model
            self._vertex_kwargs = {}
        else:
            self._model = ""
            self._vertex_kwargs = {}
        self._temperature: float = float(cfg.get("temperature", 0.1))

    @staticmethod
    def _agent_to_domain(agent_name: str) -> str:
        """Map an agent name back to its domain key."""
        for domain, info in DOMAIN_AGENT_ROUTING.items():
            if info["agent"] == agent_name:
                return domain
        return "route_optimization"

    async def _llm_decompose(self, question: str, max_sub: int) -> dict | None:
        """Use LLM to decompose and route the question."""
        try:
            from litellm import acompletion as _litellm_acompletion
        except ImportError:
            log.warning("litellm not installed, falling back to keyword routing")
            return None

        user_prompt = _DECOMPOSE_USER_PROMPT.replace("{question}", question)

        response = await _litellm_acompletion(
            model=self._model,
            messages=[
                {"role": "system", "content": _DECOMPOSE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self._temperature,
            max_tokens=2048,
            **self._vertex_kwargs,
        )

        raw = response.choices[0].message.content
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            log.warning("LLM decomposition returned unparseable result")
            return None

        if not parsed or "sub_questions" not in parsed:
            return None

        sub_questions = parsed["sub_questions"][:max_sub]
        all_agents = sorted(
            {a for a in parsed.get("all_agents", []) if a in _VALID_AGENTS}
        )

        if not all_agents:
            return None

        formatted_subs = []
        for i, sq in enumerate(sub_questions):
            target = sq.get("target_agent", "RouteOptimizer")
            if target not in _VALID_AGENTS:
                target = "RouteOptimizer"
            secondaries = [
                {"agent": a, "domain": self._agent_to_domain(a)}
                for a in sq.get("secondary_agents", [])
                if a in _VALID_AGENTS and a != target
            ]
            formatted_subs.append({
                "question": sq.get("question", question),
                "domain": self._agent_to_domain(target),
                "target_agent": target,
                "secondary_agents": secondaries,
                "priority": i + 1,
                "routing_confidence": 0.85,
            })

        return {
            "original_question": question,
            "sub_questions": formatted_subs,
            "routing_confidence": 0.85,
            "count": len(formatted_subs),
            "all_agents": all_agents,
            "routing_method": "llm",
        }

    @property
    def tool_name(self) -> str:
        return "query_decomposer"

    @property
    def tool_description(self) -> str:
        return (
            "Breaks down a whale/marine question into sub-questions, each "
            "routed to a primary specialist plus secondary specialists for "
            "multi-source evidence. Returns sub-questions with domain/agent "
            "routing and a list of all agents to delegate to."
        )

    @property
    def parameters_schema(self) -> adk_types.Schema:
        return adk_types.Schema(
            type=adk_types.Type.OBJECT,
            properties={
                "question": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="The whale/marine question to decompose",
                ),
                "max_sub_questions": adk_types.Schema(
                    type=adk_types.Type.INTEGER,
                    description="Maximum number of sub-questions to generate (default 5)",
                    nullable=True,
                ),
            },
            required=["question"],
        )

    @staticmethod
    def _store_selected_agents(tool_context: ToolContext, agents: list[str]) -> None:
        """Persist selected agents in session state for the protocol validator."""
        try:
            inv = getattr(tool_context, "_invocation_context", None)
            session_obj = getattr(inv, "session", None) if inv else None
            if session_obj and hasattr(session_obj, "state"):
                session_obj.state[_SELECTED_AGENTS_KEY] = agents
                log.info(
                    "[QueryDecomposer] Stored _selected_agents in session state: %s",
                    agents,
                )
        except Exception:
            log.debug(
                "[QueryDecomposer] Could not store _selected_agents in session state"
            )

    async def _run_async_impl(
        self,
        args: dict,
        tool_context: Optional[ToolContext] = None,
        credential: Optional[str] = None,
    ) -> dict:
        question = args.get("question", "").strip()
        max_sub = args.get("max_sub_questions", 5)

        if not question:
            return {"error": "Question is required"}

        if max_sub < 1:
            max_sub = 1
        elif max_sub > 10:
            max_sub = 10

        # LLM decomposition (preferred when model is configured)
        if self._model:
            try:
                result = await self._llm_decompose(question, max_sub)
                if result:
                    if tool_context:
                        self._store_selected_agents(tool_context, result["all_agents"])
                    return result
            except Exception as exc:
                log.warning(
                    "LLM decomposition failed, falling back to keywords: %s", exc
                )

        # Keyword fallback
        sub_questions_text = _split_question(question, max_sub)

        sub_questions = []
        all_agents: set[str] = set()
        total_confidence = 0.0
        for i, sq in enumerate(sub_questions_text):
            routes = _route_question(sq)
            primary = routes[0]
            secondaries = routes[1:]
            sub_questions.append({
                "question": sq,
                "domain": primary["domain"],
                "target_agent": primary["agent"],
                "secondary_agents": [
                    {"agent": r["agent"], "domain": r["domain"]}
                    for r in secondaries
                ],
                "priority": i + 1,
                "routing_confidence": primary["confidence"],
            })
            total_confidence += primary["confidence"]
            all_agents.add(primary["agent"])
            for r in secondaries:
                all_agents.add(r["agent"])

        avg_confidence = (
            round(total_confidence / len(sub_questions), 2) if sub_questions else 0.0
        )

        sorted_agents = sorted(all_agents)

        if tool_context:
            self._store_selected_agents(tool_context, sorted_agents)

        return {
            "original_question": question,
            "sub_questions": sub_questions,
            "routing_confidence": avg_confidence,
            "count": len(sub_questions),
            "all_agents": sorted_agents,
            "routing_method": "keyword",
        }
