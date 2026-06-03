#!/usr/bin/env bash

# Dieses Skript wird von Coolify als Scheduled Task gestartet.
# Es erstellt ein Jira API Backup, packt es lokal als tar.gz Archiv
# und erzeugt zusätzlich eine SHA256 Prüfsumme.
# Es findet kein Upload zu Hetzner oder einem anderen externen Speicher statt.

set -euo pipefail

# Prüft Pflichtvariablen.
: "${JIRA_BASE_URL:?JIRA_BASE_URL fehlt}"
: "${JIRA_EMAIL:?JIRA_EMAIL fehlt}"
: "${JIRA_API_TOKEN:?JIRA_API_TOKEN fehlt}"

# Standardwerte setzen.
BACKUP_ROOT="${BACKUP_ROOT:-/data/backups}"
ARCHIVE_ROOT="${ARCHIVE_ROOT:-/data/archives}"
LOCAL_KEEP_DAYS="${LOCAL_KEEP_DAYS:-14}"

# Arbeitsordner vorbereiten.
mkdir -p "$BACKUP_ROOT"
mkdir -p "$ARCHIVE_ROOT"

# Jira API Backup starten.
python3 /app/jira_api_backup.py

# Neuesten Backup Ordner finden.
LATEST_BACKUP_DIR="$(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)"

if [ -z "$LATEST_BACKUP_DIR" ]; then
  echo "Kein Backup Ordner gefunden."
  exit 1
fi

BACKUP_NAME="$(basename "$LATEST_BACKUP_DIR")"
ARCHIVE_FILE="$ARCHIVE_ROOT/jira-backup-$BACKUP_NAME.tar.gz"

# Backup Ordner als tar.gz packen.
tar -czf "$ARCHIVE_FILE" -C "$BACKUP_ROOT" "$BACKUP_NAME"

# Prüfsumme für das Archiv erzeugen.
sha256sum "$ARCHIVE_FILE" > "$ARCHIVE_FILE.sha256"

# Alte lokale Backup Ordner löschen.
find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime +"$LOCAL_KEEP_DAYS" -exec rm -rf {} \;

# Alte lokale Archivdateien löschen.
find "$ARCHIVE_ROOT" -type f -name "jira-backup-*.tar.gz" -mtime +"$LOCAL_KEEP_DAYS" -delete
find "$ARCHIVE_ROOT" -type f -name "jira-backup-*.tar.gz.sha256" -mtime +"$LOCAL_KEEP_DAYS" -delete

echo "Lokales Backup erfolgreich abgeschlossen: $ARCHIVE_FILE"
