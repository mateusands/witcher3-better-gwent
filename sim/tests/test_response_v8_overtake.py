"""Unit tests for V8 blunder fix #2: overtaking passed opponent when winnable."""
from unittest.mock import patch
import pytest
from test_horn_evaluation import board, card, unit
from test_position import capture
from test_sequence_search import context
from gwentsim import constants as C
from gwentsim.options import Difficulty
from gwentsim.response_search import choose_response, ResponseResult
from gwentsim.response_v8 import choose_response_v8
from gwentsim.position import Action


def test_overtakes_when_v7_passes_in_round_1(board):
    """When V7 would pass for match resources in Round 1, V8 overtakes with winning card."""
    # Board: opponent has 22 power, own has 16 power
    card(board, 22, 5, C.CardType_Creature | C.CardType_Melee, player=1)
    unit(board, 16, 5)
    # Own hand has card 7 (hero with 15 power, beats 22 reaching 31) plus other cards
    c7 = card(board, 15, 1, C.CardType_Creature | C.CardType_Hero | C.CardType_Melee, player=0)
    card(board, 8, 1, C.CardType_Creature | C.CardType_Melee, player=0)
    card(board, 10, 1, C.CardType_Creature | C.CardType_Melee, player=0)

    state = capture(board)
    ctx = context(round_index=0, own_losses=0, opponent_losses=0, opponent_passed=True, opponent_hand_count=6)

    # Mock V7 choosing to pass (simulating the g112 blunder where high reserve causes pass)
    with patch('gwentsim.response_v8.choose_response') as mock_v7:
        mock_v7.return_value = ResponseResult(
            action=None, value=0.98, pass_value=0.98, samples=0,
            nodes=10, unsupported=0, unresolved_leader=False,
            reason='pass_for_match_resources', alternatives=(),
            budget_exhausted=False, revision='response-v7'
        )
        res = choose_response_v8(state, ctx, Difficulty.EXPERT)

    assert res.action is not None
    assert res.reason == 'overtake_passed_opponent_win'
    assert res.revision == 'response-v8'


def test_overtakes_when_v7_passes_in_round_2_match_win(board):
    """In Round 2 when opponent has 1 loss, V8 overrides pass to secure 2-0 match win."""
    card(board, 10, 5, C.CardType_Creature | C.CardType_Melee, player=1)
    c12 = card(board, 12, 1, C.CardType_Creature | C.CardType_Melee, player=0)

    state = capture(board)
    ctx = context(round_index=1, own_losses=0, opponent_losses=1, opponent_passed=True, opponent_hand_count=0)

    with patch('gwentsim.response_v8.choose_response') as mock_v7:
        mock_v7.return_value = ResponseResult(
            action=None, value=0.95, pass_value=0.95, samples=0,
            nodes=10, unsupported=0, unresolved_leader=False,
            reason='pass_for_match_resources', alternatives=(),
            budget_exhausted=False, revision='response-v7'
        )
        res = choose_response_v8(state, ctx, Difficulty.EXPERT)

    assert res.action is not None
    assert res.reason == 'overtake_passed_opponent_win'
    assert res.revision == 'response-v8'


def test_preserves_supported_sequence_when_v7_already_plays(board):
    """If V7 already decides to play a sequence, V8 preserves it."""
    card(board, 3, 5, C.CardType_Creature | C.CardType_Melee, player=1)
    card(board, 4, 1, C.CardType_Creature | C.CardType_Melee, player=0)

    state = capture(board)
    ctx = context(round_index=0, own_losses=0, opponent_losses=0, opponent_passed=True, opponent_hand_count=5)
    res = choose_response_v8(state, ctx, Difficulty.EXPERT)
    assert res.action is not None
    assert res.reason == 'supported_sequence'
    assert res.revision == 'response-v8'


def test_does_not_play_spy_to_overtake(board):
    """A spy gives points to the opponent and should never be used as an overtake move."""
    card(board, 5, 5, C.CardType_Creature | C.CardType_Melee, player=1)
    card(board, 4, 1, C.CardType_Creature | C.CardType_Spy | C.CardType_Melee, player=0)

    state = capture(board)
    ctx = context(round_index=0, own_losses=0, opponent_losses=0, opponent_passed=True, opponent_hand_count=5)
    res = choose_response_v8(state, ctx, Difficulty.EXPERT)
    assert res.action is None


def test_unwinnable_gap_passes_normally(board):
    """When trailing by more points than any card can produce, pass normally."""
    card(board, 50, 5, C.CardType_Creature | C.CardType_Melee, player=1)
    card(board, 4, 1, C.CardType_Creature | C.CardType_Melee, player=0)

    state = capture(board)
    ctx = context(round_index=0, own_losses=0, opponent_losses=0, opponent_passed=True, opponent_hand_count=5)
    res = choose_response_v8(state, ctx, Difficulty.EXPERT)
    assert res.action is None


def test_equal_cost_candidates_tiebreak_without_action_comparison(board):
    """When multiple winning cards have identical cost and gain, sorting must not fail on Action objects."""
    card(board, 3, 5, C.CardType_Creature | C.CardType_Melee, player=1)
    # Two identical 4-power melee units
    c1 = card(board, 4, 1, C.CardType_Creature | C.CardType_Melee, player=0)
    c2 = card(board, 4, 1, C.CardType_Creature | C.CardType_Melee, player=0)

    state = capture(board)
    ctx = context(round_index=0, own_losses=0, opponent_losses=0, opponent_passed=True, opponent_hand_count=5)

    with patch('gwentsim.response_v8.choose_response') as mock_v7:
        mock_v7.return_value = ResponseResult(
            action=None, value=0.98, pass_value=0.98, samples=0,
            nodes=10, unsupported=0, unresolved_leader=False,
            reason='pass_for_match_resources', alternatives=(),
            budget_exhausted=False, revision='response-v7'
        )
        res = choose_response_v8(state, ctx, Difficulty.EXPERT)

    assert res.action is not None
    assert res.reason == 'overtake_passed_opponent_win'
