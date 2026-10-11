#!/usr/bin/env python3
"""Original factorial test of V7, structural exchanges and the plain-hero guard.

Uses unchanged native NPC decks/leaders, identical initial deals, both seats and
deck orders. Audited simulator-only runtime hooks keep frozen engine files intact.
Tests hero-only and combined policies directly against V7 as well as native AI.
"""
import argparse,hashlib,json
from contextlib import contextmanager,ExitStack
from pathlib import Path
from time import perf_counter
import evaluate_mulligan as exchange
from evaluate_npc_policies import setup
from evaluate import engine_hashes,validation
from compare_policies import input_hashes
from hero_pass_refinement import refine_hero_pass
from secured_round_refinement import refine_secured_round
from structural_mulligan import choose_structural_mulligan
from gwentsim.gwint.match import run_match
from gwentsim.gwint.sequence_ai_controller import ResponseAIPlayerController
from gwentsim.rng import SeededRandom

ROOT=Path(__file__).resolve().parents[1]
STATE={}


@contextmanager
def candidate_hooks(seat,variant,seed,decisions):
    original_search=ResponseAIPlayerController.search
    original_selector=exchange.choose_mulligan
    def search(controller,position,context):
        result=original_search(controller,position,context)
        refine=refine_secured_round if STATE.get('guard')=='secured' else refine_hero_pass
        return refine(position,context,result) if controller.playerID==seat else result
    try:
        with ExitStack() as stack:
            if variant in ('hero','combined'):ResponseAIPlayerController.search=search
            if variant in ('structural','combined'):
                exchange.choose_mulligan=choose_structural_mulligan
                stack.enter_context(exchange.exchange_hook(seat,'evaluated',seed,decisions))
            yield
    finally:
        ResponseAIPlayerController.search=original_search
        exchange.choose_mulligan=original_selector


def run(pair,seed,swap,seat,variant,kind):
    match=STATE['match'];a,b=STATE['pairs'][pair];seats=(b,a) if swap else (a,b)
    policies=tuple('response-v6' if s==seat or kind=='direct' else 'vanilla' for s in (0,1))
    exchanges=[]
    with candidate_hooks(seat,variant,seed,exchanges):
        recorder,flow=run_match(match.templates.values(),[d.for_player(i) for i,d in enumerate(seats)],
            match.card_values,SeededRandom(seed),seat_policies=policies,candidate_profile=3,
            coin_toss_choice=lambda:True)
    audits=flow.playerControllers[seat].policy_decisions
    initial=next(e for e in recorder.events if e['k']=='S' and e['tag']=='deal')
    return dict(pair=pair,seed=seed,swapped=swap,seat=seat,variant=variant,kind=kind,
        decks=[d.name for d in seats],leaders=[d.leader for d in seats],faction=seats[seat].faction,
        score=.5 if flow.gameWinner not in (0,1) else float(flow.gameWinner==seat),winner=flow.gameWinner,
        initialDealSha256=hashlib.sha256(json.dumps(initial,sort_keys=True).encode()).hexdigest(),
        eventSha256=hashlib.sha256(json.dumps(recorder.events,sort_keys=True).encode()).hexdigest(),
        guardedHeroes=sum(d.get('sequenceSearch',{}).get('revision')in ('hero-pass-v1','secured-round-v1') for d in audits),
        exchanges=exchanges,
        rounds=[dict(scores=[r.getPlayerScore(0),r.getPlayerScore(1)],winner=r.winningPlayer)
            for r in flow.cardManager.roundResults if r.played])


def group(task):
    pair,seed,swap=task
    try:
        rows=[run(pair,seed,swap,seat,variant,'native') for seat in (0,1)
            for variant in (('v7','hero') if STATE.get('gameplay_only') else ('v7','structural','hero','combined'))]
        rows += [run(pair,seed,swap,seat,variant,'direct') for seat in (0,1) for variant in (('hero',) if STATE.get('gameplay_only') else ('hero','combined'))]
        if len({r['initialDealSha256'] for r in rows})!=1:raise RuntimeError('initial deals differ')
        return rows,None
    except (RuntimeError,ValueError) as exc:return [],dict(task=task,error=str(exc))


