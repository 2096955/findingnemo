#!/usr/bin/env bash
# Start all MCP servers for Whale Agent
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "Starting Whale Agent MCP servers..."

python -m mcp_servers.noaa.server &
python -m mcp_servers.whale_alert.server &
python -m mcp_servers.marine_cadastre.server &
python -m mcp_servers.open_meteo.server &
python -m mcp_servers.gbif.server &
python -m mcp_servers.iucn.server &
python -m mcp_servers.searxng.server &

echo "All 7 MCP servers started (ports 9001-9007)"
wait
