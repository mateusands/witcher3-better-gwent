"""Reviewed native deal: stop spending after a safe spy secures round one.

This is a behavioral regression for one observed recovery, not a general
strength claim. Both policies retain native collections/leaders and the same RNG.
"""
from pathlib import Path
from contextlib import nullcontext
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gwentsim.data import load_match
from gwentsim.native_decks import NativeDecks
from gwentsim.gwint.match import run_match
from gwentsim.rng import SeededRandom
from evaluate_secured_resources import refinement_hook

ROOT=Path(__file__).resolve().parents[2]


def test_safe_spy_then_pass_preserves_resources_for_the_decisive_round():
    fixture=load_match(ROOT/'game/records/g113.json')
    native=NativeDecks(ROOT/'game/vanilla/xml/content0/gameplay/items',fixture.templates)
    decks=[native.build('SkelEasy',3,player=0),native.build('Halflings',3,player=1)]
    results=[]
    for candidate in (False,True):
        audit=[]
        with refinement_hook(1,audit) if candidate else nullcontext():
            recorder,flow=run_match(fixture.templates.values(),decks,fixture.card_values,
                SeededRandom(200),seat_policies=('vanilla','response-v6'),
                candidate_profile=3,coin_toss_choice=lambda:True)
        deal=next(e for e in recorder.events if e['k']=='S' and e['tag']=='deal')
        results.append((deal,flow.gameWinner,audit))
    assert results[0][0]==results[1][0]
    assert results[0][1]==0 and results[1][1]==1
    changes=[row for row in results[1][2] if row['changed']]
    assert len(changes)==1
    change=changes[0]
    assert change['round']==0 and tuple(change['scores'])==(20,21)
    assert change['reference']['action'] is not None
    assert change['candidate']['action'] is None
    # A real safe spy before this pass remains selected; it is not blanket
    # conservation of every card after the opponent passes.
    spy=results[1][2][0]
    assert tuple(spy['scores'])==(16,21)
    assert spy['candidate']['action']==spy['reference']['action']
