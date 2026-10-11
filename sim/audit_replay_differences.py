#!/usr/bin/env python3
"""Read-only full-stream difference audit; strict replay tests remain unchanged.

Classify grave-order-only snapshot differences without altering replay state,
recorded expectations, hand/deck/board order or the standard acceptance gate.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
from evaluate import engine_hashes
from evaluate_secured_resources import files_hash
from replay import diff_events
from gwentsim.data import load_match
from gwentsim.rng import ReplayRandom
from gwentsim.gwint.match import run_match

ROOT = Path(__file__).resolve().parents[1]


def grave_order_only(expected, actual):
    if expected['k'] != 'S' or actual['k'] != 'S':
        return False
    a, b = deepcopy(expected), deepcopy(actual)
    for snapshot in (a, b):
        for player in snapshot['players']:
            player['grave'] = sorted(player['grave'])
    return diff_events(a, b) is None


def audit(path):
    match = load_match(path); observed = []; differences = []
    def observe(event):
        index = len(observed); observed.append(deepcopy(event))
        if index >= len(match.events):
            differences.append(dict(event=index, kind=event['k'], graveOrderOnly=False,
                                    detail='extra emitted event'))
            return
        expected = match.events[index]; detail = diff_events(expected, event)
        if detail:
            entry = dict(event=index, kind=event['k'], graveOrderOnly=grave_order_only(expected, event), detail=detail)
            if entry['graveOrderOnly']:
                entry['graves'] = [dict(player=side, expected=a['grave'], observed=b['grave'])
                    for side, (a, b) in enumerate(zip(expected['players'], event['players']))
                    if a['grave'] != b['grave']]
            differences.append(entry)
    random = ReplayRandom(match.randoms()); errors = []
    try:
        human = any(e['k'] in ('H', 'P', 'C') for e in match.events)
        run_match(match.templates.values(), match.decks, match.card_values, random, on_event=observe,
                  double_ai=not human, scripted_events=match.events if human else None)
        random.assert_done()
    except (AssertionError, RuntimeError, ValueError) as exc:
        errors.append(dict(type=type(exc).__name__, detail=str(exc)))
    return dict(record=path.name, expectedEvents=len(match.events), emittedEvents=len(observed),
        allEventsEmitted=len(observed) == len(match.events), errors=errors, differences=differences,
        strictExact=not errors and not differences and len(observed) == len(match.events),
        onlyGraveOrderDiffers=not errors and bool(differences) and len(observed) == len(match.events)
            and all(d['graveOrderOnly'] for d in differences),
        recordedRandoms=len(match.randoms()), consumedRandoms=random.pos,
        originalFinalEvent=match.events[-1], emittedFinalEvent=observed[-1] if observed else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('records', type=Path, nargs='+')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sources = [Path(__file__), ROOT/'sim/replay.py', ROOT/'sim/evaluate.py', ROOT/'sim/evaluate_secured_resources.py']
    paths = [p.resolve() for p in args.records]
    source, inputs, engine = files_hash(sources), files_hash(paths), engine_hashes()
    rows = [audit(path) for path in paths]
    report = dict(revision='full-stream-difference-audit-v1', records=rows,
        engineSourceSha256=engine, auditSourceSha256=source, inputDataSha256=inputs,
        engineUnchanged=engine == engine_hashes(), auditUnchanged=source == files_hash(sources),
        inputsUnchanged=inputs == files_hash(paths),
        scope='Full native replay, unchanged strict comparator. Grave ordering is normalized ONLY in detached comparison copies to classify each difference. A grave-order-only record is still a strict failure. This observed continuation does not prove grave ordering irrelevant to arbitrary future random recovery or scripted choices.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('engineSourceSha256', 'auditSourceSha256', 'inputDataSha256')}))
    return int(any(r['errors'] or not r['allEventsEmitted'] for r in rows)
               or not all(report[k] for k in ('engineUnchanged', 'auditUnchanged', 'inputsUnchanged')))


if __name__ == '__main__':
    raise SystemExit(main())
