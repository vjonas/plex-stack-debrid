#!/bin/bash
# Backs up container config files (excluding logs, caches, and large databases)
# Run periodically or before major changes

set -e

BACKUP_DIR="./backups"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="$BACKUP_DIR/config-backup-$TIMESTAMP.tar.gz"

mkdir -p "$BACKUP_DIR"

echo "Backing up container configs..."

tar czf "$BACKUP_FILE" \
    --exclude='config/*/logs' \
    --exclude='config/*/Logs' \
    --exclude='config/*/Sentry' \
    --exclude='config/*/asp' \
    --exclude='config/*/Definitions' \
    --exclude='config/*/MediaCover' \
    --exclude='config/*/Backups' \
    --exclude='config/*/.cache' \
    --exclude='config/*/.yarn' \
    --exclude='config/sabnzbd/Downloads' \
    --exclude='*.log' \
    --exclude='*.pid' \
    --exclude='*-shm' \
    --exclude='*-wal' \
    config/

SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "Backup saved: $BACKUP_FILE ($SIZE)"

# Keep only the last 5 backups
ls -t "$BACKUP_DIR"/config-backup-*.tar.gz 2>/dev/null | tail -n +6 | xargs -r rm
echo "Cleaned old backups (keeping last 5)"
