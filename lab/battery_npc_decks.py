#!/usr/bin/env python3
"""Battery for a Lab burst (prepared 2026-10-11): queue every job on a running Lab.

    python3 battery.py PORT [--pairs N] [--seeds 201,202] [--hunt-seeds 301]

1. NPC deck modes after the muster fix: original / balanced (Adaptive) / strong x 4 levels.
2. A/B weather-zero (hard, expert) on Adaptive decks, same seeds as 1.
3. A/B NPC mulligan (evaluated, structural, leader-weather only) on Adaptive decks, expert.
3b. A/B decoy3 (3 Decoys against Nilfgaard / Northern Kingdoms decks), Adaptive and Strong, expert.
4. Blunder hunts on Adaptive and Strong decks, expert.
"""
import argparse
import json
import urllib.request

LEVELS = ('easy', 'medium', 'hard', 'expert')


def post(port, body):
    req = urllib.request.Request('http://127.0.0.1:%d/api/job' % port, json.dumps(body).encode(),
                                 {'Content-Type': 'application/json'})
    return urllib.request.urlopen(req, timeout=600).read().decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('port', type=int)
    ap.add_argument('--pairs', type=int)
    ap.add_argument('--seeds', default='201,202')
    ap.add_argument('--hunt-seeds', default='301')
    a = ap.parse_args()
    seeds = [int(s) for s in a.seeds.split(',')]
    hunt_seeds = [int(s) for s in a.hunt_seeds.split(',')]
    base = dict(source='player', seeds=seeds, **({'pairs': a.pairs} if a.pairs else {}))
    jobs = []
    for mode in ('original', 'balanced', 'strong'):
        for level in LEVELS:
            jobs.append(dict(base, name='decks %s %s' % (mode, level), policy='response-v8', profile=level,
                             **({'npc_decks': mode} if mode != 'original' else {})))
    for level in ('hard', 'expert'):
        jobs.append(dict(base, name='AB weather-zero %s' % level, policy='response-v8:weather-zero', profile=level,
                         npc_decks='balanced'))
    for variant in ('mulligan', 'mulligan-structural', 'mulligan-leader'):
        jobs.append(dict(base, name='AB %s expert' % variant, policy='response-v8:%s' % variant, profile='expert',
                         npc_decks='balanced'))
    for mode in ('balanced', 'strong'):
        jobs.append(dict(base, name='AB decoy3 %s expert' % mode, policy='response-v8', profile='expert',
                         npc_decks='%s:decoy3' % mode))
    for mode in ('balanced', 'strong'):
        jobs.append(dict(base, name='hunt %s expert' % mode, kind='hunt', policy='response-v8', profile='expert',
                         npc_decks=mode, seeds=hunt_seeds))
    for job in jobs:
        print(job['name'], post(a.port, job)[:120])


if __name__ == '__main__':
    main()
