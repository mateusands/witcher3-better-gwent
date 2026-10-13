#!/usr/bin/env python3
"""Tenth battery (prepared 13 October 2026): the spy engine, from the Novigrad tournament
(g158-g161) and the owner's own Northern Realms spy deck. Spec in sim/tests/test_spy_engine.py
and sim/tests/test_spy_first.py.

    python3 lab/battery_round10.py PORT [--seeds 1401] [--cells balanced:hard,strong:hard]
                                   [--variants deck|ai|all|NAME,...] [--scene] [--dry-run]

Fair scene (player-mulligan+base-mulligan); NPC switches only. The scene itself is queued only
with --scene (its baseline may come from another server running the same code and seeds).
Deck variants (npc_decks '<decks>:<flags>'):
- spyval: a spy counts by its draw, not its power, in the Adaptive strength measure (Adaptive only);
- spymirror / spymirror1: NPC spies limited to the player's (one fewer), at least one;
- mirror+decoys / mirror+decoyhalf: the mirror plus as many Decoys as the player's spies (half);
- decoy3: three Decoys against a Nilfgaard or Northern Realms player deck;
- witcherone: one of Geralt and Ciri, also in the every-hero fallback (Adaptive only).
AI variants (policy switches): spy-first, draw15, draw20.
"""
import argparse
import json
import urllib.request

SCENE = 'player-mulligan+base-mulligan'
DECK = {'spyval': 'spyval', 'spymirror': 'spymirror', 'spymirror1': 'spymirror1',
        'mirror+decoys': 'spymirror+decoymirror', 'mirror+decoyhalf': 'spymirror+decoyhalf',
        'decoy3': 'decoy3', 'witcherone': 'witcherone'}
ADAPTIVE_ONLY = {'spyval', 'witcherone'}
AI = ('spy-first', 'draw15', 'draw20')
# The Runpod plan (13 October 2026): deck variants on Hard with two seeds, Normal with its own
# scene, AI variants on Hard. Split servers queue it whole with --plan, then keep their ranges.
PLAN = ((('balanced:hard', 'strong:hard'), list(DECK), [1401], False),
        (('balanced:hard', 'strong:hard'), list(DECK), [1402], False),
        (('balanced:medium', 'strong:medium'), list(DECK), [1401], True),
        (('balanced:hard', 'strong:hard'), list(AI), [1401], False))


def post(port, path, body):
    req = urllib.request.Request('http://127.0.0.1:%d%s' % (port, path), json.dumps(body).encode(),
                                 {'Content-Type': 'application/json'})
    return urllib.request.urlopen(req, timeout=600).read().decode()


def jobs_for(cells, variants, seeds, scene=False):
    base = dict(source='player', seeds=seeds)
    jobs = []
    for cell in cells:
        decks, level = cell.split(':')
        if scene:
            jobs.append(dict(base, name='scene %s %s' % (decks, level), policy='response-v8:' + SCENE,
                             profile=level, npc_decks=decks))
        for v in variants:
            if v in DECK:
                if v in ADAPTIVE_ONLY and decks != 'balanced':
                    continue
                jobs.append(dict(base, name='AB %s %s %s' % (v, decks, level), policy='response-v8:' + SCENE,
                                 profile=level, npc_decks='%s:%s' % (decks, DECK[v])))
            elif v in AI:
                jobs.append(dict(base, name='AB %s %s %s' % (v, decks, level),
                                 policy='response-v8:%s+%s' % (SCENE, v), profile=level, npc_decks=decks))
            else:
                raise SystemExit('unknown variant %s' % v)
    return jobs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('port', type=int)
    ap.add_argument('--seeds', default='1401')
    ap.add_argument('--cells', default='balanced:hard,strong:hard')
    ap.add_argument('--variants', default='deck')
    ap.add_argument('--scene', action='store_true')
    ap.add_argument('--continuous', action='store_true')
    ap.add_argument('--dry-run', action='store_true', help='print the jobs without queueing them')
    ap.add_argument('--plan', action='store_true', help='the whole Runpod plan of 13 October 2026 (PLAN)')
    a = ap.parse_args()
    names = {'deck': list(DECK), 'ai': list(AI), 'all': list(DECK) + list(AI)}.get(a.variants, a.variants.split(','))
    jobs = jobs_for(a.cells.split(','), names, [int(s) for s in a.seeds.split(',')], a.scene)
    if a.plan:
        jobs = [j for cells, variants, seeds, scene in PLAN for j in jobs_for(cells, variants, seeds, scene)]
    for job in jobs:
        job['continuous'] = a.continuous
        if a.dry_run:
            print('%-40s %-60s %s' % (job['name'], job['policy'], job['npc_decks']))
        else:
            print(job['name'], post(a.port, '/api/job', job)[:80])


if __name__ == '__main__':
    main()
