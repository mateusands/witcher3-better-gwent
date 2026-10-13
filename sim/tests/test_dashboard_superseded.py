"""Dashboard totals leave out superseded jobs (lab/dashboard.py).

Spec: a job marked superseded was run with a known flaw; its results never reach a chart or a KPI.

Given a Lab database with a superseded hunt and a current hunt,
when the dashboard collects the mistakes found,
then only the current hunt's findings are counted.
"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'lab'))

import dashboard  # noqa: E402


def test_superseded_hunt_findings_are_not_counted(tmp_path):
    path = tmp_path / 'lab.sqlite3'
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE jobs(id INTEGER PRIMARY KEY, name TEXT, kind TEXT, params TEXT, created REAL, status TEXT)")
    db.execute("CREATE TABLE tasks(id INTEGER PRIMARY KEY, job_id INTEGER, idx INTEGER, payload TEXT, status TEXT, "
               "result TEXT, error TEXT, worker INTEGER, started REAL, finished REAL)")
    finding = dict(round=1, regret=0.5)
    for jid, status, rounds in ((1, 'superseded', 1), (2, 'active', 2)):
        db.execute("INSERT INTO jobs VALUES (?, 'hunt', 'deep-hunt', '{}', 0, ?)", (jid, status))
        db.execute("INSERT INTO tasks(job_id, idx, payload, status, result) VALUES (?, 0, '{}', 'done', ?)",
                   (jid, json.dumps(dict(score=0, findings=[dict(finding, round=rounds)]))))
    db.commit(); db.close()
    _, _, rounds = dashboard.collect([path])
    assert dict(rounds) == {2: 1}


def test_report_counts_superseded_work_but_not_its_findings(tmp_path):
    # Given the same database, when the report totals it, then its matches count (real work)
    # but only the current hunt's findings do
    import report
    path = tmp_path / 'lab.sqlite3'
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE jobs(id INTEGER PRIMARY KEY, name TEXT, kind TEXT, params TEXT, created REAL, status TEXT)")
    db.execute("CREATE TABLE tasks(id INTEGER PRIMARY KEY, job_id INTEGER, idx INTEGER, payload TEXT, status TEXT, "
               "result TEXT, error TEXT, worker INTEGER, started REAL, finished REAL)")
    for jid, status in ((1, 'superseded'), (2, 'active')):
        db.execute("INSERT INTO jobs VALUES (?, 'hunt', 'deep-hunt', '{}', 0, ?)", (jid, status))
        db.execute("INSERT INTO tasks(job_id, idx, payload, status, result) VALUES (?, 0, '{}', 'done', ?)",
                   (jid, json.dumps(dict(score=0, replays=3, findings=[dict(round=1, regret=0.5)]))))
    db.commit(); db.close()
    totals = report.lab_totals(path)
    assert totals['matches'] == 8 and totals['findings'] == 1
