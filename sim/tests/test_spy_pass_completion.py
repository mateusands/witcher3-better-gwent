"""Do not value an unprofitable retained Spy as friendly future points."""
from dataclasses import replace
import pytest
from test_horn_evaluation import board, card
from test_position import capture
from test_secured_round_refinement import ctx
from gwentsim import constants as C
from gwentsim.resource_value import spy_reserve_adjustment
from gwentsim.sequence_search import utility
from spy_pass_completion import corrected_completion_utility, spy_completion_hook


def context():
    return replace(ctx(C.FactionId_Nilfgaard), round_index=1,
        opponent_losses=1, opponent_hand_count=1,
        opponent_faction=C.FactionId_Scoiatael)


def test_owned_unprofitable_spy_loses_printed_friendly_credit(board):
    card(board, 7, 1, C.CardType_Creature | C.CardType_Melee | C.CardType_Spy,
        (C.CardEffect_Draw2,))
    body = card(board, 1, 2, C.CardType_Creature | C.CardType_Melee)
    card(board, 10, 5, C.CardType_Creature | C.CardType_Melee, player=1)
    state = capture(board)
    state.counts = {body.templateId: 2}
    reserve = state.reserve()
    assert reserve + spy_reserve_adjustment(state) == 0
    corrected = corrected_completion_utility(state, context(), 1, reserve, 6, True, 5)
    assert corrected < utility(state, context(), 1, reserve, 6, True, 5)


def test_profitable_hero_spy_keeps_own_draw_value(board):
    card(board, 0, 1, C.CardType_Creature | C.CardType_Melee | C.CardType_Spy | C.CardType_Hero,
        (C.CardEffect_Draw2,))
    body = card(board, 6, 2, C.CardType_Creature | C.CardType_Melee)
    state = capture(board)
    state.counts = {body.templateId: 2}
    state.double_spy = True
    assert state.reserve() + spy_reserve_adjustment(state) == 12


def test_nonspy_hand_estimate_is_identical(board):
    card(board, 6, 1, C.CardType_Creature | C.CardType_Melee)
    state = capture(board)
    assert corrected_completion_utility(state, context(), 1, state.reserve(), 6, True, 5) == utility(
        state, context(), 1, state.reserve(), 6, True, 5)


def test_hook_restores_private_utility_and_controller_after_error():
    import pass_completion
    from gwentsim.gwint.sequence_ai_controller import ResponseAIPlayerController
    original_search, original_utility = ResponseAIPlayerController.search, pass_completion.utility
    with pytest.raises(RuntimeError):
        with spy_completion_hook(0, []):
            assert pass_completion.utility is corrected_completion_utility
            raise RuntimeError('restoration check')
    assert pass_completion.utility is original_utility
    assert ResponseAIPlayerController.search is original_search
