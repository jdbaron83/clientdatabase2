#!/bin/sh
# Nightly database backup. Keeps 30 days of compressed dumps in ./backups.
# Run from cron:  0 2 * * * cd /home/azureuser/clientdatabase2 && ./scripts/backup.sh >> backups/backup.log 2>&1
set -eu
cd "$(dirname "$0")/.."
mkdir -p backups
chmod 700 backups
file="backups/clientdb-$(date +%Y-%m-%d-%H%M).sql.gz"
docker compose exec -T db pg_dump -U clientdb --clean --if-exists clientdb | gzip > "$file"
chmod 600 "$file"
find backups -name 'clientdb-*.sql.gz' -mtime +30 -delete
echo "$(date) backup written: $file"
