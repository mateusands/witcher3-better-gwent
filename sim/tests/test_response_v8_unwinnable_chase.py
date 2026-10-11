"""Automated tests for V8 candidate unwinnable chase elimination.

Guards against wasting cards into a mathematically unwinnable round when the opponent
has already passed and we are not facing elimination (own_losses == 0).
"""
import pytest
from test_horn_evaluation import card, unit
from test_position import capture
from test_sequence_search import context
from gwentsim import constants as C
from gwentsim.gwint.card_manager import CardManager
from gwentsim.options import Difficulty
from gwentsim.response_search import choose_response
from gwentsim.response_v8 import choose_response_v8


@pytest.fixture
def board(monkeypatch):
    monkeypatch.setattr(CardManager, '_instance', None)
    monkeypatch.setattr(CardManager, 'lastInstanceID', 0)
    manager = CardManager()
    monkeypatch.setattr(manager, 'halfWeatherEnabled', lambda player: False)
    return manager


def test_v8_concedes_unwinnable_round1_against_passed_opponent(board):
    """When trailing 5 vs 60 in Round 1 and hand only has 14 points total, V8 must pass."""
    unit(board, 5, 5)  # own melee 5
    card(board, 60, 5, C.CardType_Creature | C.CardType_Melee, player=1)  # opp melee 60
    card(board, 6, 1, C.CardType_Creature | C.CardType_Melee, player=0)  # own hand 6
    card(board, 8, 1, C.CardType_Creature | C.CardType_Melee, player=0)  # own hand 8

    state = capture(board)
    ctx = context(round_index=0, own_losses=0, opponent_losses=0,
                  opponent_passed=True, opponent_hand_count=0,
                  own_leader_available=True)

    # Baseline V7 plays a card due to leader availability / search bias
    v7_res = choose_response(state, ctx, Difficulty.EXPERT)
    assert v7_res.action is not None, "V7 baseline should demonstrate the unwinnable chase bug"

    # V8 candidate fixes this: passes to save the 6 and 8 power cards for rounds 2 & 3
    v8_res = choose_response_v8(state, ctx, Difficulty.EXPERT)
    assert v8_res.action is None, "V8 must pass when the round cannot mathematically be won"
    assert v8_res.reason == 'concede_unwinnable_chase'
    assert v8_res.revision == 'response-v8'


def test_v8_concedes_unwinnable_round2_after_round1_win(board):
    """When 1-0 up, opponent passes with 50 points, our hand only has 10 points. Concede round 2."""
    unit(board, 4, 5)  # own melee 4
    card(board, 50, 5, C.CardType_Creature | C.CardType_Melee, player=1)  # opp melee 50
    card(board, 10, 1, C.CardType_Creature | C.CardType_Melee, player=0)  # own hand 10

    state = capture(board)
    ctx = context(round_index=1, own_losses=0, opponent_losses=1,
                  opponent_passed=True, opponent_hand_count=0,
                  own_leader_available=True)

    v8_res = choose_response_v8(state, ctx, Difficulty.EXPERT)
    assert v8_res.action is None, "V8 must concede round 2 when unwinnable to take full hand into round 3"
    assert v8_res.reason in ('concede_unwinnable_chase', 'proven_no_supported_overtake')


def test_v8_does_not_concede_in_elimination_round(board):
    """When facing elimination (own_losses == 1), V8 must NOT concede even if hard."""
    unit(board, 5, 5)  # own melee 5
    card(board, 20, 5, C.CardType_Creature | C.CardType_Melee, player=1)  # opp melee 20
    card(board, 10, 1, C.CardType_Creature | C.CardType_Melee, player=0)  # own hand 10

    state = capture(board)
    ctx = context(round_index=1, own_losses=1, opponent_losses=0,
                  opponent_passed=True, opponent_hand_count=0,
                  own_leader_available=False)

    v8_res = choose_response_v8(state, ctx, Difficulty.EXPERT)
    # Even if trailing 15 vs 20, passing is instant match defeat; V8 must play
    assert v8_res.action is not None, "V8 must NEVER voluntarily concede when facing match elimination"
