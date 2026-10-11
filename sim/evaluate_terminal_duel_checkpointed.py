#!/usr/bin/env python3
"""Fresh paired terminal-duel evaluation with atomic six-trial checkpoints.

Both arms use Mushroom-both modeling, so this isolates the endgame refinement. Reuse the
existing tested checkpoint mechanism; its module globals are local to this process.
"""
import argparse
import json
from pathlib import Path
from time import perf_counter
import evaluate_terminal_duel as paired
import evaluate_mushroom_policy as checkpoints
from evaluate import engine_hashes, validation
from evaluate_npc_policies import setup

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--all-npcs', action='store_true')
    parser.add_argument('--pair-indices', type=int, nargs='+')
    parser.add_argument('--seeds', type=int, nargs='+', required=True)
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--checkpoint-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    paired.STATE.update(setup(args.all_npcs))
    indices = args.pair_indices if args.pair_indices is not None else list(range(len(paired.STATE['pairs'])))
    if args.jobs < 1 or not indices or len(set(indices)) != len(indices) or any(
            i < 0 or i >= len(paired.STATE['pairs']) for i in indices):
        parser.error('invalid jobs or pair indices')
    paths = [Path(__file__)] + [ROOT / ('sim/' + name) for name in (
        'evaluate_terminal_duel.py', 'evaluate_mushroom_policy.py',
        'terminal_duel_policy.py', 'terminal_duel.py', 'mushroom_role.py',
        'mushroom_policy.py', 'mushroom_position.py', 'evaluate_npc_policies.py',
        'evaluate_mulligan.py', 'evaluate.py')]
    input_paths = [ROOT / 'game/records/g113.json'] + sorted(
        (ROOT / 'game/vanilla/xml/content0/gameplay/items').glob('*.xml'))
    source, inputs, engine = paired.files_hash(paths), paired.files_hash(input_paths), engine_hashes()
    checkpoints.paired = paired
    checkpoints.CHECKPOINT_DIR = args.checkpoint_dir
    checkpoints.PLAN_SIGNATURE = paired.digest(dict(source=source, inputs=inputs,
        engine=engine, seeds=args.seeds, indices=indices, profile='expert',
        reference='mushroom-both', candidate='terminal-duel-v1'))
    args.checkpoint_dir.mkdir(parents=True, exist_ok=True)
    tasks = [(i, seed, swap) for i in indices for seed in args.seeds for swap in (False, True)]
    started = perf_counter()
    if args.jobs > 1:
        import multiprocessing
        with multiprocessing.get_context('fork').Pool(args.jobs) as pool:
            groups = pool.map(checkpoints.checkpoint_group, tasks)
    else:
        groups = list(map(checkpoints.checkpoint_group, tasks))
    rows = [r for subset, error in groups for r in subset]
    errors = [e for subset, e in groups if e]
    report = dict(revision='terminal-duel-v1', reference='mushroom-both',
        profile='expert', seeds=args.seeds, checkpointPlanSignature=checkpoints.PLAN_SIGNATURE,
        checkpointDirectory=str(args.checkpoint_dir),
        pairPlan=[dict(pair=i, decks=[d.name for d in paired.STATE['pairs'][i]],
            leaders=[d.leader for d in paired.STATE['pairs'][i]]) for i in indices],
        trials=rows, errors=errors, summary=paired.summarize(rows),
        engineSourceSha256=engine, evaluationSourceSha256=source, inputDataSha256=inputs,
        engineUnchanged=engine == engine_hashes(),
        evaluationUnchanged=source == paired.files_hash(paths),
        inputsUnchanged=inputs == paired.files_hash(input_paths),
        elapsedSeconds=perf_counter() - started, validation=validation(),
        scope='Simulator-only Expert terminal minimax over unchanged public hypotheses; same Mushroom-both reference,native decks/leaders/deals. At most six held cards and8192 extra nodes across scenarios. All scenarios must complete and improve reference action strictly. Known cards remain hypothetical,not live hidden information. No general-strength or production claim.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('summary', 'errors', 'elapsedSeconds',
        'engineUnchanged', 'evaluationUnchanged', 'inputsUnchanged')}))
    return int(bool(errors) or not all(report[k] for k in (
        'engineUnchanged', 'evaluationUnchanged', 'inputsUnchanged')))


if __name__ == '__main__':
    raise SystemExit(main())
