#!/usr/bin/env bash
# Render n8n credentials from .env, then import credentials + workflow into n8n.
# Idempotent: re-running re-imports (n8n upserts by id).
set -euo pipefail
cd "$(dirname "$0")/.."

# load .env
set -a
# shellcheck disable=SC1091
source .env
set +a

RENDERED="scripts/credentials.local.json"
echo "[provision] rendering credentials from .env..."
envsubst < scripts/credentials.template.json > "$RENDERED"

echo "[provision] copying into n8n container..."
docker cp "$RENDERED" easm_n8n:/tmp/credentials.json
docker cp n8n/workflow.json easm_n8n:/tmp/workflow.json

echo "[provision] importing credentials..."
docker exec easm_n8n n8n import:credentials --input=/tmp/credentials.json

echo "[provision] importing workflow..."
docker exec easm_n8n n8n import:workflow --input=/tmp/workflow.json

echo "[provision] activating workflow (registers the run-easm production webhook)..."
docker exec easm_n8n n8n update:workflow --active=true --id=easm-pipeline >/dev/null

echo "[provision] cleaning up secrets..."
docker exec easm_n8n rm -f /tmp/credentials.json
rm -f "$RENDERED"

echo "[provision] restarting n8n so the webhook registers..."
docker restart easm_n8n >/dev/null
for _ in $(seq 1 30); do
  curl -sf "http://localhost:${N8N_PORT:-5678}/healthz" >/dev/null 2>&1 && break
  sleep 2
done

echo "[provision] done. UI: http://localhost:${N8N_PORT:-5678}  (workflow id: easm-pipeline)"
