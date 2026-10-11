#!/usr/bin/env python3
"""Audit ordinary Scorch coverage on real native initial public/own snapshots."""
import argparse
import json
from pathlib import Path
from evaluate import engine_hashes
from evaluate_npc_policies import setup
from evaluate_secured_resources import files_hash
from gwentsim.gwint.match import run_match
from gwentsim.gwint.card_manager import CardManager
from gwentsim.position import Position
from gwentsim.sequence_search import Context
from gwentsim.opponent_belief import hypotheses
from gwentsim.rng import SeededRandom
from scorch_belief import scorch_hypotheses

ROOT = Path(__file__).resolve().parents[1]


class DealObserved(Exception):
    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds', type=int, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sources = [Path(__file__), ROOT/'sim/scorch_belief.py', ROOT/'sim/evaluate_npc_policies.py',
               ROOT/'sim/evaluate.py', ROOT/'sim/evaluate_secured_resources.py']
    fixtures = [ROOT/'game/records/g113.json'] + sorted((ROOT/'game/vanilla/xml/content0/gameplay/items').glob('*.xml'))
    source, inputs, engine = files_hash(sources), files_hash(fixtures), engine_hashes()
    data = setup(False); match = data['match']; rows = []
    for pair, decks in enumerate(data['pairs']):
        for seed in args.seeds:
            def observe(event):
                if event['k'] != 'S' or event['tag'] != 'deal':
                    return
                cm = CardManager.getInstance()
                for seat in (0, 1):
                    state = Position.from_manager(cm, seat)
                    ctx = Context(0, 0, 0, False, 10, decks[seat].faction,
                                  decks[1-seat].faction, state.leader_unmodeled(seat),
                                  state.leader_unmodeled(1-seat))
                    # Counts and faction only; no identities from the enemy hand.
                    original = hypotheses(state, ctx, 6)
                    candidate = scorch_hypotheses(state, ctx, 6)
                    def count(groups):
                        return sum(any(c.template == 2 for c in h.hand) for h in groups)
                    unchanged = state == Position.from_manager(cm, seat)
                    actual_types = state.catalog[2].types
                    preserved = all(c.types == actual_types for h in candidate for c in h.hand if c.template == 2)
                    rows.append(dict(pair=pair, seed=seed, seat=seat, faction=decks[seat].faction,
                        opponentFaction=decks[1-seat].faction, originalScorchHands=count(original),
                        candidateScorchHands=count(candidate), actualScorchTypes=actual_types,
                        metadataPreserved=preserved, inputSnapshotUnchanged=unchanged,
                        sampleCounts=[len(original), len(candidate)]))
                raise DealObserved()
            try:
                run_match(match.templates.values(), [d.for_player(i) for i, d in enumerate(decks)],
                          match.card_values, SeededRandom(seed), on_event=observe, coin_toss_choice=lambda: True)
            except DealObserved:
                pass
    summary = dict(snapshots=len(rows), hypothesisHandsPerArm=sum(r['sampleCounts'][0] for r in rows),
        originalScorchHands=sum(r['originalScorchHands'] for r in rows),
        candidateScorchHands=sum(r['candidateScorchHands'] for r in rows),
        snapshotsWithCandidateScorch=sum(r['candidateScorchHands'] > 0 for r in rows),
        allMetadataPreserved=all(r['metadataPreserved'] for r in rows),
        allSnapshotsUnchanged=all(r['inputSnapshotUnchanged'] for r in rows))
    report = dict(revision='scorch-pool-coverage-v1', rows=rows, summary=summary,
        engineSourceSha256=engine, diagnosticSourceSha256=source, inputDataSha256=inputs,
        engineUnchanged=engine == engine_hashes(), diagnosticUnchanged=source == files_hash(sources),
        inputsUnchanged=inputs == files_hash(fixtures),
        scope='Own/public initial snapshots from unchanged NPC pairs, six V7 scenarios per arm. Catalog-pool coverage only: these are NOT actual opponent hands or calibrated Scorch probabilities, and this is not a strength result. Initial deal aborted after read-only capture; no selected enemy-deck or hand identities inspected.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: report[k] for k in ('summary', 'engineUnchanged', 'diagnosticUnchanged', 'inputsUnchanged')}))
    return int(not all(report[k] for k in ('engineUnchanged', 'diagnosticUnchanged', 'inputsUnchanged')) or not summary['allMetadataPreserved'] or not summary['allSnapshotsUnchanged'] or summary['originalScorchHands'] != 0 or summary['candidateScorchHands'] == 0)


if __name__ == '__main__':
    raise SystemExit(main())
