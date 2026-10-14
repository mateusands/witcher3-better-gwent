#!/usr/bin/env python3
"""Lab autopilot: the Lab server keeps testing ideas for the NPC, confirms every pass on new seeds,
and reports which ideas are proven. Spec in sim/tests/test_autopilot.py.

    python3 lab/autopilot.py [--port 8765] [--explore 3] [--every 300] [--report PATH] [--once]

Typically a service on the Google Cloud server (see the gwent-gcp-lab notes). The job names in the
Lab are its memory: "AUTO idea <switches> <decks>" and "AUTO confirm <id> <k>".
"""
import argparse
import json
import time
import urllib.request
import zlib
from pathlib import Path

SCENE = 'response-v8:player-mulligan+base-mulligan'
IDEA_PREFIX = 'AUTO idea '
CONFIRM_PREFIX = 'AUTO confirm '

# Idea families, most promising first (13 October 2026: fusion25 passed on Strong, spy-first on
# Original; weights, beliefs, beam, pass margins and caution were all worse).
IDEAS = tuple(
    [('fusion25', 'original'), ('fusion20', 'strong'), ('fusion30', 'strong'),
     ('spy-first+fusion25', 'original'), ('spy-first+fusion25', 'strong'), ('spy-first+fusion25', 'balanced')]
    + [('fusion%d' % n, decks) for n in (20, 30, 15, 35, 10, 40) for decks in ('balanced', 'original')]
    + [('fusion%d' % n, 'strong') for n in (15, 35, 10, 40)])

# Decided on Runpod, 13 October 2026 (round 15): not queued again here. The ones that passed
# there are confirmed here on new seeds.
DECIDED_ELSEWHERE = IDEAS[3:12]
PASSED_ELSEWHERE = ()        # their confirmations ran on Runpod too (round 16)
# Final verdicts on Runpod, 13 October 2026 (rounds 11 to 17): passed three times, or failed a
# confirmation.
PROMOTED_ELSEWHERE = (('spy-first', 'original'), ('fusion20', 'original'))
REJECTED_ELSEWHERE = (('fusion15', 'original'), ('spy-first+fusion25', 'original'), ('fusion25', 'strong'))
# Ideas left open on Runpod, tested here before the list.
PRIORITY_IDEAS = (('r1cap20', 'original'),)


def outside_tag(switches, decks):
    return 'runpod:%s:%s' % (switches, decks)


def idea_job(switches, decks):
    name = '%s%s %s' % (IDEA_PREFIX, switches, decks)
    seed = 40000 + zlib.crc32(name.encode()) % 50000
    return dict(kind='ab', name=name, source='player', profile='hard', seeds=[seed],
                policy='%s+%s' % (SCENE, switches), npc_decks=decks,
                base_policy=SCENE, base_decks=decks, batch=100, max_tasks=6000)


def _verdict(job):
    return ((job.get('params') or {}).get('verdict') or {}).get('result')


def _confirms(job):
    """The key (job id, or tag of an outside result) a confirmation job confirms, or None."""
    if job['name'].startswith(CONFIRM_PREFIX):
        return job['name'][len(CONFIRM_PREFIX):].split()[0]
    return None


def _confirm_jobs(key, p, seed):
    return [dict(kind='ab', name='%s%s %d' % (CONFIRM_PREFIX, key, k), source='player', profile='hard',
                 seeds=[seed + k], policy=p['policy'], npc_decks=p['npc_decks'], base_policy=p['base_policy'],
                 base_decks=p['base_decks'], batch=100, max_tasks=6000) for k in (1, 2)]


def outside_confirmations(passed):
    """The two confirmation jobs of each outside pass (switches, decks), with their fixed seeds."""
    out = []
    for switches, decks in passed:
        tag = outside_tag(switches, decks)
        out += _confirm_jobs(tag, idea_job(switches, decks), 95000 + zlib.crc32(tag.encode()) % 4000 * 3)
    return out


