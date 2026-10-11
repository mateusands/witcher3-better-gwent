"""Previously reviewed safe-spy recovery under the continuation experiment.

This selected case is a regression guard, not an independent strength sample.
"""
from pathlib import Path
from contextlib import nullcontext
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gwentsim.data import load_match
from gwentsim.native_decks import NativeDecks
from gwentsim.gwint.match import run_match
from gwentsim.rng import SeededRandom
from evaluate_secured_continuation import refinement_hook

ROOT=Path(__file__).resolve().parents[2]


def test_safe_spy_recovery_is_retained_without_new_cards_or_decks():
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
        results.append((next(e for e in recorder.events if e['k']=='S' and e['tag']=='deal'),flow.gameWinner,audit))
    assert results[0][0]==results[1][0]
    assert results[0][1]==0 and results[1][1]==1
    changes=[r for r in results[1][2] if r['changed']]
    assert len(changes)==1
    assert tuple(changes[0]['scores'])==(20,21)
    assert changes[0]['candidate']['action'] is None
