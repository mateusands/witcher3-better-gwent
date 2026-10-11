#!/usr/bin/env python3
"""Local own/public decision trace for an ISMCTS regression against V7.

Never records opponent hand identities or composition. Inputs are existing local
fixtures; outputs remain private simulator diagnostics. Not a strength benchmark.
"""
import argparse,json
from pathlib import Path
from dataclasses import asdict
from time import perf_counter
from gwentsim.data import load_match
from gwentsim.gwint.match import run_match
from gwentsim.gwint.card_manager import CardManager
from gwentsim.position import Position
from gwentsim.rng import SeededRandom
from evaluate import engine_hashes


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record',type=Path,required=True)
    parser.add_argument('--seed',type=int,required=True)
    parser.add_argument('--seat',type=int,choices=[0,1],required=True)
    parser.add_argument('--swap',action='store_true')
    parser.add_argument('--profile',choices=['easy','medium','hard','expert'],default='hard')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();match=load_match(args.record);observations=[];hashes=engine_hashes()
    policies=tuple('ismcts-v1' if s==args.seat else 'response-v6' for s in (0,1))
    def observe(event):
        if event['k']!='A' or event['player']!=args.seat:return
        cm=CardManager.getInstance();position=Position.from_manager(cm,args.seat)
        # Copy only observer-owned hand/counts and public row/grave identities.
        observations.append(dict(decision=event,scores=position.scores(),
            ownHand=[asdict(position.cards[k]) for k in position.hand],ownCounts=position.counts,
            publicBoard=[dict(side=side,row=row,cards=[asdict(position.cards[k]) for k in keys])
                for (side,row),keys in position.board.items()],
            publicGraves={str(s):[asdict(position.cards[k]) for k in position.grave[s]] for s in (0,1)}))
    started=perf_counter()
    recorder,flow=run_match(match.templates.values(),list(reversed(match.decks)) if args.swap else match.decks,
        match.card_values,SeededRandom(args.seed),seat_policies=policies,
        candidate_profile=['easy','medium','hard','expert'].index(args.profile),
        coin_toss_choice=lambda:True,on_event=observe)
    audits=flow.playerControllers[args.seat].policy_decisions
    if len(audits)!=len(observations):raise RuntimeError('decision audit/trace alignment mismatch')
    for observed,audit in zip(observations,audits):observed['audit']=audit
    report=dict(record=args.record.name,seed=args.seed,seat=args.seat,swapped=args.swap,
        profile=args.profile,policies=policies,winner=flow.gameWinner,observations=observations,
        elapsedSeconds=perf_counter()-started,engineSourceSha256=hashes,
        sourceUnchangedDuringRun=engine_hashes()==hashes,
        rounds=[dict(scores=[r.getPlayerScore(0),r.getPlayerScore(1)],winner=r.winningPlayer)
            for r in flow.cardManager.roundResults if r.played])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('winner','rounds','elapsedSeconds','sourceUnchangedDuringRun')}))
    return int(not report['sourceUnchangedDuringRun'])


if __name__=='__main__':raise SystemExit(main())
