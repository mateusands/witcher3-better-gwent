#!/usr/bin/env python3
"""Sixth battery (prepared 2026-10-12): heroes that fit the NPC's faction, varied per match.

    python3 lab/battery_round6.py PORT [--seeds 901] [--cells balanced:hard,strong:hard] [--half 0|1]

Fair scene (player-mulligan+base-mulligan); NPC switches only; NPC decks in the lean shape
shipped after round 4 (Strong: 4 specials, 22 units, no Triss; Adaptive: at most 2 specials).
Per cell (decks x level):
- scene (baseline, the lean decks shipped after round 4);
- heroes: Avallac'h and Yennefer allowed, 2 or 3 of the faction's heroes drawn, Geralt or Ciri
  in about one deck in four, never Triss; the draw cycles over three variants per NPC deck.

--half splits every job by task index between two servers (0: first half, 1: second half);
the paired games stay paired because each half holds the same indices in every job.
"""
import argparse
import json
import sqlite3
import urllib.request

SCENE = 'player-mulligan+base-mulligan'
AI_SWITCHES = ()
DECK_SWITCHES = ('heroes',)


def post(port, path, body):
    req = urllib.request.Request('http://127.0.0.1:%d%s' % (port, path), json.dumps(body).encode(),
                                 {'Content-Type': 'application/json'})
    return urllib.request.urlopen(req, timeout=600).read().decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('port', type=int)
    ap.add_argument('--seeds', default='901')
    ap.add_argument('--cells', default='balanced:medium,balanced:hard,strong:medium,strong:hard')
    ap.add_argument('--half', type=int, choices=(0, 1))
    ap.add_argument('--db', default='/srv/data/db/lab.sqlite3')
    a = ap.parse_args()
    base = dict(source='player', seeds=[int(s) for s in a.seeds.split(',')])
    jobs = []
    for cell in a.cells.split(','):
        decks, level = cell.split(':')
        jobs.append(dict(base, name='scene %s %s' % (decks, level), policy='response-v8:' + SCENE,
                         profile=level, npc_decks=decks))
        for switch in AI_SWITCHES:
            jobs.append(dict(base, name='AB %s %s %s' % (switch, decks, level),
                             policy='response-v8:%s+%s' % (SCENE, switch), profile=level, npc_decks=decks))
        for switch in DECK_SWITCHES:
            jobs.append(dict(base, name='AB %s %s %s' % (switch, decks, level), policy='response-v8:' + SCENE,
                             profile=level, npc_decks='%s:%s' % (decks, switch)))
    if a.half is not None:
        post(a.port, '/api/pause', {})            # nothing may start before the other half is removed
    for job in jobs:
        print(job['name'], post(a.port, '/api/job', job)[:80])
    if a.half is not None:
        db = sqlite3.connect(a.db, timeout=60, isolation_level=None)
        db.execute('BEGIN IMMEDIATE')
        removed = 0
        for jid, total in db.execute("SELECT job_id, COUNT(*) FROM tasks WHERE status='pending' GROUP BY job_id").fetchall():
            cut = total // 2
            op = '>=' if a.half == 0 else '<'
            removed += db.execute("DELETE FROM tasks WHERE job_id=? AND status='pending' AND idx %s ?" % op,
                                  (jid, cut)).rowcount
        db.execute('COMMIT')
        print('HALF', a.half, 'removed', removed)
        post(a.port, '/api/resume', {})


if __name__ == '__main__':
    main()
