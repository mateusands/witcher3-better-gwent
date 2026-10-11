#!/usr/bin/env python3
"""Three-arm original ablation: V7, projection, projection plus held-combo reserve."""
import argparse
import json
from pathlib import Path
from time import perf_counter
import evaluate_secured_resources as paired
from evaluate import engine_hashes, validation
from evaluate_npc_policies import setup
from mushroom_policy import mushroom_hook
from mushroom_reserve import mushroom_reserve_hook

ROOT = Path(__file__).resolve().parents[1]


def group(task):
    pair, seed, swap = task
    original = paired.refinement_hook
    rows = []
    try:
        for kind in ('native', 'direct'):
            variants = ('v7', 'projection', 'combo') if kind == 'native' else ('projection', 'combo')
            for variant in variants:
                paired.refinement_hook = mushroom_reserve_hook if variant == 'combo' else mushroom_hook
                for seat in (0, 1):
                    row = paired.run(pair, seed, swap, seat,
                                     'v7' if variant == 'v7' else 'candidate', kind)
                    row['variant'] = variant
                    if variant == 'combo':
                        for audit in row['refinements']:
                            audit['candidate']['revision'] = 'mushroom-reserve-v1'
                    rows.append(row)
        if len({r['initialDealSha256'] for r in rows}) != 1:
            raise RuntimeError('initial deals differ')
        return rows, None
    except (RuntimeError, ValueError) as exc:
        return [], dict(task=task, error=str(exc))
    finally:
        paired.refinement_hook = original


def comparison(rows, reference, candidate):
    normalized = [dict(r, variant='v7' if r['variant'] == reference else 'candidate')
                  for r in rows if r['variant'] in (reference, candidate)
                  and (r['kind'] == 'native' or r['variant'] == candidate)]
    return paired.summarize(normalized)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds', type=int, nargs='+', required=True)
    parser.add_argument('--pair-indices', type=int, nargs='+')
    parser.add_argument('--all-npcs', action='store_true')
    parser.add_argument('--jobs', type=int, default=1)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    paired.STATE.update(setup(args.all_npcs))
    indices = args.pair_indices if args.pair_indices is not None else list(range(len(paired.STATE['pairs'])))
    if args.jobs < 1 or not indices or len(set(indices)) != len(indices) or any(i < 0 or i >= len(paired.STATE['pairs']) for i in indices):
        parser.error('invalid jobs or pair indices')
    paths = [Path(__file__), ROOT/'sim/mushroom_reserve.py', ROOT/'sim/mushroom_policy.py',
             ROOT/'sim/mushroom_position.py', ROOT/'sim/evaluate_secured_resources.py',
             ROOT/'sim/evaluate_npc_policies.py', ROOT/'sim/evaluate_mulligan.py', ROOT/'sim/evaluate.py']
    inputs = [ROOT/'game/records/g113.json'] + sorted((ROOT/'game/vanilla/xml/content0/gameplay/items').glob('*.xml'))
    source, fixtures, engine = paired.files_hash(paths), paired.files_hash(inputs), engine_hashes()
    tasks = [(i, seed, swap) for i in indices for seed in args.seeds for swap in (False, True)]
    started = perf_counter()
    if args.jobs > 1:
        import multiprocessing
        with multiprocessing.get_context('fork').Pool(args.jobs) as pool:
            groups = pool.map(group, tasks)
    else:
        groups = list(map(group, tasks))
    rows = [r for subset, error in groups for r in subset]
    errors = [error for subset, error in groups if error]
    summary = {f'{c}-vs-{r}': comparison(rows, r, c)
               for r, c in [('v7', 'projection'), ('v7', 'combo'), ('projection', 'combo')]}
    report = dict(revision='mushroom-reserve-v1', profile='expert', seeds=args.seeds,
        pairPlan=[dict(pair=i, decks=[d.name for d in paired.STATE['pairs'][i]],
                       leaders=[d.leader for d in paired.STATE['pairs'][i]]) for i in indices],
        trials=rows, errors=errors, summary=summary, engineSourceSha256=engine,
        evaluationSourceSha256=source, inputDataSha256=fixtures,
        engineUnchanged=engine == engine_hashes(), evaluationUnchanged=source == paired.files_hash(paths),
        inputsUnchanged=fixtures == paired.files_hash(inputs), elapsedSeconds=perf_counter()-started,
        validation=validation(), scope='Native rules execution; three explicit native-opponent arms with identical initial deals. Direct trials face unchanged V7, including in the combo-vs-projection summary; they are NOT head-to-head combo-versus-projection. Own held transformation ceiling only. No death-summon, phase, initial-exchange, deck-definition or production changes. Correlated seeds/seats, no general-strength claim.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: report[k] for k in ('summary', 'errors', 'elapsedSeconds', 'engineUnchanged', 'evaluationUnchanged', 'inputsUnchanged')}))
    return int(bool(errors) or not all(report[k] for k in ('engineUnchanged', 'evaluationUnchanged', 'inputsUnchanged')))


if __name__ == '__main__':
    raise SystemExit(main())
