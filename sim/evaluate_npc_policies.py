#!/usr/bin/env python3
"""Paired policy comparison restricted to unchanged native NPC decks and leaders.

Uses the existing comparator and a fixed native-only pair selection. Five-faction
smoke pairs match the mulligan study; --all-npcs covers every native NPC collection
once against a deterministic rotation of opponent factions. No card/deck edits.
"""
import argparse,hashlib,json
from pathlib import Path
from time import perf_counter
from evaluate import engine_hashes,validation
from compare_policies import group,summarize,input_hashes,evaluation_hashes
from evaluate_mulligan import setup as smoke_setup
from gwentsim.native_decks import NativeDecks
from gwentsim.deck_pool import build_pool,FACTIONS
import evaluate_pool

ROOT=Path(__file__).resolve().parents[1]
PLAN={}


def setup(all_npcs=False):
    if not PLAN:
        state=smoke_setup();match=state['match'];pairs=state['pairs']
        if all_npcs:
            native=NativeDecks(ROOT/'game/vanilla/xml/content0/gameplay/items',match.templates)
            decks=[d for d in build_pool(native,match.templates) if d.native_leader]
            by_faction={f:[d for d in decks if d.faction==f] for f in FACTIONS}
            pairs=[(d,by_faction[FACTIONS[i%len(FACTIONS)]][i%len(by_faction[FACTIONS[i%len(FACTIONS)]])])
                for i,d in enumerate(decks)]
        evaluate_pool._state.update(match=match,pairs=pairs)
        PLAN.update(match=match,pairs=pairs)
    return PLAN


def task_group(task):
    rows,error=group(task)
    for row in rows:row['source']='native-npc'
    if error:error['source']='native-npc'
    return rows,error


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds',nargs='+',type=int,required=True)
    parser.add_argument('--all-npcs',action='store_true')
    parser.add_argument('--candidate',choices=['resource-v9','response-pass-v8'],default='resource-v9')
    parser.add_argument('--profile',choices=['hard','expert'],default='expert')
    parser.add_argument('--jobs',type=int,default=11)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    data=setup(args.all_npcs);hashes=engine_hashes();inputs=input_hashes();evaluation=evaluation_hashes()
    extra={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (Path(__file__),ROOT/'sim/evaluate_mulligan.py')}
    pair_plan=[dict(pair=i,decks=[a.name,b.name],leaders=[a.leader,b.leader],factions=[a.faction,b.faction])
        for i,(a,b) in enumerate(data['pairs'])]
    tasks=[('pool',i,seed,swap,3 if args.profile=='expert' else 2,'all',args.candidate)
        for i in range(len(pair_plan)) for seed in args.seeds for swap in (False,True)]
    started=perf_counter()
    if args.jobs>1:
        import multiprocessing
        with multiprocessing.get_context('fork').Pool(args.jobs) as pool:groups=pool.map(task_group,tasks,chunksize=1)
    else:groups=list(map(task_group,tasks))
    trials=[r for rows,error in groups for r in rows];errors=[e for rows,e in groups if e]
    report=dict(status='exploratory',profile=args.profile,seeds=args.seeds,comparisons='all',candidate=args.candidate,
        trials=trials,errors=errors,summary=summarize(trials,args.candidate),pairPlan=pair_plan,
        validation=validation(),engineSourceSha256=hashes,inputDataSha256=inputs,evaluationSourceSha256=evaluation,
        extraEvaluationSha256=extra,sourceUnchangedDuringRun=engine_hashes()==hashes,
        inputDataUnchangedDuringRun=input_hashes()==inputs,evaluationSourceUnchangedDuringRun=evaluation_hashes()==evaluation,
        extraEvaluationUnchanged=extra=={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in extra},
        elapsedSeconds=perf_counter()-started,
        scope='Unchanged native NPC collections and actual leaders; fresh seeds needed after tuning, no production acceptance.')
    if not all(report[k] for k in ('sourceUnchangedDuringRun','inputDataUnchangedDuringRun','evaluationSourceUnchangedDuringRun','extraEvaluationUnchanged')):
        report['status']='invalidated-source-changed-during-run'
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(simulations=len(trials),errors=errors,direct=report['summary']['direct'],native=report['summary']['versusNative'],
        sourceUnchanged=report['sourceUnchangedDuringRun'],elapsedSeconds=report['elapsedSeconds'])))
    return int(bool(errors) or report['status']!='exploratory')


if __name__=='__main__':raise SystemExit(main())
