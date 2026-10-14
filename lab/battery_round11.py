#!/usr/bin/env python3
"""Eleventh battery (prepared 13 October 2026): paired SPRT A/B tests of the pending NPC ideas on
three rented servers. Spec in sim/tests/test_battery_round11.py.

    python3 lab/battery_round11.py PORT [--pod I/N] [--dry-run]

Each test is a Lab job of kind 'ab' (candidate against the fair scene on the same matchups) that
stops when the SPRT decides. The Google Cloud server already runs spy-first (balanced, strong),
draw15 (balanced) and spyval (balanced); they are not repeated here.
Ideas: NPC switches (spy-first, draw15, draw20, reserve35, r1-chase) joined with '+', and the
deck flag spyval (Adaptive only).
"""
import argparse
import json
import urllib.request

SCENE = 'response-v8:player-mulligan+base-mulligan'
DECK_FLAGS = {'spyval'}
TESTS = (('spy-first', 'original'), ('spy-first+spyval', 'balanced'),
         ('draw15', 'strong'), ('draw15', 'original'), ('draw20', 'balanced'), ('draw20', 'strong'),
         ('reserve35', 'balanced'), ('reserve35', 'strong'), ('reserve35', 'original'),
         ('r1-chase', 'balanced'), ('r1-chase', 'strong'),
         ('spy-first+draw15', 'balanced'), ('spy-first+draw15', 'strong'))
SEED_BASE = 2201


def job(idea, decks, seed):
    parts = idea.split('+')
    switches = [p for p in parts if p not in DECK_FLAGS]
    flags = [p for p in parts if p in DECK_FLAGS]
    return dict(kind='ab', name='SPRT %s %s' % (idea, decks), source='player', profile='hard', seeds=[seed],
                policy='+'.join([SCENE] + switches), npc_decks=':'.join([decks] + (['+'.join(flags)] if flags else [])),
                base_policy=SCENE, base_decks=decks, batch=100, max_tasks=6000)


def jobs(pod=None):
    out = [job(idea, decks, SEED_BASE + i) for i, (idea, decks) in enumerate(TESTS)]
    if pod:
        index, count = pod
        out = out[index::count]
    return out


def post(port, path, body):
    req = urllib.request.Request('http://127.0.0.1:%d%s' % (port, path), json.dumps(body).encode(),
                                 {'Content-Type': 'application/json'})
    return urllib.request.urlopen(req, timeout=600).read().decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('port', type=int)
    ap.add_argument('--pod', help='I/N: queue only this server\'s share of the tests')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    pod = tuple(int(v) for v in a.pod.split('/')) if a.pod else None
    for j in jobs(pod):
        if a.dry_run:
            print('%-32s %-62s %s' % (j['name'], j['policy'], j['npc_decks']))
        else:
            print(j['name'], post(a.port, '/api/job', j)[:80])


if __name__ == '__main__':
    main()
