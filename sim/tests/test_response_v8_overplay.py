"""Automated tests for V8 candidate overplay elimination.

Guards against spending cards when the round is already secured against a passed opponent.
"""
from dataclasses import replace
import pytest
from test_horn_evaluation import board, card, unit
from test_position import capture
from test_sequence_search import context
from gwentsim import constants as C
from gwentsim.options import Difficulty
from gwentsim.response_search import choose_response
from gwentsim.response_v8 import choose_response_v8


@pytest.mark.parametrize('faction', [
    C.FactionId_No_Mans_Land, C.FactionId_Nilfgaard, C.FactionId_Northern_Kingdom,
    C.FactionId_Scoiatael, C.FactionId_Skellige
])
def test_v8_passes_when_ahead_after_opponent_passed(board, faction):
    """When ahead (7 vs 0) and opponent passed, V7 overplays but V8 passes to save hand."""
    unit(board, 7, 5)  # own melee unit power 7
    for power in (10, 30, 70):
        card(board, power, 1, C.CardType_Creature | C.CardType_Melee | C.CardType_Hero, (C.CardEffect_None,))

    state = capture(board)
    ctx = context(round_index=0, own_losses=0, opponent_losses=0,
                  opponent_passed=True, opponent_hand_count=0, own_faction=faction)

    # V7 baseline has the blunder: it plays a card into an already won round
    v7_res = choose_response(state, ctx, Difficulty.EXPERT)
    assert v7_res.action is not None, "Baseline V7 should demonstrate the overplay bug"

    # V8 candidate fixes the blunder: it passes and retains all cards
    v8_res = choose_response_v8(state, ctx, Difficulty.EXPERT)
    assert v8_res.action is None, "V8 must pass when round is already secured"
    assert v8_res.reason == 'pass_for_match_resources'
    assert v8_res.revision == 'response-v8'


def test_v8_does_not_pass_when_trailing_against_passed_opponent(board):
    """When trailing (5 vs 10) against a passed opponent, V8 must NOT pass if it can overtake."""
    unit(board, 5, 5)   # own melee unit power 5
    card(board, 10, 5, C.CardType_Creature | C.CardType_Melee, player=1)  # opp melee unit power 10
    card(board, 8, 1, C.CardType_Creature | C.CardType_Melee, player=0)  # own 8-power unit in hand

    state = capture(board)
    ctx = context(round_index=0, own_losses=0, opponent_losses=0,
                  opponent_passed=True, opponent_hand_count=0)

    v8_res = choose_response_v8(state, ctx, Difficulty.EXPERT)
    assert v8_res.action is not None, "V8 must play card to overtake when trailing"


def test_v8_allows_safe_spy_draw_when_ahead(board):
    """A spy that safely draws while keeping the round won is permitted."""
    unit(board, 20, 5)  # own melee power 20
    card(board, 5, 5, C.CardType_Creature | C.CardType_Melee, player=1)  # opp melee power 5
    # Spy with 4 power given to opponent: after play, 20 vs 9 -> still secured!
    spy = card(board, 4, 1, C.CardType_Creature | C.CardType_Melee | C.CardType_Spy, (C.CardEffect_Draw2,), player=0)

    state = capture(board)
    ctx = context(round_index=0, own_losses=0, opponent_losses=0,
                  opponent_passed=True, opponent_hand_count=5)

    v8_res = choose_response_v8(state, ctx, Difficulty.EXPERT)
    if v8_res.action is not None:
        assert v8_res.action.source == spy.instanceId