def summarize(rows):
    native=[r for r in rows if r['kind']=='native'];matched={}
    for r in native:matched.setdefault((r['pair'],r['seed'],r['swapped'],r['seat']),{})[r['variant']]=r
    def block(selected):
        return dict(games=len(selected),score=sum(r['score'] for r in selected),
            guardedHeroes=sum(r['guardedHeroes'] for r in selected))
    comparisons={}
    for candidate,reference in (('hero','v7'),('combined','v7'),('combined','structural'),('structural','v7')):
        pairs=[(g[candidate],g[reference]) for g in matched.values() if candidate in g and reference in g]
        comparisons[f'{candidate}/{reference}']=dict(gains=sum(a['score']>b['score'] for a,b in pairs),
            regressions=sum(a['score']<b['score'] for a,b in pairs),equal=sum(a['score']==b['score'] for a,b in pairs),
            netScore=sum(a['score']-b['score'] for a,b in pairs))
    return dict(versusNative={v:block([r for r in native if r['variant']==v]) for v in ('v7','structural','hero','combined')},
        paired=comparisons,direct={v:block([r for r in rows if r['kind']=='direct' and r['variant']==v]) for v in ('hero','combined')},
        byFaction={str(f):{v:block([r for r in native if r['variant']==v and r['faction']==f]) for v in ('v7','structural','hero','combined')}
            for f in sorted({r['faction'] for r in rows})})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds',nargs='+',type=int,required=True)
    parser.add_argument('--all-npcs',action='store_true')
    parser.add_argument('--guard',choices=('hero','secured'),default='hero')
    parser.add_argument('--gameplay-only',action='store_true')
    parser.add_argument('--pair-indices',nargs='+',type=int)
    parser.add_argument('--jobs',type=int,default=4)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    STATE.update(setup(args.all_npcs));STATE['guard']=args.guard;STATE['gameplay_only']=args.gameplay_only
    indices=args.pair_indices if args.pair_indices is not None else list(range(len(STATE['pairs'])))
    if args.jobs<1 or not indices or len(set(indices))!=len(indices) or any(i<0 or i>=len(STATE['pairs']) for i in indices):parser.error('invalid jobs or pair indices')
    paths=[Path(__file__),ROOT/'sim/hero_pass_refinement.py',ROOT/'sim/secured_round_refinement.py',ROOT/'sim/structural_mulligan.py',ROOT/'sim/evaluate_mulligan.py',ROOT/'sim/evaluate_npc_policies.py',ROOT/'sim/mulligan_policy.py',ROOT/'sim/evaluate.py',ROOT/'sim/compare_policies.py']
    source={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    engine=engine_hashes();inputs=input_hashes();started=perf_counter()
    tasks=[(i,seed,swap) for i in indices for seed in args.seeds for swap in (False,True)]
    if args.jobs>1:
        import multiprocessing
        with multiprocessing.get_context('fork').Pool(args.jobs) as pool:groups=pool.map(group,tasks,chunksize=1)
    else:groups=list(map(group,tasks))
    rows=[r for group_rows,error in groups for r in group_rows];errors=[e for group_rows,e in groups if e]
    report=dict(guardFamily=args.guard,gameplayOnly=args.gameplay_only,variantMeaning={'hero':'selected guard without exchanges','combined':'selected guard plus structural exchanges','guardedHeroes':'legacy name: counts any selected guard activation'},profile='expert',seeds=args.seeds,pairIndices=indices,pairPlan=[dict(pair=i,decks=[d.name for d in STATE['pairs'][i]],leaders=[d.leader for d in STATE['pairs'][i]]) for i in indices],
        trials=rows,errors=errors,summary=summarize(rows),engineSourceSha256=engine,inputDataSha256=inputs,
        evaluationSourceSha256=source,sourceUnchangedDuringRun=engine==engine_hashes(),inputDataUnchangedDuringRun=inputs==input_hashes(),
        evaluationSourceUnchangedDuringRun=source=={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        elapsedSeconds=perf_counter()-started,validation=validation(),
        scope='Simulator-only explicitly audited runtime hooks; unchanged native NPC decks/leaders. Correlated seats/decks; reviewed seeds not held-out evidence. No production integration or global optimality claim.')
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(simulations=len(rows),errors=errors,summary=report['summary'],elapsedSeconds=report['elapsedSeconds'])))
    return int(bool(errors) or not all(report[k] for k in ('sourceUnchangedDuringRun','inputDataUnchangedDuringRun','evaluationSourceUnchangedDuringRun')))


if __name__=='__main__':raise SystemExit(main())
