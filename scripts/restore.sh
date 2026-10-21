#!/bin/sh
# Restore the database from a backup made by backup.sh. This REPLACES all current data.
# Usage: ./scripts/restore.sh backups/clientdb-2026-10-21-0200.sql.gz
set -eu
cd "$(dirname "$0")/.."
[ -f "${1:-}" ] || { echo "Usage: $0 <backup file>"; exit 1; }
printf "This replaces ALL current data with %s. Type RESTORE to continue: " "$1"
read answer
[ "$answer" = "RESTORE" ] || { echo "Cancelled."; exit 1; }
docker compose stop web
gunzip -c "$1" | docker compose exec -T db psql -q -U clientdb clientdb
docker compose start web
echo "Restored from $1"
