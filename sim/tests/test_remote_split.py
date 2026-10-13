"""Splitting a Lab battery across rented servers (lab/remote/split.py).

Spec: the source server keeps the first of K chunks of every active job's pending tasks and
hands out the other chunks as index ranges; a target server that queued the same battery keeps
only the tasks inside its ranges. Every pending task runs on exactly one server.
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'lab' / 'remote'))

import split  # noqa: E402


def lab_db(jobs):
    """jobs: {name: (status, {idx: task status})} -> in-memory Lab database."""
    db = sqlite3.connect(':memory:', isolation_level=None)
    db.execute("CREATE TABLE jobs(id INTEGER PRIMARY KEY, name TEXT, status TEXT)")
    db.execute("CREATE TABLE tasks(id INTEGER PRIMARY KEY, job_id INTEGER, idx INTEGER, status TEXT)")
    for name, (status, tasks) in jobs.items():
        jid = db.execute("INSERT INTO jobs(name, status) VALUES (?, ?)", (name, status)).lastrowid
        db.executemany("INSERT INTO tasks(job_id, idx, status) VALUES (?, ?, ?)",
                       [(jid, i, s) for i, s in tasks.items()])
    return db


def pending(db, name):
    return {i for (i,) in db.execute("SELECT t.idx FROM tasks t JOIN jobs j ON j.id=t.job_id "
                                     "WHERE j.name=? AND t.status='pending'", (name,))}


def in_ranges(ranges):
    return {i for lo, hi in ranges for i in range(lo, hi)}


def test_chunks_cover_every_pending_task_once():
    # Given a job with 10 done and 90 pending tasks
    tasks = {i: 'done' if i < 10 else 'pending' for i in range(100)}
    db = lab_db({'scene': ('active', tasks)})
    # When the source splits it 3 ways
    ranges = split.source(db, 3)
    # Then the source keeps one chunk and the ranges hold the rest, with no overlap or gap
    kept = pending(db, 'scene')
    handed = [in_ranges([r]) for r in ranges['scene']]
    assert len(ranges['scene']) == 2
    assert kept.isdisjoint(handed[0]) and kept.isdisjoint(handed[1]) and handed[0].isdisjoint(handed[1])
    assert kept | handed[0] | handed[1] == set(range(10, 100))


def test_last_range_is_bounded():
    # Given a job whose highest index is 49 (the pod 6 over-split came from an open end)
    db = lab_db({'scene': ('active', {i: 'pending' for i in range(50)})})
    # When it is split, then no range reaches past the job's own tasks
    assert max(hi for _, hi in split.source(db, 4)['scene']) == 50


def test_small_and_paused_jobs_untouched():
    # Given a paused job and an active job with fewer pending tasks than chunks
    db = lab_db({'paused': ('paused', {i: 'pending' for i in range(30)}),
                 'tiny': ('active', {0: 'pending', 1: 'pending'})})
    # When split 3 ways, then neither is split nor trimmed
    assert split.source(db, 3) == {}
    assert len(pending(db, 'paused')) == 30 and len(pending(db, 'tiny')) == 2


def test_target_keeps_only_its_ranges_even_when_not_contiguous():
    # Given a target that queued the same battery fresh
    db = lab_db({'scene': ('active', {i: 'pending' for i in range(100)})})
    # When it keeps two separate ranges
    kept = split.target(db, {'scene': [[10, 20], [60, 70]]})
    # Then exactly those tasks stay pending (nothing from the gap between them)
    assert pending(db, 'scene') == set(range(10, 20)) | set(range(60, 70)) and kept == 20


def test_target_uses_newest_job_of_each_name():
    # Given an older job and a freshly queued one with the same name
    db = lab_db({'scene': ('active', {i: 'pending' for i in range(10)})})
    jid = db.execute("INSERT INTO jobs(name, status) VALUES ('scene', 'active')").lastrowid
    db.executemany("INSERT INTO tasks(job_id, idx, status) VALUES (?, ?, 'pending')", [(jid, i) for i in range(10)])
    # When the target keeps a range, then only the newest job is trimmed
    split.target(db, {'scene': [[0, 5]]})
    counts = dict(db.execute("SELECT job_id, COUNT(*) FROM tasks WHERE status='pending' GROUP BY job_id"))
    assert counts == {1: 10, jid: 5}


def test_jobs_with_the_same_name_and_other_seeds_stay_apart():
    # Given two jobs named alike that differ by their seeds (a battery queued once per seed)
    db = sqlite3.connect(':memory:', isolation_level=None)
    db.execute("CREATE TABLE jobs(id INTEGER PRIMARY KEY, name TEXT, status TEXT, params TEXT)")
    db.execute("CREATE TABLE tasks(id INTEGER PRIMARY KEY, job_id INTEGER, idx INTEGER, status TEXT)")
    for seed, done in ((1401, 30), (1402, 0)):
        jid = db.execute("INSERT INTO jobs(name, status, params) VALUES ('AB x', 'active', ?)",
                         ('{"seeds": [%d]}' % seed,)).lastrowid
        db.executemany("INSERT INTO tasks(job_id, idx, status) VALUES (?, ?, ?)",
                       [(jid, i, 'done' if i < done else 'pending') for i in range(100)])
    # When the source splits 2 ways, then each job gets its own range
    ranges = split.source(db, 2)
    assert len(ranges) == 2 and sorted(r[0][0] for r in ranges.values()) == [50, 65]
    # And a target that queued both jobs keeps each job's own range
    target = sqlite3.connect(':memory:', isolation_level=None)
    target.execute("CREATE TABLE jobs(id INTEGER PRIMARY KEY, name TEXT, status TEXT, params TEXT)")
    target.execute("CREATE TABLE tasks(id INTEGER PRIMARY KEY, job_id INTEGER, idx INTEGER, status TEXT)")
    for seed in (1401, 1402):
        jid = target.execute("INSERT INTO jobs(name, status, params) VALUES ('AB x', 'active', ?)",
                             ('{"seeds": [%d]}' % seed,)).lastrowid
        target.executemany("INSERT INTO tasks(job_id, idx, status) VALUES (?, ?, 'pending')", [(jid, i) for i in range(100)])
    split.target(target, ranges)
    kept = dict(target.execute("SELECT job_id, MIN(idx) FROM tasks WHERE status='pending' GROUP BY job_id"))
    assert kept == {1: 65, 2: 50}
