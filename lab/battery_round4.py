#!/usr/bin/env python3
"""Fourth battery (prepared 2026-10-12): ideas from hand-built archetype decks and in-game play.

    python3 lab/battery_round4.py PORT [--seeds 701] [--cells balanced:hard,strong:hard]

Fair scene (player-mulligan+base-mulligan); NPC switches only. Per cell (decks x level):
- scene (baseline);
- deck switches: kit4, kit2 (at most 4 / 2 special cards), units22 (Strong with 22 units),
  notriss (no Triss), kit4+units22+notriss;
- AI switches: scorch-prior (every other sampled player hand holds Scorch), reserve35
  (kept resources weigh 0.35 instead of 0.25, so a led round is passed sooner).
"""
import argparse
import json
import urllib.request

SCENE = 'player-mulligan+base-mulligan'
DECK_SWITCHES = ('kit4', 'kit2', 'units22', 'notriss', 'kit4+units22+notriss')
AI_SWITCHES = ('scorch-prior', 'reserve35')


def post(port, body):
    req = urllib.request.Request('http://127.0.0.1:%d/api/job' % port, json.dumps(body).encode(),
                                 {'Content-Type': 'application/json'})
    return urllib.request.urlopen(req, timeout=600).read().decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('port', type=int)
    ap.add_argument('--seeds', default='701')
    ap.add_argument('--cells', default='balanced:medium,balanced:hard,strong:medium,strong:hard')
    a = ap.parse_args()
    base = dict(source='player', seeds=[int(s) for s in a.seeds.split(',')])
    jobs = []
    for cell in a.cells.split(','):
        decks, level = cell.split(':')
        jobs.append(dict(base, name='scene %s %s' % (decks, level), policy='response-v8:' + SCENE,
                         profile=level, npc_decks=decks))
        for switch in DECK_SWITCHES:
            if switch == 'units22' and decks != 'strong':
                continue                      # Adaptive grows its unit count to the target
            jobs.append(dict(base, name='AB %s %s %s' % (switch, decks, level), policy='response-v8:' + SCENE,
                             profile=level, npc_decks='%s:%s' % (decks, switch)))
        for switch in AI_SWITCHES:
            jobs.append(dict(base, name='AB %s %s %s' % (switch, decks, level),
                             policy='response-v8:%s+%s' % (SCENE, switch), profile=level, npc_decks=decks))
    for job in jobs:
        print(job['name'], post(a.port, job)[:80])


if __name__ == '__main__':
    main()
