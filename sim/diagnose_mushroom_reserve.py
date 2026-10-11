#!/usr/bin/env python3
"""Reproduce the unvalued future combo using a real native NPC initial deal.

Select a controlled subset of that own hand, without changing the NPC collection,
then contrast V7 reserve with a legal uncontested combination. This is a supported
hand-power ceiling diagnostic, not a guaranteed future score or strength result.
"""
import argparse,json
from dataclasses import replace
from pathlib import Path
from gwentsim import constants as C
from gwentsim.data import load_match
from gwentsim.native_decks import NativeDecks
from gwentsim.gwint.match import run_match
from gwentsim.gwint.card_manager import CardManager
from gwentsim.position import Action
from gwentsim.rng import SeededRandom
from mushroom_position import MushroomPosition
from evaluate import engine_hashes
from evaluate_secured_resources import files_hash

ROOT=Path(__file__).resolve().parents[1]


class DealObserved(Exception):pass


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    fixture=ROOT/'game/records/g113.json';directory=ROOT/'game/vanilla/xml/content0/gameplay/items'
    sources=[Path(__file__),ROOT/'sim/mushroom_position.py'];source=files_hash(sources)
    inputs=files_hash([fixture]+sorted(directory.glob('*.xml')));engine=engine_hashes()
    match=load_match(fixture);native=NativeDecks(directory,match.templates);result=None
    for seed in range(200):
        captured=[]
        def observe(event):
            if event['k']=='S' and event['tag']=='deal':
                captured.append(MushroomPosition.from_manager(CardManager.getInstance(),0));raise DealObserved()
        try:run_match(match.templates.values(),[native.build('SkelHard',3,player=0),native.build('Crach',3,player=1)],match.card_values,SeededRandom(seed),on_event=observe,coin_toss_choice=lambda:True)
        except DealObserved:pass
        if not captured:raise RuntimeError('native deal was not observed')
        state=captured[0]
        pair=[k for k in state.hand if state.cards[k].template==515]
        modifiers=[k for k in state.hand if state.cards[k].template==22]
        if len(pair)<2 or not modifiers:continue
        selected=tuple(pair[:2]+modifiers[:1])
        subset=replace(state,hand=selected,counts={},leader_ready={0:False,1:False})
        after=subset.apply(Action(selected[0],4)).apply(Action(selected[1],4)).apply(Action(selected[2],7))
        result=dict(seed=seed,deck='SkelHard/d3',nativeLeader=5002,heldTemplates=[state.cards[k].template for k in selected],
            inheritedV7Reserve=subset.reserve(),legalUncontestedComboScore=after.scores()[0],
            actions=[dict(source=selected[0],slot=4),dict(source=selected[1],slot=4),dict(source=selected[2],slot=7)],
            identityPreserved=all(k in after.board[0,4] for k in selected[:2]),
            scope='Controlled subset of a real native initial hand, normal-clear hand-value ceiling with no enemy response. No edited deck, order peek or guaranteed future score.')
        break
    if result is None:raise RuntimeError('no qualifying native initial deal found')
    report=dict(case=result,engineSourceSha256=engine,diagnosticSourceSha256=source,inputDataSha256=inputs,
        engineUnchanged=engine==engine_hashes(),diagnosticUnchanged=source==files_hash(sources),
        inputsUnchanged=inputs==files_hash([fixture]+sorted(directory.glob('*.xml'))))
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(result))
    return int(not all(report[k] for k in ('engineUnchanged','diagnosticUnchanged','inputsUnchanged')))


if __name__=='__main__':raise SystemExit(main())
