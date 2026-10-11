#!/usr/bin/env python3
"""Four-role diagnostic ablation and opposition with actual expanded own abilities."""
import argparse
import json
from pathlib import Path
from time import perf_counter
import evaluate_secured_resources as paired
from evaluate import engine_hashes, validation
from evaluate_npc_policies import setup
from mushroom_role import mushroom_roles_hook

ROOT = Path(__file__).resolve().parents[1]


def group(task):
    pair, seed, swap = task; rows = []; original = paired.refinement_hook
    try:
        for kind in ('native', 'direct', 'mixed'):
            variants = ('v7', 'own', 'opponent', 'both') if kind == 'native' else ('own', 'both') if kind == 'direct' else ('own',)
            for variant in variants:
                def hook(seat, audit):
                    roles = {seat: variant}
                    if kind == 'mixed':
                        roles[1-seat] = 'both'
                    return mushroom_roles_hook(roles, {seat: audit})
                paired.refinement_hook = hook
                for seat in (0, 1):
                    row = paired.run(pair, seed, swap, seat, 'v7' if variant == 'v7' else 'candidate',
                                     'direct' if kind == 'mixed' else kind)
                    row.update(variant=variant, kind=kind, peerRole='both' if kind == 'mixed' else 'v7' if kind == 'direct' else 'vanilla')
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
        and (r['kind'] == 'native' or r['kind'] == 'direct' and r['variant'] == candidate)]
    return paired.summarize(normalized)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds', type=int, nargs='+', required=True)
    parser.add_argument('--pair-indices', type=int, nargs='+')
    parser.add_argument('--all-npcs', action='store_true')
    parser.add_argument('--jobs', type=int, default=1)
    parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    paired.STATE.update(setup(args.all_npcs))
    indices = args.pair_indices if args.pair_indices is not None else list(range(len(paired.STATE['pairs'])))
    if args.jobs < 1 or not indices or len(set(indices)) != len(indices) or any(i < 0 or i >= len(paired.STATE['pairs']) for i in indices):
        parser.error('invalid jobs or pair indices')
    sources = [Path(__file__), ROOT/'sim/mushroom_role.py', ROOT/'sim/mushroom_position.py',
        ROOT/'sim/mushroom_policy.py', ROOT/'sim/evaluate_secured_resources.py',
        ROOT/'sim/evaluate_npc_policies.py', ROOT/'sim/evaluate_mulligan.py', ROOT/'sim/evaluate.py']
    fixtures = [ROOT/'game/records/g113.json'] + sorted((ROOT/'game/vanilla/xml/content0/gameplay/items').glob('*.xml'))
    source, inputs, engine = paired.files_hash(sources), paired.files_hash(fixtures), engine_hashes()
    tasks = [(i, seed, swap) for i in indices for seed in args.seeds for swap in (False, True)]
    started = perf_counter()
    if args.jobs > 1:
        import multiprocessing
        with multiprocessing.get_context('fork').Pool(args.jobs) as pool:
            groups = pool.map(group, tasks)
    else:
        groups = list(map(group, tasks))
    rows = [r for subset, error in groups for r in subset]; errors = [error for subset, error in groups if error]
    summary = {f'{c}-vs-{r}': comparison(rows, r, c)
        for r, c in [('v7', 'own'), ('v7', 'opponent'), ('v7', 'both'), ('both', 'own')]}
    mixed = [r for r in rows if r['kind'] == 'mixed']
    summary['own-vs-actual-both-opponent'] = dict(games=len(mixed), score=sum(r['score'] for r in mixed),
        wins=sum(r['score'] == 1 for r in mixed), draws=sum(r['score'] == .5 for r in mixed), losses=sum(r['score'] == 0 for r in mixed))
    report = dict(revision='mushroom-role-ablation-v1', profile='expert', seeds=args.seeds,
        pairPlan=[dict(pair=i, decks=[d.name for d in paired.STATE['pairs'][i]], leaders=[d.leader for d in paired.STATE['pairs'][i]]) for i in indices],
        trials=rows, errors=errors, summary=summary, engineSourceSha256=engine,
        evaluationSourceSha256=source, inputDataSha256=inputs, engineUnchanged=engine == engine_hashes(),
        evaluationUnchanged=source == paired.files_hash(sources), inputsUnchanged=inputs == paired.files_hash(fixtures),
        elapsedSeconds=perf_counter()-started, validation=validation(),
        scope='Four native-opponent arms: V7, own-action coverage only, hypothetical-opponent coverage only, both. Own-only/opponent-only are causal diagnostic ablations with explicit unsupported effects, NOT claims that the other side cannot use Mushroom or production recommendations. Direct arms face unchanged V7. Additional mixed matches run own-only against an ACTUAL both-role controller with expanded legal own abilities. Native execution, NPC collections/leaders/deals unchanged. No reserve, prior, search-budget or initial-exchange changes. Correlated seats/decks; no general-strength claim.')
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: report[k] for k in ('summary', 'errors', 'elapsedSeconds', 'engineUnchanged', 'evaluationUnchanged', 'inputsUnchanged')}))
    return int(bool(errors) or not all(report[k] for k in ('engineUnchanged', 'evaluationUnchanged', 'inputsUnchanged')))


if __name__ == '__main__':
    raise SystemExit(main())
