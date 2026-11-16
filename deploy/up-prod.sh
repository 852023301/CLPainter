#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose -p clpainter-prod \
  --env-file .env --env-file deploy/env/prod.env \
  -f docker-compose.yml -f docker-compose.prod.yml up -d
