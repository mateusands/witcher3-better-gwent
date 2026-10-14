#!/usr/bin/env python3
"""Twelfth battery (prepared 13 October 2026): switches of the NPC's response search, as paired
SPRT A/B tests on rented servers. Spec in sim/tests/test_battery_round12.py; the switches in
sim/tests/test_search_switches.py.

    python3 lab/battery_round12.py PORT [--pod I/N] [--dry-run]
"""
import argparse

import battery_round11 as base

SWITCHES = ('beliefs6', 'beliefs8', 'beam4', 'beam12', 'pass10', 'pass25', 'caution25', 'caution50')
TESTS = tuple((s, decks) for s in SWITCHES for decks in ('balanced', 'strong'))
SEED_BASE = 2301


def jobs(pod=None):
    out = [base.job(idea, decks, SEED_BASE + i) for i, (idea, decks) in enumerate(TESTS)]
    if pod:
        index, count = pod
        out = out[index::count]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('port', type=int)
    ap.add_argument('--pod', help='I/N: queue only this server\'s share of the tests')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    pod = tuple(int(v) for v in a.pod.split('/')) if a.pod else None
    for j in jobs(pod):
        if a.dry_run:
            print('%-28s %-56s %s' % (j['name'], j['policy'], j['npc_decks']))
        else:
            print(j['name'], base.post(a.port, '/api/job', j)[:80])


if __name__ == '__main__':
    main()
