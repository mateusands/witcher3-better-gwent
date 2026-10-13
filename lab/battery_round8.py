#!/usr/bin/env python3
"""Eighth battery (prepared 2026-10-12): NPC candidates from in-game matches g152-g157 and the
"ability-value" NPC deck switch. Lean on purpose (rented-server budget).

    python3 lab/battery_round8.py PORT [--seeds 1101] [--cells balanced:medium,...]
                                  [--variants scene,rules3,r1-chase,overkill-trim,ability-value]
                                  [--half 0|1]

Fair scene (player-mulligan+base-mulligan); NPC switches only. Variants per cell (default five):
- scene: the shipped AI and decks;
- rules3: agile-dry + weather-guard + medic-hold together in one policy;
- r1-chase: in round 1, down cards, pass a round the NPC cannot realistically win;
- overkill-trim: win the round with the smallest commitment;
- ability-value (deck switch): NPC decks value Horn units, muster packages, row-scorch and Morph
  units by their abilities (policy is the scene, npc_decks '<decks>:ability-value').
Also available, not queued by default: agile-dry, weather-guard, medic-hold (one switch each) and
all (every AI switch above together; deck flags are not part of it).
--half splits every job by task index between two servers (0: first half, 1: second half).
"""
import argparse
import json
import sqlite3
import urllib.request

SCENE = 'player-mulligan+base-mulligan'
RULES3 = 'agile-dry+weather-guard+medic-hold'
AI_SWITCHES = ('agile-dry', 'weather-guard', 'medic-hold', 'r1-chase', 'overkill-trim')
DECK_SWITCHES = ('ability-value',)
POLICIES = dict({s: s for s in AI_SWITCHES}, rules3=RULES3, all='+'.join(AI_SWITCHES))


def post(port, path, body):
    req = urllib.request.Request('http://127.0.0.1:%d%s' % (port, path), json.dumps(body).encode(),
                                 {'Content-Type': 'application/json'})
    return urllib.request.urlopen(req, timeout=600).read().decode()


def jobs_for(cells, variants, seeds):
    base = dict(source='player', seeds=seeds)
    jobs = []
    for cell in cells:
        decks, level = cell.split(':')
        for v in variants:
            if v == 'scene':
                jobs.append(dict(base, name='scene %s %s' % (decks, level), policy='response-v8:' + SCENE,
                                 profile=level, npc_decks=decks))
            elif v in POLICIES:
                jobs.append(dict(base, name='AB %s %s %s' % (v, decks, level),
                                 policy='response-v8:%s+%s' % (SCENE, POLICIES[v]), profile=level, npc_decks=decks))
            elif v in DECK_SWITCHES:
                jobs.append(dict(base, name='AB %s %s %s' % (v, decks, level), policy='response-v8:' + SCENE,
                                 profile=level, npc_decks='%s:%s' % (decks, v)))
            else:
                raise SystemExit('unknown variant %s' % v)
    return jobs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('port', type=int)
    ap.add_argument('--seeds', default='1101')
    ap.add_argument('--cells', default='balanced:medium,strong:medium,balanced:hard')
    ap.add_argument('--variants', default='scene,rules3,r1-chase,overkill-trim,ability-value')
    ap.add_argument('--half', type=int, choices=(0, 1))
    ap.add_argument('--db', default='/srv/data/db/lab.sqlite3')
    ap.add_argument('--dry-run', action='store_true', help='print the jobs without queueing them')
    a = ap.parse_args()
    jobs = jobs_for(a.cells.split(','), a.variants.split(','), [int(s) for s in a.seeds.split(',')])
    if a.dry_run:
        for job in jobs:
            print('%-36s %-80s %s' % (job['name'], job['policy'], job['npc_decks']))
        return
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
