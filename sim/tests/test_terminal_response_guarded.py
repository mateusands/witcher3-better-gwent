"""Preserve incomplete future plans instead of certifying their empty path."""
from dataclasses import replace
from test_horn_evaluation import board,card
from test_position import capture
from test_secured_round_refinement import ctx
from gwentsim import constants as C,response_search
from gwentsim.sequence_search import choose_sequence
from gwentsim.options import Difficulty
from terminal_response_guarded import terminal_value,terminal_values
from terminal_response_value import terminal_value as unguarded_value


def test_real_unsupported_mushroom_with_losing_elimination_context_stays_unresolved(board):
    card(board,0,1,C.CardType_Row_Modifier|C.CardType_SeigeRangedMelee,(C.CardEffect_Mushroom,))
    card(board,10,5,C.CardType_Creature|C.CardType_Melee,player=1)
    state=capture(board);before=state.clone();context=replace(ctx(),own_losses=1)
    result=choose_sequence(state,context,Difficulty.EXPERT)
    assert result.reason=='no_supported_plan' and result.sequence==() and result.utility==-1
    assert unguarded_value(state,context,result).utility==0
    assert terminal_value(state,context,result) is result
    assert state==before


def test_wrapper_preserves_default_difficulty_signature_and_restores(board):
    state=capture(board);context=ctx();old=response_search.choose_sequence
    with terminal_values():
        default=response_search.choose_sequence(state,context)
        explicit=response_search.choose_sequence(state,context,Difficulty.HARD)
        assert default==explicit
    assert response_search.choose_sequence is old
