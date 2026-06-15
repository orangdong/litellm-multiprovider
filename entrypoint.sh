#!/bin/sh
# Expands models.yaml -> generated/config.yaml (one place to manage models &
# their per-model regions), then hands off to LiteLLM's normal entrypoint.
# Runs on EVERY container start, so to apply a change just:
#   edit models.yaml  ->  docker compose up -d   (or: docker compose restart litellm)
set -e

echo "[render] models.yaml -> generated/config.yaml"
mkdir -p /app/generated
python3 /app/generate-config.py /app/models.yaml /app/generated/config.yaml

echo "[render] done; starting litellm"
exec /app/docker/prod_entrypoint.sh "$@"
