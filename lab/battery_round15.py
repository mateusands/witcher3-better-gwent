#!/usr/bin/env python3
"""Fifteenth battery (prepared 13 October 2026): the Lab autopilot's next ideas, run early on
rented servers as the very same jobs. Spec in sim/tests/test_battery_round15.py.

    python3 lab/battery_round15.py PORT [--pod I/N] [--dry-run]
"""
import argparse

import autopilot
import battery_round11 as base

COUNT = 9          # ideas 4 to 12 of the autopilot's list


def jobs(pod=None):
    out = [autopilot.idea_job(s, d) for s, d in autopilot.IDEAS[3:3 + COUNT]]
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
