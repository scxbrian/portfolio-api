#!/usr/bin/env bash
# Safe backup of the portfolio database, taken while the API is running.
set -euo pipefail

CONTAINER="${CONTAINER:-portfolio-api}"
DEST="${BACKUP_DIR:-$HOME/backups/portfolio-api}"
KEEP="${KEEP:-14}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$DEST/portfolio-$STAMP.db"

mkdir -p "$DEST"

# SQLite's own backup API gives a consistent copy even during a write.
docker exec "$CONTAINER" python -c "
import sqlite3
src = sqlite3.connect('/srv/data/portfolio.db')
dst = sqlite3.connect('/srv/data/backup.tmp')
src.backup(dst)
dst.close()
src.close()
"
docker cp "$CONTAINER:/srv/data/backup.tmp" "$OUT"
docker exec "$CONTAINER" rm -f /srv/data/backup.tmp

# Refuse to keep a backup that does not pass SQLite's integrity check.
RESULT="$(python3 -c "import sqlite3, sys; print(sqlite3.connect(sys.argv[1]).execute('PRAGMA integrity_check').fetchone()[0])" "$OUT")"
if [ "$RESULT" != "ok" ]; then
  echo "Backup failed integrity check: $RESULT" >&2
  rm -f "$OUT"
  exit 1
fi

# Keep only the newest $KEEP backups.
ls -1t "$DEST"/portfolio-*.db | tail -n +"$((KEEP + 1))" | xargs -r rm --

echo "$(date -Is) backup ok: $OUT ($(stat -c %s "$OUT") bytes)"