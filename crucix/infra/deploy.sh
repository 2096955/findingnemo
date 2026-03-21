#!/usr/bin/env bash
# Deploy whale-route-monitor to Cloud Run
# Usage: bash crucix/infra/deploy.sh [TAG]
#   TAG defaults to "v1"
set -euo pipefail

PROJECT_ID="gbg-neuro"
REGION="europe-west2"
SERVICE="whale-route-monitor"
TAG="${1:-v1}"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE}:${TAG}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CRUCIX_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Whale Route Monitor — Cloud Run Deploy ==="
echo "Project:  ${PROJECT_ID}"
echo "Region:   ${REGION}"
echo "Service:  ${SERVICE}"
echo "Image:    ${IMAGE}"
echo "Context:  ${CRUCIX_DIR}"
echo ""

# ---------------------------------------------------------------------------
# 1. Build Docker image
# ---------------------------------------------------------------------------
echo "[1/3] Building Docker image..."
docker build \
  -t "${IMAGE}" \
  -t "gcr.io/${PROJECT_ID}/${SERVICE}:latest" \
  -f "${CRUCIX_DIR}/infra/Dockerfile.cloudrun" \
  "${CRUCIX_DIR}"

echo "[1/3] Build complete."

# ---------------------------------------------------------------------------
# 2. Push to GCR
# ---------------------------------------------------------------------------
echo "[2/3] Pushing to Container Registry..."
docker push "${IMAGE}"
docker push "gcr.io/${PROJECT_ID}/${SERVICE}:latest"
echo "[2/3] Push complete."

# ---------------------------------------------------------------------------
# 3. Deploy to Cloud Run
# ---------------------------------------------------------------------------
echo "[3/3] Deploying to Cloud Run..."
gcloud run deploy "${SERVICE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --image="${IMAGE}" \
  --platform=managed \
  --allow-unauthenticated \
  --port=8080 \
  --cpu=1 \
  --memory=1Gi \
  --max-instances=5 \
  --timeout=300 \
  --set-env-vars="PORT=8080,LLM_PROVIDER=gemini,LLM_API_KEY=AIzaSyBOrXdwsFvLKSKRe8KUFJwnCslpkgvq6Vo,LLM_MODEL=gemini-2.0-flash,FIRECRAWL_API_KEY=fc-2146c607264b4ea899e16c2a7bc951ec,REFRESH_INTERVAL_MINUTES=15" \
  --service-account="healthcare-poc-vertexai@gbg-neuro.iam.gserviceaccount.com"

echo ""
echo "=== Deploy complete ==="
SERVICE_URL=$(gcloud run services describe "${SERVICE}" --project="${PROJECT_ID}" --region="${REGION}" --format="value(status.url)" 2>/dev/null)
echo "URL: ${SERVICE_URL}"
echo "Health: ${SERVICE_URL}/api/health"
echo ""
echo "Test: curl ${SERVICE_URL}/api/health"
