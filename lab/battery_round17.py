#!/usr/bin/env python3
"""Seventeenth battery (prepared 13 October 2026): the round-1 spending ceiling r1capN (match g167), run on
rented servers as autopilot idea jobs. Spec in sim/tests/test_battery_round17.py.

    python3 lab/battery_round17.py PORT [--pod I/N] [--dry-run]
"""
import argparse

import autopilot
import battery_round11 as base



def jobs(pod=None):
    out = [autopilot.idea_job('r1cap%d' % n, d) for n in (10, 15, 20) for d in ('balanced', 'strong', 'original')]
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
