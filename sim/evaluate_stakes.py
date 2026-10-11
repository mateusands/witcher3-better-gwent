#!/usr/bin/env python3
"""Exploratory stake-vs-native-deck experiment; original definitions only, unchanged AI."""
import argparse
import hashlib
import json
from pathlib import Path

from gwentsim.data import load_match
from gwentsim.native_decks import NativeDecks
from gwentsim.betting import AcceptedBet
from gwentsim.gwint.match import run_match
from gwentsim.rng import SeededRandom
from gwentsim import constants as C
from evaluate import validation

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds',nargs='+',type=int,default=[0,1])
    parser.add_argument('--npcs',nargs='+')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    path=ROOT/'game/records/g113.json';source=load_match(path)
    xml=ROOT/'game/vanilla/xml/content0/gameplay/items'
    native=NativeDecks(xml,source.templates)
    report=dict(status='exploratory',scope='Vanilla AI on both sides; only existing native deck version/dynamic requirements change. Not an in-game strength guarantee.',
        validation=validation(),seeds=args.seeds,sourceSha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        definitionsSha256=hashlib.sha256((xml/'def_gwint_decks.xml').read_bytes()).hexdigest(),trials=[],errors=[])
    players=[('recorded-player',source.decks[0]),('native-NKEasy',native.build('NKEasy',1,player=0))]
    for player_name,player in players:
        strength=sum(source.templates[index].power for index in player.card_indices if source.templates[index].is_type(C.CardType_Creature))
        for name in args.npcs or native.npc_names():
            for difficulty in (1,2,3):
                for seed in args.seeds:
                    baseline=None
                    for stake in (10,25,50,100,150):
                        bet=AcceptedBet(stake,True)
                        npc=native.build(name,difficulty,bet=bet)
                        row=dict(player=player_name,npc=name,nativeDifficulty=difficulty,seed=seed,stake=stake,
                                 selectedDifficulty=bet.native_difficulty(difficulty),stage=bet.stage,playerOriginalStrength=strength,
                                 baseCards=len(npc.card_indices),leader=npc.selected_king_index,
                                 activeDynamic=sum(strength>=r for r in npc.dynamic_card_requirements))
                        try:
                            rec,flow=run_match(source.templates.values(),[player,npc],source.card_values,SeededRandom(seed),coin_toss_choice=lambda:True)
                            row.update(npcWon=flow.gameWinner==1,winner=flow.gameWinner,
                                scores=[r.roundScores for r in flow.cardManager.roundResults if r.played],
                                eventSha256=hashlib.sha256(json.dumps(rec.events,sort_keys=True).encode()).hexdigest())
                            if baseline is None:baseline=row
                            row['sameStreamAsVanilla']=row['eventSha256']==baseline['eventSha256']
                            report['trials'].append(row)
                        except RuntimeError as exc:
                            report['errors'].append(dict(**row,error=str(exc)))
    report['droppedUnresolvedNames']=sorted(native.dropped_names)
    report['summary']=[]
    for stake in (10,25,50,100,150):
        rows=[r for r in report['trials'] if r['stake']==stake]
        report['summary'].append(dict(stake=stake,matches=len(rows),npcWins=sum(r['npcWon'] for r in rows),
                                     unchangedStreams=sum(r['sameStreamAsVanilla'] for r in rows)))
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
    print('exploratory:',len(report['trials']),'matches,',len(report['errors']),'errors')
    print(json.dumps(report['summary']))
    return int(bool(report['errors']))


if __name__=='__main__':raise SystemExit(main())
