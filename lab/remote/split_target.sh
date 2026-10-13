#!/bin/bash
# split_target.sh "BATTERY ARGS" 'RANGES-JSON' : stdin script for a TARGET pod. Pauses the Lab,
# queues the same battery, keeps only the given ranges ({name: [[lo, hi], ...]}, merged) of the
# NEW jobs (the newest job of each name) and resumes.
cat <<EOS
stty -echo
cd /srv/lab
curl -s -X POST -H 'Content-Type: application/json' -d '{}' 127.0.0.1:8765/api/pause </dev/null >/dev/null
python3 $1 8765 </dev/null | grep -c ok | sed 's/^/QUEUED /'
python3 - <<'PY'
import sqlite3, json
ranges = json.loads('$2')
db = sqlite3.connect('/srv/data/db/lab.sqlite3', timeout=60, isolation_level=None)
db.execute('BEGIN IMMEDIATE'); kept = 0
for jid, name in db.execute("SELECT MAX(id), name FROM jobs GROUP BY name").fetchall():
    if name not in ranges: continue
    lo, hi = min(r[0] for r in ranges[name]), max(r[1] for r in ranges[name])
    db.execute("DELETE FROM tasks WHERE job_id=? AND status='pending' AND (idx<? OR idx>=?)", (jid, lo, hi))
    kept += db.execute("SELECT COUNT(*) FROM tasks WHERE job_id=? AND status='pending'", (jid,)).fetchone()[0]
db.execute('COMMIT')
print('KEPT', kept)
PY
curl -s -X POST -H 'Content-Type: application/json' -d '{}' 127.0.0.1:8765/api/resume </dev/null >/dev/null
exit
EOS
