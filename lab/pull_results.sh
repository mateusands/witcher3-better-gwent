#!/bin/bash
# Copies a consistent snapshot of a remote Lab database to the local HDD (SQLite online
# backup on the server, then scp). Safe while the remote Lab keeps running.
#   GWENT_LAB_SERVER=user@host lab/pull_results.sh [destination file]
set -euo pipefail
SERVER="${GWENT_LAB_SERVER:?set GWENT_LAB_SERVER=user@host}"
DEST="${1:-/mnt/hdd/GwentAILab/remote/$(echo "$SERVER" | tr '@:' '__').sqlite3}"
mountpoint -q /mnt/hdd || { echo "HDD not mounted" >&2; exit 1; }
mkdir -p "$(dirname "$DEST")"
ssh -o BatchMode=yes "$SERVER" 'python3 -c "
import sqlite3
src = sqlite3.connect(\"/srv/gwentailab/data/db/lab.sqlite3\")
dst = sqlite3.connect(\"/tmp/gwent-lab-snapshot.sqlite3\")
src.backup(dst); dst.close()"'
scp -q "$SERVER:/tmp/gwent-lab-snapshot.sqlite3" "$DEST.part"
ssh -o BatchMode=yes "$SERVER" rm -f /tmp/gwent-lab-snapshot.sqlite3
mv "$DEST.part" "$DEST"
echo "saved $DEST"
