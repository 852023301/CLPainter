#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose -p clpainter-build \
  --env-file .env \
  -f docker-compose.yml build
