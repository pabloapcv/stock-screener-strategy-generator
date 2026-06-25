#!/bin/bash
# Daily morning run — schedule with cron:
#   0 8 * * 1-5  /path/to/stock\ screener/scripts/morning.sh >> /path/to/stock\ screener/output/cron.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Activate venv if present
if [ -d ".venv/bin" ]; then
  source .venv/bin/activate
fi

# Load email credentials from .env
if [ -f ".env" ]; then
  set -a
  source .env
  set +a
fi

echo "=== Morning run started: $(date) ==="

python main.py daily "$@"

echo "=== Morning run finished: $(date) ==="
