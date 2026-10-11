"""Candidate-only phase correction and restoration of both utility aliases."""
from types import SimpleNamespace
from dataclasses import replace
import pytest
from test_horn_evaluation import board,unit
from test_position import capture
from test_secured_round_refinement import ctx,result
from evaluate_round_transition import transition_hook
from gwentsim import response_search,sequence_search
from gwentsim.gwint.sequence_ai_controller import ResponseAIPlayerController


def test_phase_hook_is_scoped_to_candidate_and_restores_both_aliases(board,monkeypatch):
    unit(board,7,5);state=capture(board);reference=result(None)
    seq=response_search.utility;own=sequence_search.utility;calls=[]
    def original(controller,position,context):
        calls.append((controller.playerID,response_search.utility is seq,sequence_search.utility is own))
        return reference
    monkeypatch.setattr(ResponseAIPlayerController,'search',original)
    context=replace(ctx(),round_index=1,opponent_losses=1);audit=[]
    with transition_hook(0,audit):
        assert ResponseAIPlayerController.search(SimpleNamespace(playerID=1),state,context) is reference
        candidate=ResponseAIPlayerController.search(SimpleNamespace(playerID=0),state,context)
        assert candidate.revision=='round-transition-v1'
        assert calls==[(1,True,True),(0,True,True),(0,False,False)]
        assert len(audit)==1 and not audit[0]['changed']
        assert response_search.utility is seq and sequence_search.utility is own
    assert ResponseAIPlayerController.search is original


def test_utility_aliases_restore_after_candidate_search_error(board,monkeypatch):
    state=capture(board);reference=result(None)
    seq=response_search.utility;own=sequence_search.utility
    def original(controller,position,context):
        if response_search.utility is not seq:raise RuntimeError('test candidate failure')
        return reference
    monkeypatch.setattr(ResponseAIPlayerController,'search',original)
    with pytest.raises(RuntimeError):
        with transition_hook(0,[]):
            ResponseAIPlayerController.search(SimpleNamespace(playerID=0),state,replace(ctx(),round_index=1,opponent_losses=1))
    assert ResponseAIPlayerController.search is original
    assert response_search.utility is seq and sequence_search.utility is own
