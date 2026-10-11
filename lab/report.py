#!/usr/bin/env python3
"""Totals of the testing done so far, for the README "Testing" section.

    python3 lab/report.py DB [DB ...] [--evaluations game/evaluations]

DBs are Lab databases (live copies or archives); give each database once (a database that
was continued elsewhere is counted by its newest copy only). Matches are counted per
simulated match: a pool benchmark group plays 3 (native baseline + candidate in each
seat), a player-deck group 2, a hunt 1 plus its replays. CPU time is the sum of task
durations (one core each).
"""
import argparse
import json
import sqlite3
from pathlib import Path


def lab_totals(path):
    db = sqlite3.connect('file:%s?mode=ro' % path, uri=True)
    out = dict(cpuSeconds=0.0, matches=0, findings=0, byKind={})
    for kind, payload, result, started, finished in db.execute(
            "SELECT j.kind, t.payload, t.result, t.started, t.finished FROM tasks t JOIN jobs j ON j.id=t.job_id "
            "WHERE t.status='done'"):
        r, p = json.loads(result), json.loads(payload)
        if kind in ('hunt', 'deep-hunt'):
            matches = 1 + r.get('replays', 0)
            out['findings'] += len(r.get('findings', []))
        else:
            matches = 2 if p.get('source') == 'player' else 3
        out['matches'] += matches
        if started and finished:
            out['cpuSeconds'] += finished - started
        k = out['byKind'].setdefault(kind, dict(tasks=0, matches=0))
        k['tasks'] += 1
        k['matches'] += matches
    return out


def evaluation_matches(root):
    """Matches recorded in earlier exploratory evaluation reports (before the Lab)."""
    total = 0
    for path in Path(root).rglob('*.json'):
        try:
            data = json.loads(path.read_text())
        except (ValueError, OSError):
            continue
        if isinstance(data, dict) and isinstance(data.get('trials'), list):
            total += len(data['trials'])
    return total


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('dbs', nargs='+')
    parser.add_argument('--evaluations')
    args = parser.parse_args()
    total = dict(cpuSeconds=0.0, matches=0, findings=0)
    for path in args.dbs:
        t = lab_totals(path)
        for key in total:
            total[key] += t[key]
        print('%s: %d matches, %.1f CPU hours, %d findings, %s' % (
            Path(path).name, t['matches'], t['cpuSeconds'] / 3600, t['findings'], t['byKind']))
    print('LAB TOTAL: %d simulated matches, %.1f CPU hours, %d hunt findings' % (
        total['matches'], total['cpuSeconds'] / 3600, total['findings']))
    if args.evaluations:
        print('EARLIER EVALUATIONS: %d simulated matches' % evaluation_matches(args.evaluations))


if __name__ == '__main__':
    main()
