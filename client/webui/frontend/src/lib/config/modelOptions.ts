export const MODEL_OPTIONS = [
  { value: "flash", label: "Gemini 2.5 Flash", shortLabel: "Flash", suffix: "" },
  { value: "pro", label: "Gemini 3.1 Pro", shortLabel: "Pro", suffix: "Pro" },
  { value: "opus", label: "Claude Opus 4.6", shortLabel: "Opus", suffix: "Opus" },
] as const;

export const MODE_OPTIONS = [
  { value: "research", label: "Route Planning", shortLabel: "Routes", agentBase: "WhaleRouteCoordinator" },
  { value: "triage", label: "Risk Assessment", shortLabel: "Risk", agentBase: "RiskAssessor" },
] as const;

export type ModelValue = (typeof MODEL_OPTIONS)[number]["value"];
export type ModeValue = (typeof MODE_OPTIONS)[number]["value"];

export function resolveAgentName(_model: ModelValue, mode: ModeValue): string {
  const modeOpt = MODE_OPTIONS.find((m) => m.value === mode);
  if (!modeOpt) return "WhaleRouteCoordinator";
  // All models use the same agent — the model selection is passed as metadata,
  // not encoded in the agent name. No suffix needed.
  return modeOpt.agentBase;
}

export function inferModelFromAgentName(_agentName: string): ModelValue {
  // All models share the same agent name — model is stored separately.
  // Default to flash; the actual model selection is in the session/metadata.
  return "flash";
}

export function inferModeFromAgentName(agentName: string): ModeValue {
  if (agentName === "RiskAssessor") return "triage";
  return "research";
}
