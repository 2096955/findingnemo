FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc redis-server \
    && rm -rf /var/lib/apt/lists/*

# Install SAM from PyPI (clean, no build hook)
RUN pip install --no-cache-dir "solace-agent-mesh==1.16.4"

# Install whale-agent
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir -e .

# Cold store data directory (ephemeral on Cloud Run — lost on restart.
# Learning loops reset to defaults after each container restart.)
RUN mkdir -p /app/data

# Runtime files
COPY configs/ configs/
COPY data/sample_ais_tracks.json data/sample_ais_tracks.json
# NOTE: Do NOT copy .env — it may set FASTAPI_HOST=localhost and FASTAPI_PORT=8000
# which conflicts with Cloud Run's PORT=8080. Use --system-env + Cloud Run env vars.
COPY infra/start_whale.sh /app/start_whale.sh
RUN chmod +x /app/start_whale.sh

# Overlay whale-agent frontend over SAM's default UI.
# SAM gateway serves static files from this path (StaticFiles mount).
COPY frontend-static/ /usr/local/lib/python3.12/site-packages/solace_agent_mesh/client/webui/frontend/static/

# Non-root user
RUN useradd -m -s /bin/bash whale && chown -R whale:whale /app
USER whale

ENV PORT=8080
ENV SOLACE_DEV_MODE=true
EXPOSE 8080
ENTRYPOINT ["/app/start_whale.sh"]
