#!/usr/bin/env bash
# Full-stack Whale Agent startup for Cloud Run single-container deployment.
#
# Starts: Redis → 6 MCP servers → sam run (11 agents + gateway)
#
# Cold store (SQLite) is stored on the container's ephemeral filesystem at
# /app/data/. Data is lost on container restart. For persistent learning,
# mount a Cloud Storage FUSE volume or migrate to Cloud SQL.
set -euo pipefail

cd /app

# ---------------------------------------------------------------------------
# 1. Validate all required configs
# ---------------------------------------------------------------------------
REQUIRED_CONFIGS=(
  configs/agents/route_optimizer.yaml
  configs/agents/risk_assessor.yaml
  configs/agents/weather_analyst.yaml
  configs/agents/vessel_traffic_monitor.yaml
  configs/agents/whale_migration_tracker.yaml
  configs/agents/habitat_analyst.yaml
  configs/agents/species_identifier.yaml
  configs/agents/incident_analyst.yaml
  configs/agents/verifier.yaml
  configs/agents/reviser.yaml
  configs/agents/orchestrator.yaml
  # webui.yaml MUST be last — uvicorn in the gateway keeps sam run alive.
  # All other configs must be loaded before the gateway initialises.
  configs/gateways/webui.yaml
)

for cfg in "${REQUIRED_CONFIGS[@]}"; do
  if [ ! -s "$cfg" ]; then
    echo "[WhaleAgent] FATAL: Required config not found or empty: $cfg"
    exit 1
  fi
done

echo "[WhaleAgent] Starting full-stack Whale Agent..."
echo "[WhaleAgent] Host: 0.0.0.0, Port: ${PORT:-8080}"

export FASTAPI_HOST="0.0.0.0"
export FASTAPI_PORT="${PORT:-8080}"

# ---------------------------------------------------------------------------
# 2. Start Redis (ephemeral, localhost only)
# ---------------------------------------------------------------------------
echo "[WhaleAgent] Starting Redis..."
redis-server --daemonize yes --bind 127.0.0.1 --port 6379

for i in $(seq 1 10); do
  redis-cli ping 2>/dev/null | grep -q PONG && break
  sleep 1
done

if ! redis-cli ping 2>/dev/null | grep -q PONG; then
  echo "[WhaleAgent] FATAL: Redis failed to start"
  exit 1
fi
echo "[WhaleAgent] Redis ready"

# ---------------------------------------------------------------------------
# 3. Start MCP servers (background processes)
# ---------------------------------------------------------------------------
MCP_PIDS=()
MCP_SERVERS=(
  "mcp_servers.noaa.server:9001"
  "mcp_servers.whale_alert.server:9002"
  "mcp_servers.marine_cadastre.server:9003"
  "mcp_servers.open_meteo.server:9004"
  "mcp_servers.gbif.server:9005"
  "mcp_servers.iucn.server:9006"
)

for entry in "${MCP_SERVERS[@]}"; do
  module="${entry%%:*}"
  port="${entry##*:}"
  echo "[WhaleAgent] Starting MCP: $module (port $port)"
  python -m "$module" &
  MCP_PIDS+=($!)
done

# ---------------------------------------------------------------------------
# 4. Health check MCP servers (TCP socket, not /sse — SSE streams hang)
# ---------------------------------------------------------------------------
echo "[WhaleAgent] Waiting for MCP servers..."
for entry in "${MCP_SERVERS[@]}"; do
  port="${entry##*:}"
  module="${entry%%:*}"
  ready=false
  for i in $(seq 1 30); do
    if python -c "import socket; s=socket.create_connection(('localhost',$port),timeout=2); s.close()" 2>/dev/null; then
      ready=true
      break
    fi
    sleep 1
  done
  if [ "$ready" = true ]; then
    echo "[WhaleAgent]   Port $port ready ($module)"
  else
    echo "[WhaleAgent]   WARNING: Port $port not ready ($module) — continuing (graceful degradation)"
  fi
done

# ---------------------------------------------------------------------------
# 5. Graceful shutdown handler
# ---------------------------------------------------------------------------
cleanup() {
  echo "[WhaleAgent] Shutting down..."
  # Kill SAM first — allow PERSIST step to flush session signals
  if [ -n "${SAM_PID:-}" ]; then
    kill "$SAM_PID" 2>/dev/null || true
    wait "$SAM_PID" 2>/dev/null || true
  fi
  # Kill MCP servers in reverse start order
  for (( i=${#MCP_PIDS[@]}-1; i>=0; i-- )); do
    kill "${MCP_PIDS[$i]}" 2>/dev/null || true
  done
  # Stop Redis last
  redis-cli shutdown nosave 2>/dev/null || true
  echo "[WhaleAgent] Shutdown complete"
}
trap cleanup SIGTERM SIGINT EXIT

# ---------------------------------------------------------------------------
# 6. Start sam run (background, wait on PID)
# --system-env: skip .env file loading. On Cloud Run, env vars are injected
# via --set-env-vars in the deploy command. SAM inherits system env vars;
# --system-env prevents SAM from loading a .env with conflicting settings.
# ---------------------------------------------------------------------------
echo "[WhaleAgent] Starting sam run with ${#REQUIRED_CONFIGS[@]} configs..."
sam run --system-env "${REQUIRED_CONFIGS[@]}" &
SAM_PID=$!
wait $SAM_PID
