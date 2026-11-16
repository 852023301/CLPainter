#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose -p clpainter-test \
  --env-file .env --env-file deploy/env/test.env \
  -f docker-compose.yml -f docker-compose.test.yml up -d
