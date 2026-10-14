#!/usr/bin/env python3
"""Fourteenth battery (prepared 13 October 2026): confirm, on new seeds, the two ideas that passed
on 13 October 2026. Spec in sim/tests/test_battery_round14.py.

    python3 lab/battery_round14.py PORT [--pod I/N] [--dry-run]
"""
import argparse

import battery_round11 as base

TESTS = (('fusion25', 'strong'), ('fusion25', 'strong'), ('spy-first', 'original'), ('spy-first', 'original'))
SEED_BASE = 2501


def jobs(pod=None):
    out = []
    for i, (idea, decks) in enumerate(TESTS):
        job = base.job(idea, decks, SEED_BASE + i)
        job['name'] = 'Confirm %s %s seed %d' % (idea, decks, SEED_BASE + i)
        out.append(job)
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
            print('%-40s %-56s %s' % (j['name'], j['policy'], j['npc_decks']))
        else:
            print(j['name'], base.post(a.port, '/api/job', j)[:80])


if __name__ == '__main__':
    main()
