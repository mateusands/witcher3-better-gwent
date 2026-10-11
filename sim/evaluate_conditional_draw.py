#!/usr/bin/env python3
"""Original controlled winner-draw ablation, preserving V7 phase heuristics."""
import argparse,json
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from time import perf_counter
import evaluate_secured_resources as paired
from evaluate import engine_hashes,validation
from evaluate_npc_policies import setup
from gwentsim import sequence_search,response_search
from gwentsim.gwint.sequence_ai_controller import ResponseAIPlayerController
from conditional_draw_value import conditional_draw_utility

ROOT=Path(__file__).resolve().parents[1]


@contextmanager
def conditional_draw_hook(seat,audit):
    original=ResponseAIPlayerController.search
    def search(controller,position,context):
        reference=original(controller,position,context)
        if controller.playerID!=seat or context.round_index!=1 or (context.own_losses,context.opponent_losses) not in ((0,1),(1,0)):return reference
        seq=response_search.utility;own=sequence_search.utility
        def selected(state,ctx,*args,**kwargs):
            return conditional_draw_utility(state,ctx,*args,**kwargs) if state.player==seat else own(state,ctx,*args,**kwargs)
        started=perf_counter()
        try:
            response_search.utility=selected;sequence_search.utility=selected
            candidate=replace(original(controller,position,context),revision='conditional-draw-v1')
        finally:response_search.utility=seq;sequence_search.utility=own
        audit.append(dict(changed=candidate.action!=reference.action,round=context.round_index,
            scores=position.scores(),reference=reference.audit(),candidate=candidate.audit(),
            refinementSeconds=perf_counter()-started))
        return candidate
    ResponseAIPlayerController.search=search
    try:yield
    finally:ResponseAIPlayerController.search=original


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds',type=int,nargs='+',required=True)
    parser.add_argument('--all-npcs',action='store_true')
    parser.add_argument('--pair-indices',type=int,nargs='+')
    parser.add_argument('--jobs',type=int,default=1)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    paired.STATE.update(setup(args.all_npcs))
    indices=args.pair_indices if args.pair_indices is not None else list(range(len(paired.STATE['pairs'])))
    if args.jobs<1 or not indices or len(set(indices))!=len(indices) or any(i<0 or i>=len(paired.STATE['pairs']) for i in indices):parser.error('invalid jobs or pair indices')
    sources=[Path(__file__),ROOT/'sim/conditional_draw_value.py',ROOT/'sim/evaluate_secured_resources.py',ROOT/'sim/evaluate_npc_policies.py',ROOT/'sim/evaluate_mulligan.py',ROOT/'sim/evaluate.py']
    inputs=[ROOT/'game/records/g113.json']+sorted((ROOT/'game/vanilla/xml/content0/gameplay/items').glob('*.xml'))
    source=paired.files_hash(sources);fixtures=paired.files_hash(inputs);engine=engine_hashes()
    tasks=[(i,seed,swap) for i in indices for seed in args.seeds for swap in (False,True)]
    original_hook=paired.refinement_hook;paired.refinement_hook=conditional_draw_hook;started=perf_counter()
    try:
        if args.jobs>1:
            import multiprocessing
            with multiprocessing.get_context('fork').Pool(args.jobs) as pool:groups=pool.map(paired.group,tasks)
        else:groups=list(map(paired.group,tasks))
    finally:paired.refinement_hook=original_hook
    rows=[r for subset,error in groups for r in subset];errors=[e for subset,e in groups if e]
    report=dict(revision='conditional-draw-v1',profile='expert',seeds=args.seeds,
        pairPlan=[dict(pair=i,decks=[d.name for d in paired.STATE['pairs'][i]],leaders=[d.leader for d in paired.STATE['pairs'][i]]) for i in indices],
        trials=rows,errors=errors,summary=paired.summarize(rows),engineSourceSha256=engine,
        evaluationSourceSha256=source,inputDataSha256=fixtures,engineUnchanged=engine==engine_hashes(),
        evaluationUnchanged=source==paired.files_hash(sources),inputsUnchanged=fixtures==paired.files_hash(inputs),
        elapsedSeconds=perf_counter()-started,validation=validation(),
        scope='Explicit simulator-only search/utility hooks on candidate seat. Unchanged NPC decks/leaders, initial exchanges and V7 elsewhere. Correlated pairs; unchanged V7 phase allowance and provisional opponent draw estimate. Isolates winner-draw attribution, not full phase retuning. No production-strength claim.')
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(simulations=len(rows),errors=errors,summary=report['summary'],elapsedSeconds=report['elapsedSeconds'],engineUnchanged=report['engineUnchanged'],evaluationUnchanged=report['evaluationUnchanged'],inputsUnchanged=report['inputsUnchanged'])))
    return int(bool(errors) or not all(report[k] for k in ('engineUnchanged','evaluationUnchanged','inputsUnchanged')))


if __name__=='__main__':raise SystemExit(main())
