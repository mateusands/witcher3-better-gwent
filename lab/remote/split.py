#!/usr/bin/env python3
"""Split a Lab battery across rented servers.

Spec: jobs are told apart by name and seeds. The SOURCE server keeps the first of K chunks of every active job's pending tasks and
hands out the other chunks as index ranges, bounded by the job's own highest index. A TARGET
server that queued the same battery keeps only the pending tasks inside its ranges (of the
newest job of each name). Every pending task runs on exactly one server.

  split.py source K [DB]          prints RANGES {name: [[lo, hi], ...]} for chunks 1..K-1
  split.py target RANGES-JSON [DB]  prints KEPT n
"""
import json
import sqlite3
import sys

DB = '/srv/data/db/lab.sqlite3'


def job_keys(db, where=''):
    """[(job id, key)]: the key is the job name plus its seeds, so jobs of one battery queued once
    per seed (same names) stay apart. Lab databases without params use the name alone."""
    has_params = any(col[1] == 'params' for col in db.execute('PRAGMA table_info(jobs)'))
    rows = db.execute('SELECT id, name%s FROM jobs %s ORDER BY id' % (', params' if has_params else '', where)).fetchall()
    out = []
    for row in rows:
        seeds = json.loads(row[2]).get('seeds') if has_params and row[2] else None
        out.append((row[0], row[1] if seeds is None else '%s|%s' % (row[1], ','.join(map(str, seeds)))))
    return out


def source(db, k):
    db.execute('BEGIN IMMEDIATE')
    ranges = {}
    for jid, name in job_keys(db, "WHERE status='active'"):
        idx = [i for (i,) in db.execute("SELECT idx FROM tasks WHERE job_id=? AND status='pending' ORDER BY idx", (jid,))]
        if len(idx) < k:
            continue
        hi = db.execute("SELECT MAX(idx)+1 FROM tasks WHERE job_id=?", (jid,)).fetchone()[0]
        starts = [idx[j * len(idx) // k] for j in range(k)] + [hi]
        ranges[name] = [[starts[j], starts[j + 1]] for j in range(1, k)]
        db.execute("DELETE FROM tasks WHERE job_id=? AND status='pending' AND idx>=?", (jid, starts[1]))
    db.execute('COMMIT')
    return ranges


def target(db, ranges):
    db.execute('BEGIN IMMEDIATE')
    kept = 0
    newest = {}
    for jid, key in job_keys(db):
        newest[key] = jid                   # ordered by id: the newest job of each key wins
    for name, jid in newest.items():
        if name not in ranges:
            continue
        inside = ' OR '.join('(idx>=? AND idx<?)' for _ in ranges[name])
        bounds = [b for r in ranges[name] for b in r]
        db.execute("DELETE FROM tasks WHERE job_id=? AND status='pending' AND NOT (%s)" % inside, (jid, *bounds))
        kept += db.execute("SELECT COUNT(*) FROM tasks WHERE job_id=? AND status='pending'", (jid,)).fetchone()[0]
    db.execute('COMMIT')
    return kept


def main(argv):
    db = sqlite3.connect(argv[3] if len(argv) > 3 else DB, timeout=60, isolation_level=None)
    if argv[1] == 'source':
        print('RANGES ' + json.dumps(source(db, int(argv[2]))))
    else:
        print('KEPT', target(db, json.loads(argv[2])))


if __name__ == '__main__':
    main(sys.argv)
