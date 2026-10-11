"""Catalog coupling, revealed caps and the information boundary."""
from collections import Counter
from dataclasses import replace
from pathlib import Path
import pytest
from test_horn_evaluation import board,card
from test_position import capture
from test_sequence_search import context
from gwentsim import constants as C,rng
from gwentsim.data import load_match
from gwentsim.position import Card
from coupled_belief import exponential_priority,ranked_copies,coupled_hypotheses


def native_scorch(state):
    if 2 in state.catalog:
        replacement=max(state.catalog)+100
        old=state.catalog.pop(2)
        state.catalog[replacement]=replace(old,template=replacement)
        state.cards={k:replace(c,template=replacement) if c.template==2 else c for k,c in state.cards.items()}
        if 2 in state.counts:state.counts[replacement]=state.counts.pop(2)
    t=load_match(Path(__file__).resolve().parents[2]/'game/records/g113.json').templates[2]
    state.catalog[2]=Card(0,2,t.power,t.type_array,t.effect_flags,tuple(t.summon_flags or ()),0,0,1,faction=t.faction)


def test_adding_global_scorch_cannot_shuffle_existing_copy_priorities(board):
    for power in (4,7,10):card(board,power,1,C.CardType_Creature|C.CardType_Melee)
    state=capture(board)
    # Synthetic template 2 is moved aside before actual metadata is inserted.
    native_scorch(state);before=state.clone();ctx=context(opponent_passed=False,opponent_hand_count=3)
    for scenario in range(6):
        old=ranked_copies(state,ctx,scenario,include_scorch=False)
        new=ranked_copies(state,ctx,scenario,include_scorch=True)
        assert tuple(x for x in new if x[0]!=2)==old
    assert state==before


def test_revealed_caps_hero_capacity_and_unrelated_global_exclusion(board,monkeypatch):
    hero=card(board,10,1,C.CardType_Creature|C.CardType_Melee|C.CardType_Hero)
    unrelated=card(board,0,1,C.CardType_Global_Effect,(C.CardEffect_None,))
    state=capture(board)
    # Keep the synthetic hero distinct from native template 2.
    native_scorch(state)
    state.cards[991]=replace(state.catalog[2],key=991,owner=1,player=1,row=2)
    def forbidden(*args):raise AssertionError('game RNG consumed')
    monkeypatch.setattr(rng,'math_random',forbidden)
    ctx=context(opponent_passed=False,opponent_hand_count=1)
    for h in coupled_hypotheses(state,ctx,6):
        total=Counter(c.template for c in h.hand)+Counter(dict(h.counts))
        assert total[state.cards[hero.instanceId].template]<=1 and total[2]<=2
        assert total[state.cards[unrelated.instanceId].template]==0
        assert all(c.key<0 and c.owner==1 and c.player==1 and c.row==1 for c in h.hand)
    assert coupled_hypotheses(state,ctx,6)==coupled_hypotheses(state,ctx,6)


def test_no_missing_card_both_arms_are_identical(board):
    card(board,7,1,C.CardType_Creature|C.CardType_Melee)
    state=capture(board);ctx=context(opponent_passed=False,opponent_hand_count=2)
    assert coupled_hypotheses(state,ctx,6,include_scorch=False)==coupled_hypotheses(state,ctx,6)
    assert coupled_hypotheses(state,replace(ctx,opponent_hand_count=4))==()
    with pytest.raises(ValueError):coupled_hypotheses(state,ctx,0)


def test_exponential_weighting_has_expected_two_item_first_choice_frequency():
    # Fixed broad seed sweep detects inverted weights/ordering, not calibration
    # of any Gwent deck or a claim about exact pseudorandom independence.
    heavier=sum(exponential_priority(s,0,10,0,3)<exponential_priority(s,0,11,0,1) for s in range(5000))
    assert .73<heavier/5000<.77
    with pytest.raises(ValueError):exponential_priority(0,0,1,0,0)
