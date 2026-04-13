#!/bin/bash
# Run Alembic migrations against the configured Postgres instance.
# Usage: bash scripts/migrate.sh [alembic args]
# Default: alembic upgrade head

set -e

# Move to project root regardless of where the script is called from
cd "$(dirname "$0")/.."

alembic "${@:-upgrade head}"
