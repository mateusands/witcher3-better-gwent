#!/usr/bin/env python3
"""Sixteenth battery (prepared 13 October 2026): the autopilot's confirmations of the three
Original-mode passes of round 15, run on Runpod as the very same jobs. Spec in
sim/tests/test_battery_round16.py.

    python3 lab/battery_round16.py PORT [--dry-run]
"""
import argparse

import autopilot
import battery_round11 as base


ROUND15_PASSES = (('fusion15', 'original'), ('spy-first+fusion25', 'original'), ('fusion20', 'original'))


def jobs():
    return autopilot.outside_confirmations(ROUND15_PASSES)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('port', type=int)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    for j in jobs():
        if a.dry_run:
            print('%-50s %-60s %s' % (j['name'], j['policy'], j['npc_decks']))
        else:
            print(j['name'], base.post(a.port, '/api/job', j)[:80])


if __name__ == '__main__':
    main()
