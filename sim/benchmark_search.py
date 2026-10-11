#!/usr/bin/env python3
"""Local search latency and budgets on public positions from native seeded matches.

Python timings do not predict Scaleform latency. No game installation is touched.
"""
import json
import argparse
import time
from pathlib import Path
from statistics import median
from gwentsim.data import load_match
from gwentsim.rng import SeededRandom
from gwentsim.gwint.match import run_match
from gwentsim.gwint.card_manager import CardManager
from gwentsim.gwint.gwint_game_flow_controller import GwintGameFlowController
from gwentsim.gwint.base_player_controller import ROUND_PLAYER_STATUS_DONE
from gwentsim.position import Position
from gwentsim.sequence_search import Context,choose_sequence
from gwentsim.options import Difficulty

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy',choices=('sequence-v5','response-v6'),default='sequence-v5')
    args=parser.parse_args()
    search=choose_sequence
    if args.policy=='response-v6':
        from gwentsim.response_search import choose_response
        search=choose_response
    samples=[];sampled_per_pair=0
    def observe(event):
        nonlocal sampled_per_pair
        if event['k']!='A' or sampled_per_pair>=10:return
        sampled_per_pair+=1
        cm=CardManager.getInstance();flow=GwintGameFlowController.getInstance();player=event['player'];other=1-player
        state=Position.from_manager(cm,player)
        ctx=Context(flow.currentRound,
            sum(r.played and r.winningPlayer!=player for r in cm.roundResults),
            sum(r.played and r.winningPlayer!=other for r in cm.roundResults),
            flow.playerControllers[other].currentRoundStatus==ROUND_PLAYER_STATUS_DONE,
            len(cm.getCardInstanceList(1,other)),cm.playerDeckDefinitions[player].getDeckFaction(),
            cm.playerDeckDefinitions[other].getDeckFaction(),bool(cm.getCardLeader(player).canBeUsed),bool(cm.getCardLeader(other).canBeUsed))
        for difficulty in Difficulty:
            elapsed=[];result=None
            for _ in range(2):
                started=time.perf_counter();plan=search(state,ctx,difficulty);elapsed.append((time.perf_counter()-started)*1000)
                if result is not None:assert result==plan
                result=plan
            samples.append(dict(profile=difficulty.name,ms=median(elapsed),nodes=result.nodes,ownHand=len(state.hand)))
    for name in ('g101','g105','g109','g113'):
        sampled_per_pair=0
        match=load_match(ROOT/f'game/records/{name}.json')
        run_match(match.templates.values(),match.decks,match.card_values,SeededRandom(90),coin_toss_choice=lambda:True,on_event=observe)
    report=dict(scope='Local Python only; not production latency.',policy=args.policy,profiles={})
    for difficulty in Difficulty:
        rows=[s for s in samples if s['profile']==difficulty.name];times=sorted(s['ms'] for s in rows)
        report['profiles'][difficulty.name]=dict(samples=len(rows),medianMs=median(times),p95Ms=times[min(len(times)-1,int(len(times)*.95))],
            maxMs=max(times),maxNodes=max(s['nodes'] for s in rows))
    destination='response-latency.json' if args.policy=='response-v6' else 'search-latency.json'
    (ROOT/'game/evaluations'/destination).write_text(json.dumps(report,indent=2)+'\n')
    print(report)


if __name__=='__main__':main()
