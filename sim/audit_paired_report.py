#!/usr/bin/env python3
"""Independently audit completed six-trial native/direct comparison reports.

Checks coverage, unchanged real NPC metadata, same deals and score arithmetic.
This is experiment-integrity evidence, not proof of optimal decisions or strength.
Faction names come from the simulator constants rather than hand-written labels.
"""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from gwentsim import constants as C
from evaluate_npc_policies import setup

ROOT = Path(__file__).resolve().parents[1]
FACTIONS = {
    C.FactionId_No_Mans_Land: 'Monsters',
    C.FactionId_Nilfgaard: 'Nilfgaard',
    C.FactionId_Northern_Kingdom: 'Northern Kingdoms',
    C.FactionId_Scoiatael: 'Scoiatael',
    C.FactionId_Skellige: 'Skellige',
}


def audit(report, all_npcs=False):
    assert not report['errors'], 'evaluation errors'
    for gate in ('engineUnchanged', 'evaluationUnchanged', 'inputsUnchanged'):
        assert report[gate], f'failed gate: {gate}'
    for field in ('engineSourceSha256', 'evaluationSourceSha256', 'inputDataSha256'):
        for name, digest in report[field].items():
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, f'changed source/input: {name}'
    variants = set(report['summary']['versusNative'])
    assert 'candidate' in variants and len(variants) == 2, 'not a two-arm comparison'
    reference = next(v for v in variants if v != 'candidate')
    native = setup(all_npcs)['pairs']
    plan = {entry['pair']: entry for entry in report['pairPlan']}
    assert len(plan) == len(report['pairPlan']), 'duplicate plan pair'
    for pair, entry in plan.items():
        expected = native[pair]
        assert entry['decks'] == [d.name for d in expected], 'changed native collection'
        assert entry['leaders'] == [d.leader for d in expected], 'changed native leader'
    expected_keys = {(p, seed, swap, seat, kind, variant)
        for p in plan for seed in report['seeds'] for swap in (False, True)
        for seat in (0, 1) for kind, variant in (
            ('native', reference), ('native', 'candidate'), ('direct', 'candidate'))}
    observed = {}
    groups = defaultdict(list)
    scores = defaultdict(list)
    paired = defaultdict(dict)
    factions = defaultdict(lambda: defaultdict(list))
    for row in report['trials']:
        key = (row['pair'], row['seed'], row['swapped'], row['seat'], row['kind'], row['variant'])
        assert key not in observed, f'duplicate trial: {key}'
        assert key in expected_keys, f'unplanned trial: {key}'
        observed[key] = row
        pair = native[row['pair']]
        decks = tuple(reversed(pair)) if row['swapped'] else pair
        assert row['decks'] == [d.name for d in decks], 'wrong deck order'
        assert row['leaders'] == [d.leader for d in decks], 'wrong leader order'
        assert row['faction'] == decks[row['seat']].faction, 'wrong faction'
        assert len(row['rounds']) in (2, 3), 'invalid number of played rounds'
        losses = [0, 0]
        for result in row['rounds']:
            assert max(losses) < 2, 'extra round after match ended'
            left, right = result['scores']
            if left != right:
                winner = 0 if left > right else 1
            elif decks[0].faction != decks[1].faction and C.FactionId_Nilfgaard in (decks[0].faction, decks[1].faction):
                winner = 0 if decks[0].faction == C.FactionId_Nilfgaard else 1
            else:
                winner = -1
            assert result['winner'] == winner, 'round score/tie winner mismatch'
            for side in (0, 1):
                losses[side] += winner != side
        assert max(losses) >= 2, 'unfinished match'
        final_winner = -1 if min(losses) >= 2 else (0 if losses[1] >= 2 else 1)
        assert row['winner'] == final_winner, 'round/match winner mismatch'
        score = .5 if row['winner'] not in (0, 1) else float(row['winner'] == row['seat'])
        assert row['score'] == score, 'winner/score mismatch'
        groups[key[:3]].append(row['initialDealSha256'])
        scores[row['kind'], row['variant']].append(score)
        if row['kind'] == 'native':
            paired[key[:4]][row['variant']] = score
            factions[row['faction']][row['variant']].append(score)
    assert set(observed) == expected_keys, 'missing trials'
    assert all(len(values) == 6 and len(set(values)) == 1 for values in groups.values()), 'different initial deals'
    for (kind, variant), values in scores.items():
        block = report['summary']['direct'] if kind == 'direct' else report['summary']['versusNative'][variant]
        assert block['games'] == len(values) and block['score'] == sum(values), 'summary arithmetic mismatch'
        assert (block['wins'], block['draws'], block['losses']) == (
            values.count(1), values.count(.5), values.count(0)), 'outcome counts mismatch'
    deltas = [values['candidate'] - values[reference] for values in paired.values()]
    outcome = dict(gains=sum(v > 0 for v in deltas), regressions=sum(v < 0 for v in deltas),
        equal=sum(v == 0 for v in deltas), netScore=sum(deltas))
    assert outcome == report['summary']['paired'], 'paired arithmetic mismatch'
    for faction, arms in factions.items():
        for variant, values in arms.items():
            block = report['summary']['byFaction'][str(faction)][variant]
            assert block['games'] == len(values) and block['score'] == sum(values), 'faction summary mismatch'
    return dict(integrityVerified=True, trials=len(observed), reference=reference,
        paired=outcome, byFaction={FACTIONS[f]: {v: dict(games=len(values), score=sum(values))
            for v, values in arms.items()} for f, arms in sorted(factions.items())},
        limitation='Coverage/data/score integrity only; correlated families and uncalibrated heuristics remain. No optimality, robustness or production-runtime guarantee.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--all-npcs', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(json.loads(args.report.read_text()), args.all_npcs)
    result['reportSha256'] = hashlib.sha256(args.report.read_bytes()).hexdigest()
    result['auditorSha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
