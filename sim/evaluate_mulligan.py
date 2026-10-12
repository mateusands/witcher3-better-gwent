#!/usr/bin/env python3
"""Controlled original mulligan study on unchanged native NPC decks.

All three variants use V7 for actual play, against native AI, and differ only in
zero/random/up-to-two evaluated initial exchanges. Both seats/deck orders are
exchanged. No shuffled deck order or opponent hand enters the mulligan policy.
Runtime hooks are simulator-only; native rule-source files remain unchanged.
"""
import argparse,hashlib,json,random
from pathlib import Path
from contextlib import contextmanager
from time import perf_counter
from gwentsim import constants as C
from gwentsim.data import load_match
from gwentsim.native_decks import NativeDecks
from gwentsim.deck_pool import build_pool,FACTIONS
from gwentsim.position import Position
from gwentsim.gwint.match import run_match
from gwentsim.gwint.gwint_game_flow_controller import GwintGameFlowController
from gwentsim.rng import SeededRandom
from mulligan_policy import choose_mulligan,initial_hand_potential
from evaluate import engine_hashes,validation

ROOT=Path(__file__).resolve().parents[1]
STATE={}


def setup():
    if not STATE:
        match=load_match(ROOT/'game/records/g113.json')
        native=NativeDecks(ROOT/'game/vanilla/xml/content0/gameplay/items',match.templates)
        decks=[d for d in build_pool(native,match.templates) if d.native_leader]
        by_faction={f:[d for d in decks if d.faction==f] for f in FACTIONS}
        own=[by_faction[f][len(by_faction[f])//2] for f in FACTIONS]
        # Fixed before seeing results; use existing NPC collections and leaders.
        pairs=[(d,by_faction[FACTIONS[(i+1)%len(FACTIONS)]][0]) for i,d in enumerate(own)]
        STATE.update(match=match,pairs=pairs)
    return STATE


@contextmanager
def exchange_hook(seat,variant,seed,audit):
    original=GwintGameFlowController.state_begin_Mulligan
    def begin(flow):
        original(flow)
        if variant=='none':return
        cm=flow.cardManager;local=random.Random(seed*1009+seat)
        if variant=='leader':
            # A leader that pulls a weather card from the deck: that weather in the opening hand
            # goes back to the deck (the leader can still pull it), freeing a hand slot.
            from gwentsim.npc_balance import LEADER_PICK
            king=cm.getCardTemplate(cm.playerDeckDefinitions[seat].selectedKingIndex)
            weather=LEADER_PICK.get(king.getFirstEffect())
            for turn in range(2):
                state=Position.from_manager(cm,seat)
                key=next((k for k in state.hand if weather is not None and state.cards[k].effects[:1]==(weather,)),None)
                if key is None or not sum(state.counts.values()):break
                source=cm.getCardInstance(key);template=source.templateId
                if cm.mulliganCard(source) is None:raise RuntimeError('native exchange failed')
                audit.append(dict(turn=turn,variant=variant,source=key,sourceTemplate=template))
            flow.hooks.record('S','ai_mulligan')
            return
        for turn in range(2):
            state=Position.from_manager(cm,seat)
            if not state.hand or not sum(state.counts.values()):break
            if variant=='structural':
                from structural_mulligan import choose_structural_mulligan
                decision=choose_structural_mulligan(state)
            else:
                decision=choose_mulligan(state)
            key=decision.source if variant in('evaluated','structural') else local.choice(state.hand)
            entry=dict(turn=turn,variant=variant,beforePotential=getattr(decision,'before',None),
                projected=decision.audit() if variant in('evaluated','structural') else None,source=key)
            if key is None:audit.append(entry);break
            source=cm.getCardInstance(key);before_count=len(state.hand)
            template=source.templateId
            replacement=cm.mulliganCard(source)
            if replacement is None:raise RuntimeError('native exchange failed')
            after=Position.from_manager(cm,seat)
            if len(after.hand)!=before_count:raise RuntimeError('exchange changed hand size')
            entry.update(sourceTemplate=template,replacementTemplate=replacement.templateId,
                afterPotential=initial_hand_potential(after),afterV7Reserve=after.reserve(),handCountUnchanged=True)
            audit.append(entry)
        flow.hooks.record('S','ai_mulligan')
    GwintGameFlowController.state_begin_Mulligan=begin
    try:yield
    finally:GwintGameFlowController.state_begin_Mulligan=original


def group(task):
    index,seed,swap,profile=task;data=setup();a,b=data['pairs'][index]
    seats=(b,a) if swap else (a,b);match=data['match'];rows=[]
    try:
        for seat in (0,1):
            for variant in ('none','random','evaluated'):
                decisions=[];policies=tuple('response-v6' if s==seat else 'vanilla' for s in (0,1))
                started=perf_counter()
                with exchange_hook(seat,variant,seed,decisions):
                    recorder,flow=run_match(match.templates.values(),[d.for_player(i) for i,d in enumerate(seats)],
                        match.card_values,SeededRandom(seed),seat_policies=policies,
                        candidate_profile=profile,coin_toss_choice=lambda:True)
                initial=next(e for e in recorder.events if e['k']=='S' and e['tag']=='deal')
                rows.append(dict(pair=index,seed=seed,swapped=swap,seat=seat,variant=variant,
                    decks=[d.name for d in seats],leaders=[d.leader for d in seats],
                    faction=seats[seat].faction,winner=flow.gameWinner,
                    score=0.5 if flow.gameWinner not in (0,1) else float(flow.gameWinner==seat),
                    initialDealSha256=hashlib.sha256(json.dumps(initial,sort_keys=True).encode()).hexdigest(),
                    decisions=decisions,elapsedSeconds=perf_counter()-started,
                    rounds=[dict(scores=[r.getPlayerScore(0),r.getPlayerScore(1)],winner=r.winningPlayer)
                        for r in flow.cardManager.roundResults if r.played]))
    except (RuntimeError,ValueError) as error:return [],dict(task=task,error=str(error))
    for seat in (0,1):
        if len({r['initialDealSha256'] for r in rows if r['seat']==seat})!=1:
            return [],dict(task=task,error='initial deals differ across variants')
    return rows,None


def summarize(rows):
    out={}
    for variant in ('none','random','evaluated'):
        subset=[r for r in rows if r['variant']==variant]
        out[variant]=dict(games=len(subset),score=sum(r['score'] for r in subset),
            swaps=sum(d['source'] is not None for r in subset for d in r['decisions']))
    groups={}
    for r in rows:groups.setdefault((r['pair'],r['seed'],r['swapped'],r['seat']),{})[r['variant']]=r
    comparisons={}
    for reference in ('none','random'):
        matched=[(g['evaluated'],g[reference]) for g in groups.values()]
        comparisons[reference]=dict(gains=sum(a['score']>b['score'] for a,b in matched),
            regressions=sum(a['score']<b['score'] for a,b in matched),
            equal=sum(a['score']==b['score'] for a,b in matched),
            netScore=sum(a['score']-b['score'] for a,b in matched))
    return dict(variants=out,paired=comparisons,
        byFaction={str(f):{v:dict(games=len([r for r in rows if r['faction']==f and r['variant']==v]),
            score=sum(r['score'] for r in rows if r['faction']==f and r['variant']==v))
            for v in out} for f in FACTIONS},
        scope='Five fixed native NPC pairs, correlated seats/deck swaps; not all NPCs or a release acceptance gate')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds',nargs='+',type=int,required=True)
    parser.add_argument('--profile',choices=['hard','expert'],default='expert')
    parser.add_argument('--jobs',type=int,default=4)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    hashes=engine_hashes();started=perf_counter();data=setup()
    # Hash source/fixtures prospectively, including the runtime hook and evaluator.
    paths=[Path(__file__),ROOT/'sim/mulligan_policy.py',ROOT/'sim/evaluate.py',ROOT/'game/records/g113.json']
    paths+=sorted((ROOT/'game/vanilla/xml/content0/gameplay/items').glob('*.xml'))
    inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    tasks=[(i,seed,swap,3 if args.profile=='expert' else 2)
        for i in range(len(data['pairs'])) for seed in args.seeds for swap in (False,True)]
    if args.jobs>1:
        import multiprocessing
        with multiprocessing.get_context('fork').Pool(args.jobs) as pool:groups=pool.map(group,tasks,chunksize=1)
    else:groups=list(map(group,tasks))
    rows=[r for trials,error in groups for r in trials];errors=[e for trials,e in groups if e]
    report=dict(profile=args.profile,seeds=args.seeds,trials=rows,errors=errors,
        summary=summarize(rows),engineSourceSha256=hashes,
        sourceUnchangedDuringRun=engine_hashes()==hashes,inputSourceSha256=inputs,
        inputsUnchanged=inputs=={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        elapsedSeconds=perf_counter()-started,validation=validation(),
        limitation='Expected value uses a uniform own-template prior and V7 reserve; match strength remains empirical. Simulator hooks only; not production integration.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(summary=report['summary'],errors=errors,elapsedSeconds=report['elapsedSeconds'],
        sourceUnchanged=report['sourceUnchangedDuringRun'],inputsUnchanged=report['inputsUnchanged'])))
    return int(bool(errors) or not report['sourceUnchangedDuringRun'] or not report['inputsUnchanged'])


if __name__=='__main__':raise SystemExit(main())
