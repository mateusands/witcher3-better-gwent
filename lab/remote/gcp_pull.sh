#!/bin/bash
# Copies a consistent snapshot of the Lab database on the Google Cloud VM to the local HDD,
# over the IAP tunnel (the VM has no open ports). Safe while the Lab keeps running; does
# nothing when the VM is stopped. A corrupt copy never replaces the last good one and leaves no
# partial files; a second pull while one runs (timer + manual) is skipped.
#   lab/remote/gcp_pull.sh [destination file]
set -euo pipefail
PROJECT=${GWENT_GCP_PROJECT:-better-gwent-lab-3579}; ZONE=${GWENT_GCP_ZONE:-us-central1-a}; VM=${GWENT_GCP_VM:-gwent-lab}
DEST="${1:-/mnt/hdd/GwentAILab/remote/gcp-$VM.sqlite3}"
[ -d "$(dirname "$DEST")" ] || { echo "destination folder missing (HDD not mounted?)" >&2; exit 1; }
exec 9>"${GWENT_PULL_LOCK:-/tmp/gwent-gcp-pull.lock}"
flock -n 9 || { echo "another pull is already running"; exit 0; }
trap 'rm -f "$DEST.gz.part" "$DEST.part"' EXIT
[ "$(gcloud compute instances describe "$VM" --project "$PROJECT" --zone "$ZONE" --format='value(status)')" = RUNNING ] \
  || { echo "VM not running, nothing to pull"; exit 0; }
O=(--project "$PROJECT" --zone "$ZONE" --tunnel-through-iap --ssh-key-file "$HOME/.ssh/id_ed25519" --strict-host-key-checking=no --quiet)
gcloud compute ssh "mateuswzt@$VM" "${O[@]}" --command 'python3 -c "
import sqlite3
s = sqlite3.connect(\"/srv/gwentailab/data/db/lab.sqlite3\"); d = sqlite3.connect(\"/tmp/gwent-lab-snapshot.sqlite3\")
s.backup(d); d.close()" && gzip -f /tmp/gwent-lab-snapshot.sqlite3' 2>/dev/null
gcloud compute scp "${O[@]}" "mateuswzt@$VM:/tmp/gwent-lab-snapshot.sqlite3.gz" "$DEST.gz.part" 2>/dev/null
gunzip -c "$DEST.gz.part" > "$DEST.part"
[ "$(sqlite3 "$DEST.part" "PRAGMA integrity_check" 2>/dev/null)" = ok ] || { echo "snapshot failed the integrity check; kept $DEST" >&2; exit 1; }
mv "$DEST.part" "$DEST"
echo "$(date '+%F %T') saved $DEST"
