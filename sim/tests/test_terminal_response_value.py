"""Recompute a supported future outcome without its action-ranking epsilon."""
from dataclasses import replace
import pytest
from test_horn_evaluation import board,card,unit
from test_position import capture
from test_secured_round_refinement import ctx
from gwentsim import constants as C,response_search
from gwentsim.options import Difficulty
from gwentsim.sequence_search import choose_sequence,utility,public_opponent_average
from terminal_response_value import terminal_value,terminal_values


def test_saturated_winning_future_does_not_exceed_one_or_change_selected_path(board):
    unit(board,7,5)
    for power in (10,30,70):card(board,power,1,C.CardType_Creature|C.CardType_Melee|C.CardType_Hero)
    state=capture(board);before=state.clone();context=ctx()
    original=choose_sequence(state,context,Difficulty.EXPERT)
    assert original.utility>1 and original.sequence
    corrected=terminal_value(state,context,original)
    assert 0<=corrected.utility<=1 and corrected.utility<original.utility
    assert corrected.action==original.action and corrected.sequence==original.sequence
    assert corrected.nodes==original.nodes and state==before


def test_non_saturated_future_returns_same_terminal_utility_used_for_pass(board):
    unit(board,7,5)
    card(board,10,1,C.CardType_Creature|C.CardType_Melee)
    state=capture(board);context=replace(ctx(),opponent_hand_count=10)
    original=choose_sequence(state,context,Difficulty.EXPERT)
    after=state
    for action in original.sequence:after=after.apply(action)
    corrected=terminal_value(state,context,original)
    assert corrected.utility==utility(after,context,len(original.sequence),after.reserve(),
        public_opponent_average(state),passing=not original.sequence)
    assert corrected.pass_utility==original.pass_utility
    assert 0<=corrected.utility<=1


def test_unpassed_context_and_error_restore_keep_reference(board):
    unit(board,7,5);state=capture(board);context=replace(ctx(),opponent_passed=False)
    original=choose_sequence(state,context,Difficulty.EXPERT)
    assert terminal_value(state,context,original) is original
    old=response_search.choose_sequence
    with pytest.raises(RuntimeError):
        with terminal_values():
            assert response_search.choose_sequence is not old
            raise RuntimeError('scope test')
    assert response_search.choose_sequence is old


def test_runtime_hook_is_candidate_only_skips_real_passed_context_and_restores(board,monkeypatch):
    from types import SimpleNamespace
    from gwentsim.gwint.sequence_ai_controller import ResponseAIPlayerController
    from gwentsim.response_search import ResponseResult
    from terminal_response_value import terminal_response_hook
    state=capture(board);context=replace(ctx(),opponent_passed=False);seen=[]
    old=response_search.choose_sequence
    def search(controller,position,context):
        seen.append((controller.playerID,response_search.choose_sequence is old))
        return ResponseResult(None,.5,.5,0,0,0,False,'pass_for_match_resources')
    monkeypatch.setattr(ResponseAIPlayerController,'search',search)
    audit=[]
    with pytest.raises(RuntimeError):
        with terminal_response_hook(0,audit):
            a=SimpleNamespace(playerID=0,_decidedCardTransaction=None)
            b=SimpleNamespace(playerID=1,_decidedCardTransaction=None)
            ResponseAIPlayerController.search(a,state,context)
            ResponseAIPlayerController.search(b,state,context)
            ResponseAIPlayerController.search(a,state,replace(context,opponent_passed=True))
            raise RuntimeError('scope test')
    assert seen==[(0,True),(0,False),(1,True),(0,True)]
    assert len(audit)==1 and not audit[0]['changed']
    assert ResponseAIPlayerController.search is search
    assert response_search.choose_sequence is old
