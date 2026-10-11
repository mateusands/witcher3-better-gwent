"""Remaining wins, real tie endpoints and candidate-only allocation changes."""
from dataclasses import replace
from types import SimpleNamespace
import pytest
from test_horn_evaluation import board,card,unit
from test_position import capture
from test_secured_round_refinement import ctx
from gwentsim import constants as C,response_search,sequence_search
from gwentsim.sequence_search import utility
from gwentsim.response_search import ResponseResult
from gwentsim.gwint.sequence_ai_controller import ResponseAIPlayerController
from first_round_budget import first_round_budget_utility,first_round_budget_hook


@pytest.mark.parametrize('faction',[1,2,3,4,5])
def test_losing_first_round_requires_sharing_known_resources_between_two_future_wins(board,faction):
    unit(board,3,5);card(board,4,5,C.CardType_Creature|C.CardType_Melee,player=1)
    card(board,100,1,C.CardType_Creature|C.CardType_Melee|C.CardType_Hero)
    state=capture(board);before=state.clone();context=replace(ctx(faction),opponent_hand_count=10)
    original=utility(state,context,0,100,5,passing=True)
    corrected=first_round_budget_utility(state,context,0,100,5,passing=True)
    assert 0<=corrected<original<=1 and state==before


def test_secured_win_and_real_first_round_draw_keep_reference_value(board):
    state=capture(board);context=ctx()
    assert first_round_budget_utility(state,context,0,100,5,passing=True)==utility(state,context,0,100,5,passing=True)
    unit(board,8,5);state=capture(board)
    assert first_round_budget_utility(state,context,0,100,5)==utility(state,context,0,100,5)
    for later in (replace(context,round_index=1),replace(context,own_losses=1),replace(context,opponent_losses=1)):
        assert first_round_budget_utility(state,later,1,100,5)==utility(state,later,1,100,5)


def test_hook_changes_only_candidate_first_round_and_restores_on_error(board,monkeypatch):
    old_response=response_search.utility;old_sequence=sequence_search.utility;seen=[]
    def search(controller,position,context):
        seen.append((controller.playerID,response_search.utility is old_response,sequence_search.utility is old_sequence))
        return ResponseResult(None,.5,.5,0,0,0,False,'pass_for_match_resources')
    monkeypatch.setattr(ResponseAIPlayerController,'search',search)
    state=capture(board);context=ctx();audit=[]
    with pytest.raises(RuntimeError):
        with first_round_budget_hook(0,audit):
            a=SimpleNamespace(playerID=0,_decidedCardTransaction=None)
            b=SimpleNamespace(playerID=1,_decidedCardTransaction=None)
            ResponseAIPlayerController.search(a,state,context)
            ResponseAIPlayerController.search(b,state,context)
            ResponseAIPlayerController.search(a,state,replace(context,round_index=1))
            raise RuntimeError('scope test')
    assert seen==[(0,True,True),(0,False,False),(1,True,True),(0,True,True)]
    assert len(audit)==1 and not audit[0]['changed']
    assert response_search.utility is old_response and sequence_search.utility is old_sequence
    assert ResponseAIPlayerController.search is search
