#!/usr/bin/env bash
# Start all Whale Agent agents + gateway via a SINGLE sam run process.
#
# In dev mode (SOLACE_DEV_MODE=true), each sam run process creates its own
# in-memory DevBroker. Running agents in separate processes means they each
# get an isolated broker and can never discover each other. The fix is to
# pass ALL config YAMLs to one sam run invocation so they share a broker.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIGS_DIR="$PROJECT_DIR/configs"

cd "$PROJECT_DIR"

echo "Starting Whale Agent (11 agents + gateway, single process)..."

# Specialists first (for discovery ordering), then orchestrator, support agents, gateway.
sam run \
  "$CONFIGS_DIR/agents/route_optimizer.yaml" \
  "$CONFIGS_DIR/agents/risk_assessor.yaml" \
  "$CONFIGS_DIR/agents/weather_analyst.yaml" \
  "$CONFIGS_DIR/agents/vessel_traffic_monitor.yaml" \
  "$CONFIGS_DIR/agents/whale_migration_tracker.yaml" \
  "$CONFIGS_DIR/agents/habitat_analyst.yaml" \
  "$CONFIGS_DIR/agents/species_identifier.yaml" \
  "$CONFIGS_DIR/agents/incident_analyst.yaml" \
  "$CONFIGS_DIR/agents/verifier.yaml" \
  "$CONFIGS_DIR/agents/reviser.yaml" \
  "$CONFIGS_DIR/agents/orchestrator.yaml" \
  "$CONFIGS_DIR/gateways/webui.yaml"
