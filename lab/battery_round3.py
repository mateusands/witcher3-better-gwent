#!/usr/bin/env python3
"""Third battery (prepared 2026-10-12, three difficulty levels): queue jobs on a running Lab.

    python3 lab/battery_round3.py PORT [--seeds 601] [--part modes|ab|all]

Scene of the shipped mod: the player exchanges opening cards too; the NPC uses the shipped
exchange (leader weather first). Levels easy / medium / hard = the mod's Easy / Normal / Hard.
- modes: NPC deck modes (original, Adaptive, Strong) x three levels (README charts).
- ab: mulligan-full (leader weather, then a Muster copy called from the deck, then evaluated)
  and spies4 (NPC decks with up to 4 spies), Adaptive and Strong, Normal and Hard.
"""
import argparse
import json
import urllib.request

SCENE = 'player-mulligan+base-mulligan'


def post(port, body):
    req = urllib.request.Request('http://127.0.0.1:%d/api/job' % port, json.dumps(body).encode(),
                                 {'Content-Type': 'application/json'})
    return urllib.request.urlopen(req, timeout=600).read().decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('port', type=int)
    ap.add_argument('--seeds', default='601')
    ap.add_argument('--part', default='all', choices=('modes', 'ab', 'all'))
    ap.add_argument('--levels', default='easy,medium,hard')
    a = ap.parse_args()
    seeds = [int(s) for s in a.seeds.split(',')]
    base = dict(source='player', seeds=seeds)
    levels = a.levels.split(',')
    jobs = []
    if a.part in ('modes', 'all'):
        for mode in ('original', 'balanced', 'strong'):
            for level in levels:
                jobs.append(dict(base, name='modes %s %s' % (mode, level), policy='response-v8:' + SCENE,
                                 profile=level, **({'npc_decks': mode} if mode != 'original' else {})))
    if a.part in ('ab', 'all'):
        for decks in ('balanced', 'strong'):
            for level in [l for l in levels if l != 'easy']:
                jobs.append(dict(base, name='AB mulligan-full %s %s' % (decks, level),
                                 policy='response-v8:%s+mulligan-full' % SCENE, profile=level, npc_decks=decks))
                jobs.append(dict(base, name='AB spies4 %s %s' % (decks, level), policy='response-v8:' + SCENE,
                                 profile=level, npc_decks='%s:spies4' % decks))
    for job in jobs:
        print(job['name'], post(a.port, job)[:80])


if __name__ == '__main__':
    main()
