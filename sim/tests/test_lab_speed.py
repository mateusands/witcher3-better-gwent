"""Lab throughput (lab/core.py): audit of 13 October 2026.

Spec (owner, 13 October 2026): find and fix the Lab's bottlenecks.
- Task claim: every worker picks its next task inside a write lock. On the Google Cloud database
  (73,000 tasks) that query scanned every task of every job: 150 ms per claim, so 32 workers
  finishing ~6 tasks a second kept the database locked most of the time. An index on
  tasks(job_id, status) answers it in 0.2 ms; the claim query must use it.
- Sequential A/B jobs ('ab'): the next batch is queued as soon as the last batch has no pending
  task left (its tasks may still be running), so workers never idle at the end of a batch. The
  SPRT is checked on the finished matchups at every step, so a clear answer stops the job
  without waiting for the batch; the job's pending tasks are then removed (running ones finish
  and are kept). No more than max_tasks matchups are ever queued.
- Batches of 100 matchups (was 200): the test can stop at every 100.

Given the Lab database, when a worker claims a task, then the query plan uses the index; given an
'ab' job, when its batch is all claimed but not finished, then the next batch is queued, and when
the finished matchups already decide, then the job stops and its pending tasks are removed.
"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'lab'))
sys.path.insert(0, str(ROOT / 'sim'))

import core  # noqa: E402

SCENE = 'response-v8:player-mulligan+base-mulligan'


def fresh():
    db = sqlite3.connect(':memory:', isolation_level=None)
    db.executescript(core.SCHEMA)
    return db


def test_task_claim_uses_the_job_status_index():
    db = fresh()
    plan = ' '.join(str(r) for r in db.execute('EXPLAIN QUERY PLAN ' + core.CLAIM_JOB))
    assert 'tasks_job_status' in plan
    assert 'tasks_job_status' in core.SCHEMA and 'ON tasks(job_id, status)' in core.SCHEMA


def ab_job(db, **over):
    params = dict(source='player', profile='hard', base_policy=SCENE, base_decks='balanced', policy=SCENE,
                  npc_decks='balanced:spyval', seeds=[1], batch=10, max_tasks=40,
                  sprt=dict(mu0=0.0, mu1=0.02, alpha=0.05, beta=0.05, min_n=10))
    params.update(over)
    return core.create_job(db, 't', 'ab', params)


def count(db, jid, status):
    return db.execute('SELECT COUNT(*) FROM tasks WHERE job_id=? AND status=?', (jid, status)).fetchone()[0]


def test_next_batch_is_queued_while_the_last_tasks_still_run():
    db = fresh()
    jid = ab_job(db)
    ids = [r[0] for r in db.execute('SELECT id FROM tasks WHERE job_id=? ORDER BY id', (jid,))]
    # Given a batch fully claimed: half finished with no clear answer, half still running
    for i, tid in enumerate(ids):
        if i < 5:
            db.execute("UPDATE tasks SET status='done', result=? WHERE id=?",
                       (json.dumps(dict(candidate=1.0 if i % 2 else 0.0, base=0.5)), tid))
        else:
            db.execute("UPDATE tasks SET status='running' WHERE id=?", (tid,))
    core.ab_step(db)
    # Then the next batch is already queued and the job goes on
    assert count(db, jid, 'pending') == 10
    assert db.execute('SELECT status FROM jobs WHERE id=?', (jid,)).fetchone()[0] == 'active'


def test_a_clear_answer_stops_the_job_and_drops_its_pending_tasks():
    db = fresh()
    jid = ab_job(db, batch=20)
    ids = [r[0] for r in db.execute('SELECT id FROM tasks WHERE job_id=? ORDER BY id', (jid,))]
    # Given 12 finished matchups that the candidate all loses, 3 running, the rest pending
    for i, tid in enumerate(ids[:12]):
        db.execute("UPDATE tasks SET status='done', result=? WHERE id=?",
                   (json.dumps(dict(candidate=0.0, base=1.0)), tid))
    for tid in ids[12:15]:
        db.execute("UPDATE tasks SET status='running' WHERE id=?", (tid,))
    core.ab_step(db)
    params = json.loads(db.execute('SELECT params FROM jobs WHERE id=?', (jid,)).fetchone()[0])
    assert db.execute('SELECT status FROM jobs WHERE id=?', (jid,)).fetchone()[0] == 'done'
    assert params['verdict']['result'] == 'not better' and params['verdict']['n'] == 12
    assert count(db, jid, 'pending') == 0 and count(db, jid, 'running') == 3


def test_never_more_than_max_tasks_are_queued():
    db = fresh()
    jid = ab_job(db, batch=30, max_tasks=40)
    for _ in range(5):
        db.execute("UPDATE tasks SET status='done', result=? WHERE job_id=? AND status='pending'",
                   (json.dumps(dict(candidate=0.5, base=0.5)), jid))
        core.ab_step(db)
    assert db.execute('SELECT COUNT(*) FROM tasks WHERE job_id=?', (jid,)).fetchone()[0] <= 40


def test_batches_of_100():
    assert core.AB_DEFAULTS['batch'] == 100
    import battery_round11
    assert battery_round11.job('spy-first', 'balanced', 1)['batch'] == 100
