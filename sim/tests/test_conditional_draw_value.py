"""Winner-draw correction must not silently change non-Northern phase heuristics."""
from dataclasses import replace
import pytest
from test_horn_evaluation import board,card
from test_position import capture
from test_round_transition_value import position,ctx
from gwentsim import constants as C
from gwentsim.sequence_search import utility
from conditional_draw_value import conditional_draw_utility as corrected


@pytest.mark.parametrize('own_faction,enemy_faction',[
    (C.FactionId_Nilfgaard,C.FactionId_No_Mans_Land),
    (C.FactionId_Scoiatael,C.FactionId_Skellige),
    (C.FactionId_Skellige,C.FactionId_Nilfgaard)])
def test_non_northern_phase_estimates_remain_exactly_v7(board,own_faction,enemy_faction):
    state=position(board)
    for own,enemy in ((0,1),(1,0)):
        context=replace(ctx(),own_losses=own,opponent_losses=enemy,
            own_faction=own_faction,opponent_faction=enemy_faction)
        assert corrected(state,context,0,20,6,passing=True)==utility(state,context,0,20,6,passing=True)


def test_losing_northern_player_gets_no_winner_draw(board):
    state=position(board);base=ctx();north=replace(base,own_faction=C.FactionId_Northern_Kingdom)
    assert corrected(state,north,0,20,6,passing=True)==pytest.approx(utility(state,base,0,20,6,passing=True))
    assert corrected(state,north,0,20,6,passing=True)<utility(state,north,0,20,6,passing=True)


def test_opponent_northern_winner_is_credited_without_phase_retuning(board):
    state=position(board);base=ctx();north=replace(base,opponent_faction=C.FactionId_Northern_Kingdom)
    assert corrected(state,north,0,20,6,passing=True)<utility(state,north,0,20,6,passing=True)


def test_valid_own_winner_draw_is_unchanged_but_pending_draw_capacity_is_respected(board):
    state=position(board,True);context=replace(ctx(),own_losses=1,opponent_losses=0,
        own_faction=C.FactionId_Northern_Kingdom)
    assert corrected(state,context,0,20,6)==utility(state,context,0,20,6)
    state.unknown_draws=2
    assert corrected(state,context,0,20,6)<utility(state,context,0,20,6)


def test_rounds_and_exact_second_win_tie_are_preserved(board):
    state=position(board,True);north=replace(ctx(),own_faction=C.FactionId_Northern_Kingdom)
    for context in (replace(north,round_index=0),replace(north,round_index=2,own_losses=1)):
        assert corrected(state,context,0,20,6)==utility(state,context,0,20,6)
    card(board,5,5,C.CardType_Creature|C.CardType_Melee,player=1)
    assert corrected(capture(board),north,0,20,6)==1
