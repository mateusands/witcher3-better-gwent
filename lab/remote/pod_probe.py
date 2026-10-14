#!/usr/bin/env python3
"""Work left on a rented Lab server, for pod.sh wait. Spec in sim/tests/test_pod_probe.py.

    python3 lab/remote/pod_probe.py [PORT]   ->   STATUS <unix time> <work left> <tasks done>

A sequential job (kind 'ab' or 'deck-tune') that is still active always counts as work left: it
queues its next batch only after the last one, and becomes 'done' when it decides.
"""
import json
import sys
import time
import urllib.request

SEQUENTIAL = ('ab', 'deck-tune')


def work_left(jobs):
    left = 0
    for j in jobs:
        if j['status'] != 'active':
            continue
        left += max(0, j['total'] - j['done'] - (j.get('errors') or 0))
        if j['kind'] in SEQUENTIAL:
            left += 1
    return left


def done(jobs):
    return sum(j['done'] for j in jobs)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    with urllib.request.urlopen('http://127.0.0.1:%d/api/status' % port, timeout=30) as r:
        jobs = json.load(r)['jobs']
    print('STATUS', int(time.time()), work_left(jobs), done(jobs))


if __name__ == '__main__':
    main()
