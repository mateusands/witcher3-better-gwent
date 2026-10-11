#!/usr/bin/env python3
"""Local decision traces for outcome changes; excludes the opponent's hidden cards.

Paired initial seeds can diverge later. A first changed play is a lead for an
investigation, not proof that this move alone caused the match outcome.
"""
import argparse
import json
from pathlib import Path

from gwentsim.data import load_match
from gwentsim.gwint.match import run_match
from gwentsim.gwint.card_manager import CardManager
from gwentsim.rng import SeededRandom

ROOT = Path(__file__).resolve().parents[1]


def trace(path, seed, swapped, seat=None, policy='tactical-v3'):
    match = load_match(path)
    decks = list(reversed(match.decks)) if swapped else match.decks
    decisions = []
    current_round = 0
    def observe(event):
        nonlocal current_round
        if event['k'] == 'S' and event['tag'].startswith('t'):
            current_round = int(event['tag'][1:].split('.')[0])
        if event['k'] != 'A':
            return
        cm = CardManager.getInstance()
        player = event['player']
        hand = cm.getCardInstanceList(1, player)
        tx = event['tx']
        action = None if tx is None else {k: tx[k] for k in ('source', 'slot', 'targetPlayer', 'target')}
        decisions.append(dict(roundIndex=current_round, player=player, action=action,
            scores=list(cm.currentPlayerScores),
            ownHand=[dict(id=[c.templateId,c.instanceId], power=c.templateRef.power,
                          effects=c.templateRef.effectFlags,
                          gain=c.getOptimalTransaction().powerChangeResult,
                          strategic=c.getOptimalTransaction().strategicValue) for c in hand],
            opponentHandCount=len(cm.getCardInstanceList(1, 1-player))))
    rec, flow=run_match(match.templates.values(),decks,match.card_values,SeededRandom(seed),
        coin_toss_choice=lambda:True,on_event=observe,candidate_player=seat,candidate_policy=policy)
    return dict(winner=flow.gameWinner, decisions=decisions,
        roundHands=[dict(roundIndex=int(e['tag'][2:]),counts=[len(p['hand']) for p in e['players']])
                    for e in rec.events if e['k']=='S' and e['tag'].startswith('rr')])


def compare(baseline, candidate):
    for index,(a,b) in enumerate(zip(baseline['decisions'],candidate['decisions'])):
        if (a['player'],a['action'])!=(b['player'],b['action']):
            return dict(index=index,baseline=a,candidate=b)
    return None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports',nargs='+');parser.add_argument('--output',required=True)
    args=parser.parse_args();report=dict(cases=[])
    for source in args.reports:
        data=json.loads(Path(source).read_text())
        baselines={(t['record'],t['seed'],t['swapped']):t for t in data['trials'] if 'candidatePlayer' not in t}
        for t in data['trials']:
            if 'candidatePlayer' not in t:continue
            key=t['record'],t['seed'],t['swapped'];seat=t['candidatePlayer']
            won_before=baselines[key]['winner']==seat
            if won_before==t['candidateWon']:continue
            path=ROOT/'game/records'/t['record']
            before=trace(path,t['seed'],t['swapped'])
            after=trace(path,t['seed'],t['swapped'],seat,t['policy'])
            report['cases'].append(dict(report=Path(source).name,record=t['record'],seed=t['seed'],
                swapped=t['swapped'],seat=seat,outcome='regression' if won_before else 'gain',
                firstChangedPlay=compare(before,after),baseline=before,candidate=after))
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
    for c in report['cases']:
        first=c['firstChangedPlay']
        print(c['outcome'],c['record'],c['seed'],c['swapped'],c['seat'],
              None if first is None else dict(round=first['candidate']['roundIndex'],
                before=first['baseline']['action'],after=first['candidate']['action'],
                scores=first['candidate']['scores']))


if __name__=='__main__':main()
