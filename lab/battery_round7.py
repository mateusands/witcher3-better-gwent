#!/usr/bin/env python3
"""Seventh battery (prepared 2026-10-12): no self-harm, the Adaptive hero fallback, and fresh
deck-mode charts with the decks shipped today.

    python3 lab/battery_round7.py PORT [--seeds 1001] [--cells balanced:hard,...]
                                  [--variants scene,allow-self-harm,strictheroes] [--half 0|1]

Fair scene (player-mulligan+base-mulligan); NPC switches only. Variants per cell:
- scene: the shipped AI and decks (each task also plays the native AI, for the charts);
- allow-self-harm: the NPC keeps the rule from before the no-self-harm fix (Scorch that burns
  only its own cards, a wasted leader ability with an empty hand);
- strictheroes: Adaptive faction heroes without the every-hero fallback (Adaptive cells only).
--half splits every job by task index between two servers (0: first half, 1: second half).
"""
import argparse
import json
import sqlite3
import urllib.request

SCENE = 'player-mulligan+base-mulligan'


def post(port, path, body):
    req = urllib.request.Request('http://127.0.0.1:%d%s' % (port, path), json.dumps(body).encode(),
                                 {'Content-Type': 'application/json'})
    return urllib.request.urlopen(req, timeout=600).read().decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('port', type=int)
    ap.add_argument('--seeds', default='1001')
    ap.add_argument('--cells', default='balanced:medium,balanced:hard,strong:medium,strong:hard')
    ap.add_argument('--variants', default='scene,allow-self-harm,strictheroes')
    ap.add_argument('--half', type=int, choices=(0, 1))
    ap.add_argument('--db', default='/srv/data/db/lab.sqlite3')
    a = ap.parse_args()
    base = dict(source='player', seeds=[int(s) for s in a.seeds.split(',')])
    jobs = []
    variants = a.variants.split(',')
    for cell in a.cells.split(','):
        decks, level = cell.split(':')
        for v in variants:
            if v == 'scene':
                jobs.append(dict(base, name='scene %s %s' % (decks, level), policy='response-v8:' + SCENE,
                                 profile=level, npc_decks=decks))
            elif v == 'allow-self-harm':
                jobs.append(dict(base, name='AB %s %s %s' % (v, decks, level),
                                 policy='response-v8:%s+%s' % (SCENE, v), profile=level, npc_decks=decks))
            elif v == 'strictheroes' and decks == 'balanced':
                jobs.append(dict(base, name='AB %s %s %s' % (v, decks, level), policy='response-v8:' + SCENE,
                                 profile=level, npc_decks='%s:%s' % (decks, v)))
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
