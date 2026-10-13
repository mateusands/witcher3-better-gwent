#!/bin/bash
# split_source.sh K : stdin script for the SOURCE pod. It keeps the first of K chunks of every
# active job's pending tasks, deletes the rest, and prints {job name: [[lo, hi], ...]} for chunks
# 1..K-1 (the last hi is open-ended: only right when the source holds every higher index).
cat <<EOS
stty -echo
python3 - <<'PY'
import sqlite3, json
k = $1
db = sqlite3.connect('/srv/data/db/lab.sqlite3', timeout=60, isolation_level=None)
db.execute('BEGIN IMMEDIATE'); ranges = {}
for jid, name in db.execute("SELECT id, name FROM jobs WHERE status='active'").fetchall():
    idx = [i for (i,) in db.execute("SELECT idx FROM tasks WHERE job_id=? AND status='pending' ORDER BY idx", (jid,))]
    if len(idx) < k: continue
    hi = db.execute("SELECT MAX(idx)+1 FROM tasks WHERE job_id=?", (jid,)).fetchone()[0]
    starts = [idx[j * len(idx) // k] for j in range(k)] + [hi]
    ranges[name] = [[starts[j], starts[j + 1]] for j in range(1, k)]
    db.execute("DELETE FROM tasks WHERE job_id=? AND status='pending' AND idx>=?", (jid, starts[1]))
db.execute('COMMIT')
print('RANGES ' + json.dumps(ranges))
PY
exit
EOS
