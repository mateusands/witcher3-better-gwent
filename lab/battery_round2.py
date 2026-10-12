#!/usr/bin/env python3
"""Second battery (prepared 2026-10-12): queue every job on a running Lab.

    python3 lab/battery_round2.py PORT [--pairs N] [--seeds 401,402] [--hunt-seeds 501]

Every arm plays the fair scene of the shipped mod: the player exchanges opening cards too and
the NPC uses the shipped exchange ("player-mulligan+base-mulligan"). Experiment switches change
the NPC only. NPC decks Adaptive and Strong; Medium, Hard and Expert.

A/B (each against the scene alone):
- lead-pass: with a round lost, pass a led round when no public hypothesis can overtake.
- known-hand: remember cards publicly returned to the player's hand (Decoy).
- mulligan-combined: exchange the weather card the leader can pull first, then evaluated.
- weather-zero: weather that changes nothing now counts as wasted (earlier test changed both sides).
- skellige: Mardroeme/Ermion/Berserkers, Clan Dimun Pirate and Kambi in the search model
  (sim/skellige_position.py, checked against the native engine); only Skellige NPCs change.
- budget-half: half the search nodes (thinking time and frame drops vs strength).
- all strategy switches together (without budget-half).
Hunts: Adaptive Expert against my real decks with the scene, for the next mistake patterns.
"""
import argparse
import json
import urllib.request

SCENE = 'player-mulligan+base-mulligan'
SWITCHES = ('lead-pass', 'known-hand', 'mulligan-combined', 'weather-zero', 'skellige', 'budget-half',
            'lead-pass+known-hand+mulligan-combined+weather-zero+skellige')


def post(port, body):
    req = urllib.request.Request('http://127.0.0.1:%d/api/job' % port, json.dumps(body).encode(),
                                 {'Content-Type': 'application/json'})
    return urllib.request.urlopen(req, timeout=600).read().decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('port', type=int)
    ap.add_argument('--pairs', type=int)
    ap.add_argument('--seeds', default='401')
    ap.add_argument('--hunt-seeds', default='501')
    ap.add_argument('--cells', help='only these "decks:level" cells, comma-separated (split across pods)')
    ap.add_argument('--hunt', action='store_true', help='with --cells: also queue the hunt')
    ap.add_argument('--levels', default='', help='seeds for fresh pool benchmarks of all four levels, e.g. 700,701')
    ap.add_argument('--no-ab', action='store_true')
    ap.add_argument('--ladder', default='', help='node budgets on the Medium profile, e.g. 768,1024,1536')
    a = ap.parse_args()
    cells = set(a.cells.split(',')) if a.cells else None
    seeds = [int(s) for s in a.seeds.split(',')]
    base = dict(source='player', seeds=seeds, **({'pairs': a.pairs} if a.pairs else {}))
    jobs = []
    for decks in ('balanced', 'strong'):
        for level in ('medium', 'hard', 'expert'):
            if a.no_ab or (cells is not None and '%s:%s' % (decks, level) not in cells):
                continue
            jobs.append(dict(base, name='scene %s %s' % (decks, level), policy='response-v8:' + SCENE,
                             profile=level, npc_decks=decks))
            for switch in SWITCHES:
                jobs.append(dict(base, name='AB %s %s %s' % (switch, decks, level),
                                 policy='response-v8:%s+%s' % (SCENE, switch), profile=level, npc_decks=decks))
    # Fresh shipped-AI pool benchmarks, same seeds for every level (README levels chart).
    for level in (('easy', 'medium', 'hard', 'expert') if a.levels and not a.ladder else ()):
        jobs.append(dict(source='pool', name='levels %s %s' % (level, a.levels), policy='response-v8', profile=level,
                         seeds=[int(x) for x in a.levels.split(',')]))
    # Difficulty ladder: the Medium search profile with other node budgets, same seeds as --levels.
    for nodes in (a.ladder.split(',') if a.ladder else ()):
        jobs.append(dict(source='pool', name='ladder medium nodes%s %s' % (nodes, a.levels), profile='medium',
                         policy='response-v8:nodes%s' % nodes, seeds=[int(x) for x in a.levels.split(',')]))
    if (cells is None and not a.no_ab) or a.hunt:
        jobs.append(dict(base, name='hunt scene balanced expert (my decks)', kind='hunt',
                         policy='response-v8:' + SCENE, profile='expert', npc_decks='balanced',
                         seeds=[int(s) for s in a.hunt_seeds.split(',')], player_filter='recorded', game_seat=True))
    for job in jobs:
        print(job['name'], post(a.port, job)[:120])


if __name__ == '__main__':
    main()
