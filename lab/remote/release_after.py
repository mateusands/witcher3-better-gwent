#!/usr/bin/env python3
"""Release queued Lab jobs when a priority batch ends (runs on the Lab server).

Spec: while some jobs run with priority, others wait paused; once every awaited job has no
work left (all tasks done or failed, or the job superseded), the waiting jobs are set active.
An awaited id the Lab does not list is a mistake: it raises instead of releasing everything.

  release_after.py --wait 13,14,15 --release 3,5,16 [--every 120] [--port 8765]
Typically started as a one-shot unit: sudo systemd-run --unit gwent-release python3 release_after.py ...
"""
import argparse
import json
import time
import urllib.request

PORT = 8765


def post(path, body):
    req = urllib.request.Request('http://127.0.0.1:%d/api/%s' % (PORT, path), json.dumps(body).encode(),
                                 {'Content-Type': 'application/json'})
    urllib.request.urlopen(req, timeout=30).read()


def jobs():
    with urllib.request.urlopen('http://127.0.0.1:%d/api/status' % PORT, timeout=30) as r:
        return json.load(r)['jobs']


def finished(status, wait):
    by_id = {j['id']: j for j in status}
    for jid in wait:
        j = by_id[jid]                      # KeyError on an unknown id
        if j['status'] != 'superseded' and j['total'] - j['done'] - (j.get('errors') or 0) > 0:
            return False
    return True


def release(ids):
    for jid in ids:
        post('job/status', {'id': jid, 'status': 'active'})


def main():
    global PORT
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--wait', required=True)
    parser.add_argument('--release', required=True)
    parser.add_argument('--every', type=int, default=120)
    parser.add_argument('--port', type=int, default=PORT)
    args = parser.parse_args()
    PORT = args.port
    wait = {int(x) for x in args.wait.split(',')}
    while not finished(jobs(), wait):
        time.sleep(args.every)
    release([int(x) for x in args.release.split(',')])
    print('released', args.release)


if __name__ == '__main__':
    main()
