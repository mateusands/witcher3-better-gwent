#!/usr/bin/env python3
"""Original paired V7 first-round future-resource allocation experiment on unchanged native NPC decks.

Both seats and deck orders, identical initial deals, native comparisons and direct
V7 opposition. No initial-exchange changes. Calls and actual action changes are
counted separately. Source and consumed fixture hashes are fixed before dispatch.
"""
import argparse,hashlib,json
from contextlib import contextmanager
from pathlib import Path
from time import perf_counter
from evaluate import engine_hashes,validation
from evaluate_npc_policies import setup
from first_round_budget import first_round_budget_hook as refinement_hook
from gwentsim.gwint.sequence_ai_controller import ResponseAIPlayerController
from gwentsim.gwint.match import run_match
from gwentsim.rng import SeededRandom
from gwentsim.response_search import secured

ROOT=Path(__file__).resolve().parents[1]
STATE={}


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def files_hash(paths):
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}




def run(pair,seed,swap,seat,variant,kind):
    a,b=STATE['pairs'][pair];decks=(b,a) if swap else (a,b);match=STATE['match']
    policies=tuple('response-v6' if side==seat or kind=='direct' else 'vanilla' for side in (0,1))
    audit=[];started=perf_counter()
    from contextlib import nullcontext
    with refinement_hook(seat,audit) if variant=='candidate' else nullcontext():
        recorder,flow=run_match(match.templates.values(),[d.for_player(i) for i,d in enumerate(decks)],
            match.card_values,SeededRandom(seed),seat_policies=policies,
            candidate_profile=3,coin_toss_choice=lambda:True)
    initial=next(e for e in recorder.events if e['k']=='S' and e['tag']=='deal')
    return dict(pair=pair,seed=seed,swapped=swap,seat=seat,variant=variant,kind=kind,
        decks=[d.name for d in decks],leaders=[d.leader for d in decks],faction=decks[seat].faction,
        score=.5 if flow.gameWinner not in (0,1) else float(flow.gameWinner==seat),winner=flow.gameWinner,
        initialDealSha256=digest(initial),eventSha256=digest(recorder.events),
        calls=len(audit),actionChanges=sum(e['changed'] for e in audit),refinements=audit,
        elapsedSeconds=perf_counter()-started,
        rounds=[dict(scores=[r.getPlayerScore(0),r.getPlayerScore(1)],winner=r.winningPlayer)
            for r in flow.cardManager.roundResults if r.played])


def group(task):
    pair,seed,swap=task
    try:
        rows=[run(pair,seed,swap,seat,variant,'native') for seat in (0,1) for variant in ('v7','candidate')]
        rows += [run(pair,seed,swap,seat,'candidate','direct') for seat in (0,1)]
        if len({r['initialDealSha256'] for r in rows})!=1:raise RuntimeError('initial deals differ')
        return rows,None
    except (RuntimeError,ValueError) as exc:return [],dict(task=task,error=str(exc))


def summarize(rows):
    def block(subset):
        return dict(games=len(subset),score=sum(r['score'] for r in subset),
            wins=sum(r['score']==1 for r in subset),draws=sum(r['score']==.5 for r in subset),
            losses=sum(r['score']==0 for r in subset),calls=sum(r['calls'] for r in subset),
            actionChanges=sum(r['actionChanges'] for r in subset))
    native=[r for r in rows if r['kind']=='native'];paired={}
    for r in native:paired.setdefault((r['pair'],r['seed'],r['swapped'],r['seat']),{})[r['variant']]=r
    changes=[g['candidate']['score']-g['v7']['score'] for g in paired.values()]
    return dict(versusNative={v:block([r for r in native if r['variant']==v]) for v in ('v7','candidate')},
        paired=dict(gains=sum(x>0 for x in changes),regressions=sum(x<0 for x in changes),
            equal=sum(x==0 for x in changes),netScore=sum(changes)),
        direct=block([r for r in rows if r['kind']=='direct']),
        byFaction={str(f):{v:block([r for r in native if r['variant']==v and r['faction']==f]) for v in ('v7','candidate')}
            for f in sorted({r['faction'] for r in rows})})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--all-npcs',action='store_true')
    parser.add_argument('--pair-indices',type=int,nargs='+')
    parser.add_argument('--seeds',type=int,nargs='+',required=True)
    parser.add_argument('--jobs',type=int,default=2)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    STATE.update(setup(args.all_npcs))
    indices=args.pair_indices if args.pair_indices is not None else list(range(len(STATE['pairs'])))
    if args.jobs<1 or not indices or len(set(indices))!=len(indices) or any(i<0 or i>=len(STATE['pairs']) for i in indices):parser.error('invalid jobs or pair indices')
    source_paths=[Path(__file__),ROOT/'sim/first_round_budget.py',ROOT/'sim/evaluate_npc_policies.py',ROOT/'sim/evaluate_mulligan.py',ROOT/'sim/evaluate.py']
    # Only g113 and native XML initialize these fixtures. New recordings arriving
    # during my own play are not inputs to this prospective evaluation.
    input_paths=[ROOT/'game/records/g113.json']+sorted((ROOT/'game/vanilla/xml/content0/gameplay/items').glob('*.xml'))
    engine=engine_hashes();source=files_hash(source_paths);inputs=files_hash(input_paths)
    tasks=[(i,seed,swap) for i in indices for seed in args.seeds for swap in (False,True)]
    started=perf_counter()
    if args.jobs>1:
        import multiprocessing
        with multiprocessing.get_context('fork').Pool(args.jobs) as pool:groups=pool.map(group,tasks)
    else:groups=list(map(group,tasks))
    rows=[r for subset,error in groups for r in subset];errors=[e for subset,e in groups if e]
    report=dict(revision='first-round-budget-v1',profile='expert',seeds=args.seeds,
        pairPlan=[dict(pair=i,decks=[d.name for d in STATE['pairs'][i]],leaders=[d.leader for d in STATE['pairs'][i]]) for i in indices],
        trials=rows,errors=errors,summary=summarize(rows),engineSourceSha256=engine,
        evaluationSourceSha256=source,inputDataSha256=inputs,
        engineUnchanged=engine==engine_hashes(),evaluationUnchanged=source==files_hash(source_paths),
        inputsUnchanged=inputs==files_hash(input_paths),elapsedSeconds=perf_counter()-started,validation=validation(),
        scope='Simulator-only audited runtime method hook; unchanged real NPC decks/leaders and initial exchanges. Correlated seats/deck families. Only the losing-first-round future branch divides the acting resource estimate across two required wins. Winning branches, actual first-round tie endpoints, card/deck definitions, search budgets, priors and initial exchanges stay reference. Conservative allocation heuristic, uncalibrated opponent allocation and future draws; no optimality or production-runtime claim.')
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(simulations=len(rows),errors=errors,summary=report['summary'],elapsedSeconds=report['elapsedSeconds'],engineUnchanged=report['engineUnchanged'],evaluationUnchanged=report['evaluationUnchanged'],inputsUnchanged=report['inputsUnchanged'])))
    return int(bool(errors) or not all(report[k] for k in ('engineUnchanged','evaluationUnchanged','inputsUnchanged')))


if __name__=='__main__':raise SystemExit(main())