def confirmations(jobs):
    """Two confirmation jobs (new seeds) for every passed 'ab' job, and every outside pass,
    not yet confirmed."""
    confirmed = {_confirms(j) for j in jobs} - {None}
    out = []
    for job in jobs:
        if job['kind'] != 'ab' or _verdict(job) != 'better' or _confirms(job) is not None or str(job['id']) in confirmed:
            continue
        out += _confirm_jobs(job['id'], job['params'], 90000 + job['id'] * 10)
    out += [j for j in outside_confirmations(PASSED_ELSEWHERE) if _confirms(j) not in confirmed]
    return out


def report(jobs):
    by_target = {}
    for job in jobs:
        target = _confirms(job)
        if target is not None:
            by_target.setdefault(target, []).append(job)
    out = dict(promoted=[], rejected=[], waiting=[], tested=[])
    outside = [dict(id=outside_tag(s, d), name='Runpod ' + idea_job(s, d)['name'], kind='ab', status='done',
                    params=dict(idea_job(s, d), verdict=dict(result='better'))) for s, d in PASSED_ELSEWHERE]
    for kind, verdicts in (('promoted', PROMOTED_ELSEWHERE), ('rejected', REJECTED_ELSEWHERE)):
        for s, d in verdicts:
            out[kind].append(dict(id=outside_tag(s, d), name='Runpod %s %s' % (s, d), policy=idea_job(s, d)['policy'],
                                  decks=d, verdict=dict(result='better' if kind == 'promoted' else 'not better')))
    for job in jobs + outside:
        if job['kind'] != 'ab' or _confirms(job) is not None:
            continue
        p = job.get('params') or {}
        entry = dict(id=job['id'], name=job['name'], policy=p.get('policy'), decks=p.get('npc_decks'),
                     verdict=p.get('verdict'))
        if _verdict(job):
            out['tested'].append(entry)
        if _verdict(job) != 'better':
            continue
        checks = [_verdict(c) for c in by_target.get(str(job['id']), [])]
        entry['confirmations'] = checks
        if any(v in ('not better', 'undecided') for v in checks):
            out['rejected'].append(entry)
        elif len(checks) >= 2 and all(v == 'better' for v in checks):
            out['promoted'].append(entry)
        else:
            out['waiting'].append(entry)
    return out


def next_ideas(jobs, families=None, explore=3):
    names = {j['name'] for j in jobs}
    active = sum(1 for j in jobs if j['name'].startswith(IDEA_PREFIX) and j['status'] == 'active')
    out = []
    for switches, decks in (PRIORITY_IDEAS + IDEAS if families is None else families):
        if active + len(out) >= explore:
            break
        if (switches, decks) in DECIDED_ELSEWHERE:
            continue
        job = idea_job(switches, decks)
        if job['name'] not in names:
            out.append(job)
    return out


def _api(port, path, body=None):
    url = 'http://127.0.0.1:%d/api/%s' % (port, path)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data, {'Content-Type': 'application/json'} if data else {})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def step(port, explore, report_path):
    jobs = [dict(id=j['id'], name=j['name'], kind=j['kind'], status=j['status'], params=j['params'])
            for j in _api(port, 'status')['jobs']]
    queued = confirmations(jobs) + next_ideas(jobs, explore=explore)
    for body in queued:
        _api(port, 'job', body)
    summary = dict(report(jobs), updated=time.strftime('%Y-%m-%d %H:%M:%S'), queued=[b['name'] for b in queued])
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).write_text(json.dumps(summary, indent=1))
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--explore', type=int, default=3)
    ap.add_argument('--every', type=int, default=300)
    ap.add_argument('--report', default='/srv/gwentailab/data/autopilot/report.json')
    ap.add_argument('--once', action='store_true')
    a = ap.parse_args()
    while True:
        try:
            s = step(a.port, a.explore, a.report)
            print(time.strftime('%H:%M'), 'promoted', len(s['promoted']), 'waiting', len(s['waiting']),
                  'queued', s['queued'], flush=True)
        except OSError as exc:          # the Lab restarting: try again next time
            print('lab not reachable:', exc, flush=True)
        if a.once:
            return
        time.sleep(a.every)


if __name__ == '__main__':
    main()
