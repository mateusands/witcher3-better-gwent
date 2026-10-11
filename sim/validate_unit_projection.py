#!/usr/bin/env python3
"""Read-only probe: supported row projections versus actual recorded next-turn scores.

This adds no policy, RNG calls or rule changes. It does not replace strict replay.
"""
import hashlib
import json
from pathlib import Path

from gwentsim.data import load_match
from gwentsim.rng import ReplayRandom
from gwentsim.gwint.match import run_match
from gwentsim.gwint.card_manager import CardManager
from gwentsim.unit_evaluation import unit_alternatives

ROOT = Path(__file__).resolve().parents[1]


def validate(path):
    match = load_match(path)
    pending = None
    comparisons, unsupported, failures = [], 0, []
    skipped = 0
    expected = match.events
    human = any(e['k'] in ('H', 'P', 'C') for e in expected)
    event_index = 0
    def observe(event):
        nonlocal pending, unsupported, event_index, skipped
        index = event_index
        event_index += 1
        if event['k'] == ('H' if human else 'A') and event['tx'] is not None:
            if pending is not None:
                skipped += 1
                pending = None
            manager = CardManager.getInstance()
            tx, player = event['tx'], event['player']
            source = manager.getCardInstance(tx['source'][1])
            options = unit_alternatives(manager, source, player) if source.inList == 1 else ()
            selected = next((o for o in options if o.row == tx['slot']), None)
            if selected is not None:
                scores = list(manager.currentPlayerScores)
                scores[player] += selected.gain
                pending = dict(playEvent=index, source=tx['source'], player=player,
                               predicted=scores, gain=selected.gain)
            else:
                unsupported += 1
        if event['k'] == 'S' and pending is not None and event['tag'].startswith('t'):
            original = expected[index]
            actual = [p['score'] for p in original['players']]
            entry = dict(pending, snapshotEvent=index, observed=actual)
            comparisons.append(entry)
            if actual != pending['predicted']:
                failures.append(entry)
            pending = None
    run_match(match.templates.values(), match.decks, match.card_values,
              ReplayRandom(match.randoms()), double_ai=not human, scripted_events=expected if human else None,
              on_event=observe)
    return dict(record=path.name, sourceSha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                comparisons=comparisons, unsupportedPlays=unsupported,
                skippedWithoutIntermediateSnapshot=skipped, failures=failures)


if __name__ == '__main__':
    report = dict(records=[], errors=[])
    for path in sorted((ROOT/'game/records').glob('g[0-9][0-9][0-9].json')):
        try:
            report['records'].append(validate(path))
        except Exception as error:
            report['errors'].append(dict(record=path.name, error=str(error)))
    report['comparedPlays'] = sum(len(r['comparisons']) for r in report['records'])
    report['mismatches'] = sum(len(r['failures']) for r in report['records'])
    destination=ROOT/'game/evaluations/unit-projection-observed.json'
    destination.write_text(json.dumps(report, indent=2)+'\n')
    print({key:value for key,value in report.items() if key!='records'})
    raise SystemExit(bool(report['errors'] or report['mismatches']))
