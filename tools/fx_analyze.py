#!/usr/bin/env python3
"""Summarize observed Scorch batches; never infer missing completion callbacks.

Usage: python3 tools/fx_analyze.py [game/records/gNNN.json ...]
Trace rows come from build_recorder.py --trace-fx and are outside logical replay events.
"""
import argparse
import glob
import json
from collections import defaultdict


def analyze(trace):
    starts = {}
    ends = {}
    applied = {}
    groups = defaultdict(list)
    errors = []
    for row in trace:
        fx_id = row['fxId']
        target = {'start': starts, 'end': ends, 'applied': applied}.get(row['phase'])
        if target is None:
            errors.append('unknown phase %r' % row['phase'])
            continue
        if fx_id in target:
            errors.append('duplicate %s for FX %d' % (row['phase'], fx_id))
            continue
        target[fx_id] = row
        if row['phase'] == 'start':
            groups[(row['frame'], row['eventIndex'])].append(fx_id)
        elif fx_id not in starts:
            errors.append('FX %d completed before its start was recorded' % fx_id)
    batches = []
    for (frame, event_index), ids in groups.items():
        completed = [fx for fx in ends if fx in ids]
        permutation = [ids.index(fx) + 1 for fx in completed]
        missing = [fx for fx in ids if fx not in ends]
        returned = [fx for fx in applied if fx in ids]
        if missing:
            order = 'incomplete'
        elif completed == ids:
            order = 'creation order'
        elif completed == ids[1:] + ids[:1]:
            order = 'first finishes last'
        else:
            order = 'other'
        for fx in completed:
            start, end = starts[fx], ends[fx]
            if start['card'] != end['card'] or end['timeMs'] < start['timeMs'] or end['frame'] < frame:
                errors.append('inconsistent completion for FX %d' % fx)
        batches.append(dict(startFrame=frame, eventIndex=event_index, fxIds=ids,
                            cards=[starts[fx]['card'] for fx in ids], completionOrder=permutation,
                            order=order, missing=missing,
                            endFrames=[ends[fx]['frame'] for fx in completed],
                            durationsMs=[ends[fx]['timeMs'] - starts[fx]['timeMs'] for fx in completed],
                            startDepths=[starts[fx]['depth'] for fx in ids],
                            endDepths=[ends[fx]['depth'] for fx in completed],
                            callbackReturnsObserved=bool(returned),
                            callbackReturnOrder=[ids.index(fx) + 1 for fx in returned],
                            callbackReturnsMissing=[fx for fx in ids if fx not in applied],
                            callbackReturnFrames=[applied[fx]['frame'] for fx in returned]))
    for fx, row in applied.items():
        entry = ends.get(fx)
        if entry is None:
            errors.append('FX %d callback return has no entry record' % fx)
        elif row['card'] != entry['card'] or row['timeMs'] < entry['timeMs'] or row['frame'] < entry['frame']:
            errors.append('inconsistent callback return for FX %d' % fx)
    return batches, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paths', nargs='*')
    parser.add_argument('--json', action='store_true', help='emit machine-readable reports')
    args = parser.parse_args()
    reports = []
    for path in args.paths or sorted(glob.glob('game/records/g[0-9][0-9][0-9].json')):
        with open(path) as stream:
            match = json.load(stream)
        trace = match.get('fxTrace', [])
        batches, errors = analyze(trace)
        reports.append(dict(path=path, traceRows=len(trace), batches=batches, errors=errors))
    if args.json:
        print(json.dumps(reports, indent=2))
    else:
        for report in reports:
            print('%s: %d trace rows, %d batches' % (report['path'], report['traceRows'], len(report['batches'])))
            for batch in report['batches']:
                print('  event %d frame %d cards=%s order=%s (%s), end frames=%s, durations=%s ms' %
                      (batch['eventIndex'], batch['startFrame'], batch['cards'], batch['completionOrder'],
                       batch['order'], batch['endFrames'], batch['durationsMs']))
                if batch['callbackReturnsObserved']:
                    print('    callback return order=%s, missing=%s' % (batch['callbackReturnOrder'], batch['callbackReturnsMissing']))
            for error in report['errors']:
                print('  ERROR: ' + error)
    return int(any(report['errors'] for report in reports))


if __name__ == '__main__':
    raise SystemExit(main())
