"""A pass must account for supported hypothetical cards spent catching up."""
from dataclasses import replace
from test_horn_evaluation import board, card, unit
from test_position import capture
from test_secured_round_refinement import ctx
from gwentsim import constants as C
from gwentsim.position import Card
from gwentsim.opponent_belief import Hypothesis
from gwentsim.options import Difficulty
from pass_completion import completion_value


def scenario(board, own_power=10):
    unit(board, own_power, 5)
    card(board, 8, 1, C.CardType_Creature | C.CardType_Melee)
    # An actual hidden opponent card is not part of the acting snapshot and must
    # never become a hypothetical reply.
    card(board, 50, 1, C.CardType_Creature | C.CardType_Melee, player=1)
    state = capture(board)
    context = replace(ctx(), round_index=1, opponent_losses=1,
        opponent_passed=False, opponent_hand_count=2,
        own_faction=C.FactionId_Northern_Kingdom,
        opponent_faction=C.FactionId_Scoiatael)
    body = Card(-100, 900, 7, C.CardType_Creature | C.CardType_Melee,
        (C.CardEffect_None,), (), 1, 1, 1)
    hypothesis = Hypothesis((body, replace(body, key=-101)), (), 0, 'test-known-scenario')
    return state, context, hypothesis


def test_opponent_spends_two_hypothetical_units_before_pass_is_valued(board):
    state, context, hypothesis = scenario(board)
    before = state.clone()
    audit = []
    value = completion_value(state, context, hypothesis, Difficulty.EXPERT, audit)
    assert value is not None and 0 <= value <= 1
    assert audit[0]['completed'] and len(audit[0]['moves']) == 2
    assert audit[0]['remainingHypotheticalCards'] == 0
    assert audit[0]['scores'] == (10, 14)
    assert state == before
    assert all(a['source'] in (-100, -101) for a in audit[0]['moves'])


def test_failed_bounded_completion_is_not_a_proven_win(board):
    state, context, hypothesis = scenario(board, 20)
    assert completion_value(state, context, hypothesis, Difficulty.EXPERT) is None


def test_unsupported_hypothesis_keeps_reference_estimate(board):
    state, context, hypothesis = scenario(board)
    assert completion_value(state, context, replace(hypothesis, unsupported=1)) is None


def test_other_rounds_and_already_passed_opponent_are_unchanged(board):
    state, context, hypothesis = scenario(board)
    assert completion_value(state, replace(context, round_index=0), hypothesis) is None
    assert completion_value(state, replace(context, opponent_passed=True), hypothesis) is None
    assert completion_value(state, replace(context, own_losses=1), hypothesis) is None
