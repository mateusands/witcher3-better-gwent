#!/usr/bin/env python3
"""Original V7 Mushroom projection ablation on unchanged real NPC collections."""
import argparse,json
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from time import perf_counter
import evaluate_secured_resources as paired
from evaluate import engine_hashes,validation
from evaluate_npc_policies import setup
from gwentsim.gwint.sequence_ai_controller import ResponseAIPlayerController
from mushroom_policy import mushroom_hook

ROOT=Path(__file__).resolve().parents[1]
CHECKPOINT_DIR=None
PLAN_SIGNATURE=None


def checkpoint_group(task):
    if CHECKPOINT_DIR is None:return paired.group(task)
    pair,seed,swap=task
    path=CHECKPOINT_DIR/f'pair-{pair}-seed-{seed}-swap-{int(swap)}.json'
    if path.exists():
        data=json.loads(path.read_text())
        if data.get('planSignature')!=PLAN_SIGNATURE or data.get('task')!=list(task):
            raise ValueError(f'incompatible checkpoint: {path}')
        rows,error=data['rows'],data['error']
        if error is None and (len(rows)!=6 or len({r['initialDealSha256'] for r in rows})!=1):
            raise ValueError(f'incomplete checkpoint: {path}')
        return rows,error
    rows,error=paired.group(task)
    data=dict(planSignature=PLAN_SIGNATURE,task=list(task),rows=rows,error=error)
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data)+'\n')
    temporary.replace(path)
    return rows,error




def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds',type=int,nargs='+',required=True)
    parser.add_argument('--all-npcs',action='store_true')
    parser.add_argument('--pair-indices',type=int,nargs='+')
    parser.add_argument('--jobs',type=int,default=1)
    parser.add_argument('--checkpoint-dir',type=Path,help='atomic completed-group checkpoints; matching source/input signature required')
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    paired.STATE.update(setup(args.all_npcs))
    indices=args.pair_indices if args.pair_indices is not None else list(range(len(paired.STATE['pairs'])))
    if args.jobs<1 or not indices or len(set(indices))!=len(indices) or any(i<0 or i>=len(paired.STATE['pairs']) for i in indices):parser.error('invalid jobs or pair indices')
    sources=[Path(__file__),ROOT/'sim/mushroom_policy.py',ROOT/'sim/mushroom_position.py',ROOT/'sim/evaluate_secured_resources.py',ROOT/'sim/evaluate_npc_policies.py',ROOT/'sim/evaluate_mulligan.py',ROOT/'sim/evaluate.py']
    inputs=[ROOT/'game/records/g113.json']+sorted((ROOT/'game/vanilla/xml/content0/gameplay/items').glob('*.xml'))
    source=paired.files_hash(sources);fixtures=paired.files_hash(inputs);engine=engine_hashes()
    tasks=[(i,seed,swap) for i in indices for seed in args.seeds for swap in (False,True)]
    global CHECKPOINT_DIR,PLAN_SIGNATURE
    CHECKPOINT_DIR=args.checkpoint_dir
    PLAN_SIGNATURE=paired.digest(dict(source=source,inputs=fixtures,engine=engine,
        seeds=args.seeds,indices=indices,profile='expert'))
    if CHECKPOINT_DIR is not None:CHECKPOINT_DIR.mkdir(parents=True,exist_ok=True)
    original_hook=paired.refinement_hook;paired.refinement_hook=mushroom_hook;started=perf_counter()
    try:
        if args.jobs>1:
            import multiprocessing
            with multiprocessing.get_context('fork').Pool(args.jobs) as pool:groups=pool.map(checkpoint_group,tasks)
        else:groups=list(map(checkpoint_group,tasks))
    finally:paired.refinement_hook=original_hook
    rows=[r for subset,error in groups for r in subset];errors=[e for subset,e in groups if e]
    report=dict(revision='mushroom-projection-v1',profile='expert',seeds=args.seeds,checkpointPlanSignature=PLAN_SIGNATURE,checkpointDirectory=str(CHECKPOINT_DIR) if CHECKPOINT_DIR else None,
        pairPlan=[dict(pair=i,decks=[d.name for d in paired.STATE['pairs'][i]],leaders=[d.leader for d in paired.STATE['pairs'][i]]) for i in indices],
        trials=rows,errors=errors,summary=paired.summarize(rows),engineSourceSha256=engine,
        evaluationSourceSha256=source,inputDataSha256=fixtures,engineUnchanged=engine==engine_hashes(),
        evaluationUnchanged=source==paired.files_hash(sources),inputsUnchanged=fixtures==paired.files_hash(inputs),
        elapsedSeconds=perf_counter()-started,validation=validation(),
        scope='Explicit simulator-only candidate projection/controller hook. Native FX execution, real unchanged NPC decks/leaders/deals. V7 future reserve, budgets and belief priors retained. Same-snapshot reference search is distinguished from actual native fallback. Correlated pairs; no production-strength claim.')
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(simulations=len(rows),errors=errors,summary=report['summary'],elapsedSeconds=report['elapsedSeconds'],engineUnchanged=report['engineUnchanged'],evaluationUnchanged=report['evaluationUnchanged'],inputsUnchanged=report['inputsUnchanged'])))
    return int(bool(errors) or not all(report[k] for k in ('engineUnchanged','evaluationUnchanged','inputsUnchanged')))


if __name__=='__main__':raise SystemExit(main())
